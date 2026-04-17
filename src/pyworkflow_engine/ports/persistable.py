"""
Port — Contrat de persistence déclarative pour les modèles Pydantic (ADR-017).

Chaque modèle Pydantic qui doit être persisté :
1. Hérite de ``PersistableModel``
2. Déclare un ``__table_meta__: ClassVar[TableMeta]``
3. Est enregistré via ``@ModelRegistry.register``

Le ``ModelRegistry`` fournit un auto-discovery de tous les modèles
persistables, analogue à ``django.apps.apps.get_models()``.

Règle hexagonale :
    ``ports/persistable.py`` ne dépend que de la stdlib + pydantic.
    Les adapters (``adapters/storage/``) importent depuis ce module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel


# ── Types de colonnes SQL ─────────────────────────────────────────────────────


class ColumnType(StrEnum):
    """Types de colonnes SQL supportés par le SchemaGenerator.

    Note: BOOLEAN et JSON ont des valeurs distinctes de INTEGER/TEXT
    pour permettre la distinction dans ``match`` / ``if`` statements.
    Le mapping vers les types SQL réels est fait dans ``SchemaGenerator._SQL_TYPE_MAP``.
    """

    TEXT = "TEXT"
    INTEGER = "INTEGER"
    REAL = "REAL"
    BOOLEAN = "BOOLEAN"  # mapped to INTEGER by SchemaGenerator
    JSON = "JSON"  # mapped to TEXT by SchemaGenerator
    TIMESTAMP = "TIMESTAMP"


# ── Définition d'une colonne ──────────────────────────────────────────────────


@dataclass
class ColumnDef:
    """Définition d'une colonne SQL.

    Attributes:
        name: Nom de la colonne (doit correspondre au nom du champ Pydantic).
        col_type: Type SQL de la colonne.
        primary_key: Si ``True``, cette colonne est la clé primaire.
        nullable: Si ``True``, la colonne accepte NULL.
        default: Valeur par défaut SQL (string, int, ou None).
        foreign_key: Référence FK au format ``"table.column"`` (ex: ``"agents.id"``).
        index: Si ``True``, crée un index individuel sur cette colonne.
    """

    name: str
    col_type: ColumnType
    primary_key: bool = False
    nullable: bool = True
    default: Any = None
    foreign_key: str | None = None
    index: bool = False


# ── Métadonnées de table ──────────────────────────────────────────────────────


@dataclass
class TableMeta:
    """Métadonnées de persistence pour un modèle Pydantic.

    Équivalent du ``class Meta:`` de Django.

    Attributes:
        table_name: Nom de la table SQL.
        columns: Liste ordonnée des colonnes.
        indexes: Index composites (tuples de noms de colonnes).
        foreign_keys_cascade: Si ``True``, les FK utilisent ``ON DELETE CASCADE``.
    """

    table_name: str
    columns: list[ColumnDef]
    indexes: list[tuple[str, ...]] = field(default_factory=list)
    foreign_keys_cascade: bool = True

    @property
    def primary_key(self) -> ColumnDef | None:
        """Retourne la colonne PK (première trouvée)."""
        for col in self.columns:
            if col.primary_key:
                return col
        return None

    @property
    def pk_name(self) -> str:
        """Retourne le nom de la colonne PK."""
        pk = self.primary_key
        if pk is None:
            raise ValueError(f"Table '{self.table_name}' has no primary key defined")
        return pk.name

    @property
    def column_names(self) -> list[str]:
        """Retourne la liste des noms de colonnes."""
        return [c.name for c in self.columns]

    @property
    def foreign_keys(self) -> list[tuple[str, str, str]]:
        """Retourne les FK sous forme (col_name, ref_table, ref_col)."""
        fks: list[tuple[str, str, str]] = []
        for col in self.columns:
            if col.foreign_key:
                ref_table, ref_col = col.foreign_key.split(".")
                fks.append((col.name, ref_table, ref_col))
        return fks

    @property
    def referenced_tables(self) -> set[str]:
        """Retourne les noms des tables référencées par FK."""
        return {ref_table for _, ref_table, _ in self.foreign_keys}


# ── Modèle persistable (base Pydantic) ───────────────────────────────────────


class PersistableModel(BaseModel):
    """Base pour les modèles Pydantic qui doivent être persistés.

    Chaque sous-classe DOIT déclarer ``__table_meta__`` comme ``ClassVar[TableMeta]``.

    Usage::

        @ModelRegistry.register
        class Agent(PersistableModel):
            __table_meta__: ClassVar[TableMeta] = TableMeta(
                table_name="agents",
                columns=[...],
            )
            # ... champs Pydantic ...
    """

    __table_meta__: ClassVar[TableMeta]


# ── Registre global de modèles ───────────────────────────────────────────────


class ModelRegistry:
    """Registre centralisé de tous les modèles persistables.

    Analogue à ``django.apps.apps.get_models()``.

    Usage::

        @ModelRegistry.register
        class Agent(PersistableModel):
            __table_meta__ = TableMeta(table_name="agents", columns=[...])

        # Plus tard :
        all_models = ModelRegistry.get_all()       # {"agents": <Agent>}
        agent_cls = ModelRegistry.get_model("agents")
    """

    _models: dict[str, type[PersistableModel]] = {}

    @classmethod
    def register(cls, model: type[PersistableModel]) -> type[PersistableModel]:
        """Décorateur d'enregistrement d'un modèle persistable.

        Args:
            model: Classe Pydantic avec ``__table_meta__`` déclaré.

        Returns:
            La classe inchangée (permet l'usage comme décorateur ``@register``).

        Raises:
            ValueError: Si ``__table_meta__`` est absent.
        """
        meta = getattr(model, "__table_meta__", None)
        if meta is None:
            raise ValueError(
                f"{model.__name__} must define a __table_meta__ ClassVar[TableMeta]"
            )
        cls._models[meta.table_name] = model
        return model

    @classmethod
    def get_all(cls) -> dict[str, type[PersistableModel]]:
        """Retourne tous les modèles enregistrés {table_name: model_class}."""
        return dict(cls._models)

    @classmethod
    def get_model(cls, table_name: str) -> type[PersistableModel] | None:
        """Récupère un modèle par nom de table."""
        return cls._models.get(table_name)

    @classmethod
    def get_ordered(cls) -> list[type[PersistableModel]]:
        """Retourne les modèles triés par ordre topologique des FK.

        Les tables sans FK viennent en premier, puis celles qui
        dépendent de tables déjà émises. Garantit que les ``CREATE TABLE``
        respectent l'ordre des clés étrangères.

        Les FK vers des tables **non enregistrées** (externes) sont ignorées
        dans le calcul de l'ordre — seules les dépendances intra-registry comptent.
        """
        all_models = dict(cls._models)
        registered_tables = set(all_models.keys())
        ordered: list[type[PersistableModel]] = []
        emitted: set[str] = set()

        # Itérer jusqu'à ce que tous les modèles soient émis
        max_iterations = len(all_models) * 2  # guard against cycles
        iteration = 0
        while all_models and iteration < max_iterations:
            iteration += 1
            for table_name, model in list(all_models.items()):
                meta: TableMeta = model.__table_meta__
                # Only consider deps that are in the registry
                deps = meta.referenced_tables & registered_tables
                if deps <= emitted:
                    ordered.append(model)
                    emitted.add(table_name)
                    del all_models[table_name]

        # Si des modèles restent, il y a un cycle ou une FK vers une table inconnue
        if all_models:
            remaining = list(all_models.keys())
            raise ValueError(
                f"Cannot resolve table creation order — circular or missing FK "
                f"dependencies: {remaining}"
            )

        return ordered

    @classmethod
    def clear(cls) -> None:
        """Réinitialise le registre (utile pour les tests)."""
        cls._models.clear()


__all__ = [
    "ColumnType",
    "ColumnDef",
    "TableMeta",
    "PersistableModel",
    "ModelRegistry",
]
