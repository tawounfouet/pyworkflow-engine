"""
Abstraction Data Warehouse — DuckDB ou PostgreSQL.

Fournit une interface unifiée pour interagir avec le Data Warehouse,
indépendamment du backend (DuckDB en dev, PostgreSQL en prod).

Le backend est choisi via les variables d'environnement :
- ``WAREHOUSE_BACKEND`` : ``duckdb`` (défaut) ou ``postgres``
- ``WAREHOUSE_CONN`` : connection string ou chemin fichier

Examples:
    >>> wh = Warehouse.from_env()
    >>> wh.upsert("staging.stg_payments", data, key="payment_id")
    42
    >>> count = wh.query_scalar("SELECT COUNT(*) FROM staging.stg_payments")
"""

from __future__ import annotations

import os
from typing import Any


class Warehouse:
    """Interface unifiée pour le Data Warehouse.

    En développement, utilise DuckDB (fichier ``data/warehouse/warehouse.duckdb``).
    En production, utilise PostgreSQL via ``WAREHOUSE_CONN``.
    """

    def __init__(self, backend: str, connection_string: str) -> None:
        self._backend = backend
        self._conn_str = connection_string
        self._conn: Any = None

    @classmethod
    def from_env(cls) -> Warehouse:
        """Factory depuis variables d'environnement.

        Lit ``WAREHOUSE_BACKEND`` (défaut : ``duckdb``)
        et ``WAREHOUSE_CONN`` (défaut : ``./data/warehouse/warehouse.duckdb``).
        """
        backend = os.environ.get("WAREHOUSE_BACKEND", "duckdb")
        conn_str = os.environ.get("WAREHOUSE_CONN", "./data/warehouse/warehouse.duckdb")
        return cls(backend=backend, connection_string=conn_str)

    # ── Connexion ────────────────────────────────────────────────────

    def _get_connection(self) -> Any:
        """Lazy-connect au backend configuré."""
        if self._conn is None:
            if self._backend == "duckdb":
                import duckdb  # noqa: PLC0415

                self._conn = duckdb.connect(self._conn_str)
            elif self._backend == "postgres":
                import psycopg2  # noqa: PLC0415

                self._conn = psycopg2.connect(self._conn_str)
            else:
                msg = f"Unknown warehouse backend: {self._backend!r}"
                raise ValueError(msg)
        return self._conn

    # ── Écriture ─────────────────────────────────────────────────────

    def upsert(
        self,
        table: str,
        data: list[dict[str, Any]],
        key: str | list[str],
    ) -> int:
        """Upsert générique — insère ou met à jour selon la clé (simple ou composite).

        Args:
            table: Nom de la table (ex: ``staging.stg_payments``).
            data:  Liste de dictionnaires à upsert.
            key:   Colonne clé simple (``"id"``) ou liste de colonnes pour
                   une clé composite (``["activity_id", "stream_type"]``).

        Returns:
            Nombre de lignes traitées.
        """
        if not data:
            return 0

        keys: list[str] = [key] if isinstance(key, str) else list(key)
        conn = self._get_connection()

        if self._backend == "duckdb":
            # DuckDB : CREATE IF NOT EXISTS + DELETE by key(s) + INSERT
            columns = list(data[0].keys())
            col_defs = ", ".join(f'"{c}" VARCHAR' for c in columns)
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} ({col_defs})"
            )  # noqa: S608

            placeholders = ", ".join(["?"] * len(columns))
            col_names = ", ".join(f'"{c}"' for c in columns)

            # Clause WHERE pour clé simple ou composite
            where_clause = " AND ".join(f'"{k}" = ?' for k in keys)

            for row in data:
                key_values = [row.get(k) for k in keys]
                conn.execute(
                    f"DELETE FROM {table} WHERE {where_clause}",  # noqa: S608
                    key_values,
                )
                values = [row.get(c) for c in columns]
                conn.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",  # noqa: S608
                    values,
                )
        else:
            # Postgres : à implémenter avec INSERT ... ON CONFLICT
            raise NotImplementedError("PostgreSQL upsert not yet implemented")

        return len(data)

    # ── Lecture ───────────────────────────────────────────────────────

    def query_scalar(self, sql: str, params: tuple[Any, ...] | None = None) -> Any:
        """Exécute une requête SQL retournant une valeur scalaire."""
        conn = self._get_connection()
        result = conn.execute(sql, params or ()).fetchone()
        return result[0] if result else None

    def query(
        self, sql: str, params: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Exécute une requête SQL retournant des lignes."""
        conn = self._get_connection()
        cursor = conn.execute(sql, params or ())
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ── Gestion ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Ferme la connexion au backend."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Warehouse:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
