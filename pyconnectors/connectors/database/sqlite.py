import sqlite3
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("database.sqlite")
class SQLiteConnector(BaseConnector):
    """SQLite Connector using stdlib sqlite3."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        database = self.config.params.get("database", ":memory:")
        # Keep a single connection so that :memory: databases persist across calls
        self._conn = sqlite3.connect(database, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> list[Any]:
        cur = self._conn.cursor()
        cur.execute(query, params or ())
        self._conn.commit()

        try:
            # Convert rows to dicts for easier consumption
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.ProgrammingError:
            # e.g., for INSERT/UPDATE without returning rows
            return []

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
