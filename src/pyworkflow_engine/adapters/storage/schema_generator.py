"""
Adapter persistence — génération DDL et sérialisation Pydantic ↔ SQL (ADR-017).

``SchemaGenerator`` produit le DDL SQLite à partir des ``TableMeta`` déclarés
dans chaque ``PersistableModel``.

``ModelSerializer`` convertit les instances Pydantic en lignes SQL-ready
(``to_row``) et vice-versa (``from_row``).

Règle hexagonale :
    Ce module dépend de ``ports/persistable.py`` et de la stdlib uniquement.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, get_args, get_origin

from pydantic import BaseModel, SecretStr

from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


# ── SchemaGenerator ──────────────────────────────────────────────────────────


def _q(name: str) -> str:
    """Quote un identifiant SQL avec des guillemets doubles (SQLite safe)."""
    return f'"{name}"'


class SchemaGenerator:
    """Génère le DDL SQLite depuis les ``TableMeta`` enregistrés.

    Inspiration : ``django.core.management.commands.migrate``.
    """

    # Mapping ColumnType → SQL type string (SQLite)
    _SQL_TYPE_MAP: dict[ColumnType, str] = {
        ColumnType.TEXT: "TEXT",
        ColumnType.INTEGER: "INTEGER",
        ColumnType.REAL: "REAL",
        ColumnType.BOOLEAN: "INTEGER",
        ColumnType.JSON: "TEXT",
        ColumnType.TIMESTAMP: "TIMESTAMP",
    }

    @classmethod
    def generate_create_table(cls, meta: TableMeta) -> str:
        """Génère un ``CREATE TABLE IF NOT EXISTS`` pour une ``TableMeta``.

        Args:
            meta: Métadonnées de la table.

        Returns:
            Instruction DDL complète.
        """
        lines: list[str] = []
        pk_cols = [col for col in meta.columns if col.primary_key]
        composite_pk = len(pk_cols) > 1

        for col in meta.columns:
            parts: list[str] = [f"    {_q(col.name)} {cls._SQL_TYPE_MAP[col.col_type]}"]

            # Inline PRIMARY KEY only when there's exactly one PK column
            if col.primary_key and not composite_pk:
                parts.append("PRIMARY KEY")
            if not col.nullable and not col.primary_key:
                parts.append("NOT NULL")
            if col.default is not None:
                default_val = col.default
                if isinstance(default_val, str):
                    default_val = f"'{default_val}'"
                parts.append(f"DEFAULT {default_val}")

            lines.append(" ".join(parts))

        # Composite PRIMARY KEY table constraint
        if composite_pk:
            pk_names = ", ".join(_q(c.name) for c in pk_cols)
            lines.append(f"    PRIMARY KEY ({pk_names})")

        # Foreign key constraints
        for col_name, ref_table, ref_col in meta.foreign_keys:
            cascade = " ON DELETE CASCADE" if meta.foreign_keys_cascade else ""
            lines.append(
                f"    FOREIGN KEY ({_q(col_name)}) REFERENCES {_q(ref_table)}({_q(ref_col)}){cascade}"
            )

        columns_sql = ",\n".join(lines)
        return f"CREATE TABLE IF NOT EXISTS {_q(meta.table_name)} (\n{columns_sql}\n);"

    @classmethod
    def generate_indexes(cls, meta: TableMeta) -> list[str]:
        """Génère les ``CREATE INDEX IF NOT EXISTS`` pour une ``TableMeta``.

        Couvre :
        - Les index individuels déclarés via ``ColumnDef.index``
        - Les index composites déclarés via ``TableMeta.indexes``

        Returns:
            Liste d'instructions DDL d'index.
        """
        stmts: list[str] = []

        # Index individuels (ColumnDef.index=True)
        for col in meta.columns:
            if col.index:
                idx_name = f"idx_{meta.table_name}_{col.name}"
                stmts.append(
                    f"CREATE INDEX IF NOT EXISTS {_q(idx_name)} "
                    f"ON {_q(meta.table_name)}({_q(col.name)});"
                )

        # Index composites (TableMeta.indexes)
        for cols in meta.indexes:
            idx_name = f"idx_{meta.table_name}_{'_'.join(cols)}"
            cols_sql = ", ".join(_q(c) for c in cols)
            stmts.append(
                f"CREATE INDEX IF NOT EXISTS {_q(idx_name)} "
                f"ON {_q(meta.table_name)}({cols_sql});"
            )

        return stmts

    @classmethod
    def generate_full_schema(cls) -> str:
        """Génère le DDL complet pour TOUS les modèles du ``ModelRegistry``.

        Les tables sont émises dans l'ordre topologique des FK
        (``ModelRegistry.get_ordered()``).

        Returns:
            Script DDL complet (multi-statements, séparé par ``\\n\\n``).
        """
        parts: list[str] = []

        # Pragma pour activer les FK dans SQLite
        parts.append("PRAGMA foreign_keys = ON;")

        for model_cls in ModelRegistry.get_ordered():
            meta: TableMeta = model_cls.__table_meta__
            parts.append(cls.generate_create_table(meta))
            for idx_stmt in cls.generate_indexes(meta):
                parts.append(idx_stmt)

        return "\n\n".join(parts)


# ── ModelSerializer ──────────────────────────────────────────────────────────


class ModelSerializer:
    """Sérialise/désérialise ``PersistableModel`` ↔ lignes SQL.

    Gère automatiquement les conversions de types :
    - ``JSON`` : ``BaseModel`` → ``model_dump_json()``, ``dict/list`` → ``json.dumps()``
    - ``TIMESTAMP`` : ``datetime`` → ``isoformat()``
    - ``BOOLEAN`` : ``bool`` → ``0/1``
    - ``SecretStr`` → ``get_secret_value()``
    - ``StrEnum`` → ``.value``
    """

    @classmethod
    def to_row(cls, instance: PersistableModel) -> dict[str, Any]:
        """Convertit un modèle Pydantic en dict SQL-ready.

        Seules les colonnes déclarées dans ``__table_meta__`` sont incluses.

        Args:
            instance: Instance Pydantic à sérialiser.

        Returns:
            Dict ``{column_name: sql_value}`` prêt pour un INSERT/UPDATE.
        """
        meta: TableMeta = instance.__table_meta__
        col_map = {c.name: c for c in meta.columns}
        row: dict[str, Any] = {}

        for col_name, col_def in col_map.items():
            value = getattr(instance, col_name, None)
            row[col_name] = cls._serialize_value(value, col_def)

        return row

    @classmethod
    def from_row(
        cls,
        model_class: type[PersistableModel],
        row: dict[str, Any] | Any,
    ) -> PersistableModel:
        """Convertit une ligne SQL en instance Pydantic.

        Args:
            model_class: Classe du modèle cible.
            row: Dict ou ``sqlite3.Row`` contenant les données.

        Returns:
            Instance du modèle Pydantic.
        """
        meta: TableMeta = model_class.__table_meta__
        col_map = {c.name: c for c in meta.columns}

        # Convertir sqlite3.Row → dict si nécessaire
        if not isinstance(row, dict):
            row = dict(row)

        data: dict[str, Any] = {}
        for col_name, col_def in col_map.items():
            if col_name in row:
                val = cls._deserialize_value(
                    row[col_name], col_def, model_class, col_name
                )
                if val is not None:
                    data[col_name] = val
                # When val is None, omit the key so Pydantic uses the field's
                # default / default_factory (e.g. list fields stored as NULL).

        return model_class.model_validate(data)

    # ── Sérialisation (Python → SQL) ────────────────────────────────

    @classmethod
    def _serialize_value(cls, value: Any, col_def: ColumnDef) -> Any:
        """Sérialise une valeur Python pour stockage SQL."""
        if value is None:
            return None

        match col_def.col_type:
            case ColumnType.JSON:
                return cls._serialize_json(value)
            case ColumnType.TIMESTAMP:
                if isinstance(value, datetime):
                    return value.isoformat()
                return str(value)
            case ColumnType.BOOLEAN:
                return 1 if value else 0
            case _:
                # TEXT, INTEGER, REAL
                if isinstance(value, SecretStr):
                    return value.get_secret_value()
                if hasattr(value, "value"):
                    # StrEnum → .value
                    return value.value
                return value

    @classmethod
    def _serialize_json(cls, value: Any) -> str | None:
        """Sérialise une valeur vers JSON string."""
        if value is None:
            return None
        if isinstance(value, BaseModel):
            return value.model_dump_json()
        if isinstance(value, list):
            # Handle list of BaseModel items
            serialized = [
                item.model_dump() if isinstance(item, BaseModel) else item
                for item in value
            ]
            return json.dumps(serialized, default=str)
        if isinstance(value, dict):
            return json.dumps(value, default=str)
        # Fallback
        return json.dumps(value, default=str)

    # ── Désérialisation (SQL → Python) ──────────────────────────────

    @classmethod
    def _deserialize_value(
        cls,
        value: Any,
        col_def: ColumnDef,
        model_class: type[PersistableModel],
        field_name: str,
    ) -> Any:
        """Désérialise une valeur SQL vers Python."""
        if value is None:
            return None

        match col_def.col_type:
            case ColumnType.JSON:
                return cls._deserialize_json(value, model_class, field_name)
            case ColumnType.TIMESTAMP:
                if isinstance(value, str):
                    return datetime.fromisoformat(value)
                return value
            case ColumnType.BOOLEAN:
                return bool(value)
            case _:
                return value

    @classmethod
    def _deserialize_json(
        cls,
        value: Any,
        model_class: type[PersistableModel],
        field_name: str,
    ) -> Any:
        """Désérialise une valeur JSON string vers le type Python attendu."""
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            # Déjà désérialisé (ex: test en mémoire)
            return value

        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

        # Tenter de résoudre le type du champ pour reconstruire les BaseModel embedded
        field_type = cls._get_field_type(model_class, field_name)
        if field_type is not None and _is_pydantic_model(field_type):
            return field_type.model_validate(parsed)

        # Vérifier si c'est un list[BaseModel]
        origin = get_origin(field_type)
        if origin is list:
            args = get_args(field_type)
            if args and _is_pydantic_model(args[0]):
                return [args[0].model_validate(item) for item in parsed]

        return parsed

    @classmethod
    def _get_field_type(
        cls, model_class: type[PersistableModel], field_name: str
    ) -> Any:
        """Récupère le type annoté d'un champ Pydantic.

        Gère les types ``Optional[T]`` en retournant ``T``.
        """
        field_info = model_class.model_fields.get(field_name)
        if field_info is None:
            return None

        annotation = field_info.annotation
        if annotation is None:
            return None

        # Résoudre Optional[T] → T
        origin = get_origin(annotation)
        if origin is type(None):
            return None

        # Union[T, None] (Optional)
        import types

        if origin is types.UnionType or (
            hasattr(origin, "__origin__") and str(origin) == "typing.Union"
        ):
            args = get_args(annotation)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return non_none[0]

        return annotation


def _is_pydantic_model(tp: Any) -> bool:
    """Vérifie si un type est une sous-classe de BaseModel."""
    try:
        return isinstance(tp, type) and issubclass(tp, BaseModel)
    except TypeError:
        return False


__all__ = [
    "SchemaGenerator",
    "ModelSerializer",
]
