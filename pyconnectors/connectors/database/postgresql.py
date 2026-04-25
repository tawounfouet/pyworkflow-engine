from typing import Any
from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import psycopg
except ImportError:
    psycopg = None


@connector("database.postgresql")
class PostgreSQLConnector(BaseConnector):
    """PostgreSQL Connector using psycopg."""

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> list[Any]:
        if psycopg is None:
            raise ImportError(
                "PostgreSQL connector requires psycopg. Install with: pip install pyconnectors[postgresql]"
            )

        # Accept DATABASE_URL (PaaS standard) as an alias for dsn
        dsn = (
            self.config.params.get("dsn")
            or self.config.params.get("url")
            or self.config.params.get("database_url")
        )
        if not dsn:
            raise ValueError(
                "Configuration missing database URL. "
                "Set 'dsn', 'url', or 'database_url' in params, "
                "or set the DATABASE_URL environment variable."
            )

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                try:
                    return list(cur.fetchall())
                except psycopg.ProgrammingError:
                    # e.g., for INSERT/UPDATE without RETURNING
                    return []
