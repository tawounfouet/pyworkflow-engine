from typing import Any
from urllib.parse import urlparse

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import pymysql  # type: ignore
except ImportError:
    pymysql = None


@connector("database.mysql")
class MySQLConnector(BaseConnector):
    """MySQL Connector using pymysql."""

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> list[Any]:
        if pymysql is None:
            raise ImportError(
                "MySQL connector requires pymysql. Install with: pip install pyconnectors[mysql]"
            )

        # Accept a URL like mysql://user:password@host:3306/dbname
        url = (
            self.config.params.get("url")
            or self.config.params.get("database_url")
            or self.config.params.get("mysql_url")
        )

        if url:
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 3306
            user = parsed.username
            password = parsed.password
            # strip leading "/" from path to get the database name
            database = parsed.path.lstrip("/") or None
        else:
            host = self.config.params.get("host", "localhost")
            port = self.config.params.get("port", 3306)
            user = self.config.params.get("user")
            password = self.config.params.get("password")
            database = self.config.params.get("database")

        if not all([user, password, database]):
            raise ValueError(
                "Configuration missing connection details. "
                "Set 'url' (e.g. mysql://user:pass@host/db) or individual "
                "'user', 'password', and 'database' params."
            )

        with pymysql.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            cursorclass=pymysql.cursors.DictCursor,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return list(cur.fetchall())
