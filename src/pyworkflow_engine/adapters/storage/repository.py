"""
Adapter persistence — Repository CRUD générique (ADR-017).

``Repository[T]`` fournit un accès CRUD typé pour tout
``PersistableModel``, analogue au ``Manager`` de Django
(``Model.objects.filter(...)``).

Filtres dynamiques supportés (style Django ``QuerySet.filter()``) :
    - ``field=value``          → ``field = ?``
    - ``field__gte=value``     → ``field >= ?``
    - ``field__lte=value``     → ``field <= ?``
    - ``field__gt=value``      → ``field > ?``
    - ``field__lt=value``      → ``field < ?``
    - ``field__like=value``    → ``field LIKE ?``
    - ``field__in=values``     → ``field IN (?, ?, ?)``
    - ``field__isnull=True``   → ``field IS NULL``

Tous les filtres utilisent des paramètres positionnels (``?``) —
**aucune injection SQL possible**.

Règle hexagonale :
    Ce module dépend de ``ports/persistable.py`` + ``adapters/storage/schema_generator.py``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pyworkflow_engine.adapters.storage.schema_generator import ModelSerializer, _q
from pyworkflow_engine.ports.persistable import PersistableModel, TableMeta

T = TypeVar("T", bound=PersistableModel)

# ── Opérateurs de filtre ─────────────────────────────────────────────────────

_FILTER_OPERATORS: dict[str, str] = {
    "gte": ">=",
    "lte": "<=",
    "gt": ">",
    "lt": "<",
    "like": "LIKE",
    "in": "IN",
    "isnull": "IS_NULL",
}


class Repository(Generic[T]):
    """Repository CRUD générique, paramétré par ``type[T: PersistableModel]``.

    Analogue au ``Model.objects`` (Manager) de Django.

    Usage::

        repo = Repository(connection, Agent)
        agent = repo.create(Agent(name="bot", provider_id="p1", ...))
        found = repo.get(agent.id)
        results = repo.filter(role="researcher", is_active=True)
        repo.delete(agent.id)

    Args:
        connection: Connexion ``sqlite3.Connection`` ouverte.
        model_class: Classe ``PersistableModel`` gérée par ce repository.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        model_class: type[T],
        *,
        autocommit: bool = True,
    ) -> None:
        self._conn = connection
        self._model_class = model_class
        self._meta: TableMeta = model_class.__table_meta__
        self._table = self._meta.table_name
        self._pk = self._meta.pk_name
        self._columns = self._meta.column_names
        self._valid_columns = set(self._columns)
        self._autocommit = autocommit

    # ── Commit helper ────────────────────────────────────────────────

    def _commit(self) -> None:
        """Commit si autocommit est activé (pas en transaction explicite)."""
        if self._autocommit:
            self._conn.commit()

    # ── Create ───────────────────────────────────────────────────────

    def create(self, instance: T) -> T:
        """Insère une nouvelle ligne (INSERT).

        Args:
            instance: Modèle Pydantic à persister.

        Returns:
            Le modèle inchangé (confirmation de persistence).

        Raises:
            sqlite3.IntegrityError: Si la PK existe déjà.
        """
        row = ModelSerializer.to_row(instance)
        cols = list(row.keys())
        placeholders = ", ".join("?" for _ in cols)
        cols_sql = ", ".join(_q(c) for c in cols)
        values = list(row.values())

        sql = f"INSERT INTO {_q(self._table)} ({cols_sql}) VALUES ({placeholders})"
        self._conn.execute(sql, values)
        self._commit()
        return instance

    def create_or_update(self, instance: T) -> T:
        """Insère ou remplace (INSERT OR REPLACE).

        Correspond à un « upsert » — si la PK existe, la ligne est remplacée.

        Args:
            instance: Modèle Pydantic à persister.

        Returns:
            Le modèle inchangé.
        """
        row = ModelSerializer.to_row(instance)
        cols = list(row.keys())
        placeholders = ", ".join("?" for _ in cols)
        cols_sql = ", ".join(_q(c) for c in cols)
        values = list(row.values())

        sql = f"INSERT OR REPLACE INTO {_q(self._table)} ({cols_sql}) VALUES ({placeholders})"
        self._conn.execute(sql, values)
        self._commit()
        return instance

    # ── Read ─────────────────────────────────────────────────────────

    def get(self, pk: str) -> T | None:
        """Récupère un modèle par sa clé primaire.

        Args:
            pk: Valeur de la clé primaire.

        Returns:
            L'instance du modèle, ou ``None`` si non trouvée.
        """
        sql = f"SELECT * FROM {_q(self._table)} WHERE {_q(self._pk)} = ?"
        cursor = self._conn.execute(sql, (pk,))
        row = cursor.fetchone()
        if row is None:
            return None
        return ModelSerializer.from_row(self._model_class, row)

    def get_or_raise(self, pk: str) -> T:
        """Récupère un modèle par sa PK, lève ``LookupError`` si absent.

        Args:
            pk: Valeur de la clé primaire.

        Returns:
            L'instance du modèle.

        Raises:
            LookupError: Si aucune ligne ne correspond.
        """
        result = self.get(pk)
        if result is None:
            raise LookupError(
                f"{self._model_class.__name__} with {self._pk}={pk!r} not found "
                f"in table '{self._table}'"
            )
        return result

    def filter(
        self,
        *,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        **conditions: Any,
    ) -> list[T]:
        """Requête avec filtres dynamiques (style Django ``QuerySet.filter()``).

        Supporte les suffixes ``__gte``, ``__lte``, ``__gt``, ``__lt``,
        ``__like``, ``__in``, ``__isnull``.

        Args:
            order_by: Nom de colonne pour ORDER BY (préfixer par ``-`` pour DESC).
            limit: Nombre maximum de résultats.
            offset: Décalage (pagination).
            **conditions: Filtres ``field=value`` ou ``field__op=value``.

        Returns:
            Liste d'instances du modèle.

        Raises:
            ValueError: Si un nom de colonne n'existe pas dans la table.
        """
        where_parts, params = self._build_where(conditions)

        sql = f"SELECT * FROM {_q(self._table)}"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        if order_by is not None:
            sql += self._build_order_by(order_by)

        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        if offset:
            sql += f" OFFSET {int(offset)}"

        cursor = self._conn.execute(sql, params)
        return [
            ModelSerializer.from_row(self._model_class, row)
            for row in cursor.fetchall()
        ]

    def all(self, *, order_by: str | None = None) -> list[T]:
        """Retourne toutes les lignes de la table.

        Args:
            order_by: Nom de colonne pour ORDER BY (préfixer par ``-`` pour DESC).

        Returns:
            Liste de toutes les instances.
        """
        return self.filter(order_by=order_by)

    def count(self, **conditions: Any) -> int:
        """Compte les lignes correspondant aux filtres.

        Args:
            **conditions: Mêmes filtres que ``filter()``.

        Returns:
            Nombre de lignes.
        """
        where_parts, params = self._build_where(conditions)

        sql = f"SELECT COUNT(*) FROM {_q(self._table)}"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        cursor = self._conn.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else 0

    def exists(self, pk: str) -> bool:
        """Vérifie si une ligne existe pour la PK donnée.

        Args:
            pk: Valeur de la clé primaire.

        Returns:
            ``True`` si la ligne existe.
        """
        sql = f"SELECT 1 FROM {_q(self._table)} WHERE {_q(self._pk)} = ? LIMIT 1"
        cursor = self._conn.execute(sql, (pk,))
        return cursor.fetchone() is not None

    # ── Update ───────────────────────────────────────────────────────

    def update(self, instance: T) -> T:
        """Met à jour une ligne existante (UPDATE).

        Détecte automatiquement ``updated_at`` et le met à jour
        si le champ existe.

        Args:
            instance: Modèle Pydantic avec les nouvelles valeurs.

        Returns:
            Le modèle mis à jour.

        Raises:
            LookupError: Si la PK n'existe pas.
        """
        row = ModelSerializer.to_row(instance)
        pk_value = row.pop(self._pk)

        # Auto-update updated_at si le champ existe
        if "updated_at" in self._valid_columns:
            now = datetime.now(UTC).isoformat()
            row["updated_at"] = now

        if not row:
            return instance

        set_parts = [f"{_q(col)} = ?" for col in row]
        values = list(row.values())
        values.append(pk_value)

        sql = (
            f"UPDATE {_q(self._table)} SET {', '.join(set_parts)} "
            f"WHERE {_q(self._pk)} = ?"
        )
        cursor = self._conn.execute(sql, values)
        self._commit()

        if cursor.rowcount == 0:
            raise LookupError(
                f"{self._model_class.__name__} with {self._pk}={pk_value!r} "
                f"not found in table '{self._table}'"
            )

        return instance

    # ── Delete ───────────────────────────────────────────────────────

    def delete(self, pk: str) -> bool:
        """Supprime une ligne par sa PK.

        Args:
            pk: Valeur de la clé primaire.

        Returns:
            ``True`` si une ligne a été supprimée, ``False`` sinon.
        """
        sql = f"DELETE FROM {_q(self._table)} WHERE {_q(self._pk)} = ?"
        cursor = self._conn.execute(sql, (pk,))
        self._commit()
        return cursor.rowcount > 0

    def delete_where(self, **conditions: Any) -> int:
        """Supprime les lignes correspondant aux filtres.

        Args:
            **conditions: Mêmes filtres que ``filter()``.

        Returns:
            Nombre de lignes supprimées.
        """
        where_parts, params = self._build_where(conditions)

        sql = f"DELETE FROM {_q(self._table)}"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        cursor = self._conn.execute(sql, params)
        self._commit()
        return cursor.rowcount

    # ── Helpers internes ─────────────────────────────────────────────

    def _build_where(self, conditions: dict[str, Any]) -> tuple[list[str], list[Any]]:
        """Construit les clauses WHERE depuis les conditions kwargs.

        Supporte les opérateurs ``__gte``, ``__lte``, ``__gt``, ``__lt``,
        ``__like``, ``__in``, ``__isnull``.

        Returns:
            Tuple ``(where_parts, params)`` avec des ``?`` positionnels.

        Raises:
            ValueError: Si un nom de colonne est invalide.
        """
        where_parts: list[str] = []
        params: list[Any] = []

        for key, value in conditions.items():
            col_name, operator = self._parse_filter_key(key)
            self._validate_column(col_name)

            if operator == "IS_NULL":
                if value:
                    where_parts.append(f"{_q(col_name)} IS NULL")
                else:
                    where_parts.append(f"{_q(col_name)} IS NOT NULL")
            elif operator == "IN":
                if not isinstance(value, (list, tuple, set)):
                    raise ValueError(
                        f"Filter '{key}' expects a list/tuple/set, got {type(value).__name__}"
                    )
                values_list = list(value)
                placeholders = ", ".join("?" for _ in values_list)
                where_parts.append(f"{_q(col_name)} IN ({placeholders})")
                # Serialize enum values
                params.extend(
                    v.value if hasattr(v, "value") and isinstance(v, str) else v
                    for v in values_list
                )
            else:
                sql_op = operator or "="
                where_parts.append(f"{_q(col_name)} {sql_op} ?")
                # Serialize enum values and booleans
                if isinstance(value, bool):
                    params.append(1 if value else 0)
                elif hasattr(value, "value") and isinstance(value, str):
                    params.append(value.value)
                else:
                    params.append(value)

        return where_parts, params

    def _parse_filter_key(self, key: str) -> tuple[str, str | None]:
        """Parse un filtre ``field__op`` → ``(field, sql_operator)``.

        Returns:
            Tuple ``(column_name, sql_operator_or_None)``.
        """
        for suffix, sql_op in _FILTER_OPERATORS.items():
            dunder = f"__{suffix}"
            if key.endswith(dunder):
                col_name = key[: -len(dunder)]
                return col_name, sql_op

        # Pas d'opérateur → égalité simple
        return key, None

    def _validate_column(self, col_name: str) -> None:
        """Vérifie qu'un nom de colonne est valide (anti-injection).

        Raises:
            ValueError: Si le nom n'est pas dans la table.
        """
        if col_name not in self._valid_columns:
            raise ValueError(
                f"Column '{col_name}' does not exist in table '{self._table}'. "
                f"Valid columns: {sorted(self._valid_columns)}"
            )

    def _build_order_by(self, order_by: str) -> str:
        """Construit la clause ORDER BY.

        Préfixer par ``-`` pour DESC (ex: ``-created_at``).
        """
        if order_by.startswith("-"):
            col = order_by[1:]
            direction = "DESC"
        else:
            col = order_by
            direction = "ASC"

        self._validate_column(col)
        return f" ORDER BY {_q(col)} {direction}"


__all__ = [
    "Repository",
]
