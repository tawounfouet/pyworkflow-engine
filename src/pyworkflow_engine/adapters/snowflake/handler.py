"""
Snowflake logging handler — ``logging.Handler`` stdlib pour Snowflake.

Persiste les logs dans une table Snowflake avec batching thread-safe.
Utilise une factory de connexion injectable pour le découplage.

Requires: pip install snowflake-connector-python
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class SnowflakeLogHandler(logging.Handler):
    """Persiste les logs dans une table Snowflake.

    Handler ``logging.Handler`` standard qui accumule les logs en batch
    et les écrit dans Snowflake. Thread-safe grâce à un lock interne.

    La table est créée automatiquement au premier log si elle n'existe pas.

    Args:
        connection_factory: Callable qui retourne une connexion Snowflake.
            Doit retourner un objet avec ``.cursor()`` et ``.is_closed()``.
        database: Nom de la base Snowflake.
        schema: Nom du schéma Snowflake.
        table: Nom de la table de logs.
        batch_size: Nombre de logs avant un flush automatique.
            Si 1, chaque log est écrit immédiatement.

    Raises:
        ImportError: Si ``snowflake-connector-python`` n'est pas installé
            (au moment du premier flush).

    Examples:
        >>> def my_connection():
        ...     import snowflake.connector
        ...     return snowflake.connector.connect(...)
        >>>
        >>> handler = SnowflakeLogHandler(
        ...     connection_factory=my_connection,
        ...     database="MONITORING",
        ...     schema="LOGS",
        ...     table="PYTHON_LOGS",
        ... )
        >>> logger = logging.getLogger("pyworkflow_engine")
        >>> logger.addHandler(handler)
        >>> logger.info("Workflow started", extra={"job_id": "abc-123"})
    """

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        database: str,
        schema: str,
        table: str = "WORKFLOW_LOGS",
        batch_size: int = 10,
    ) -> None:
        super().__init__()
        self._connection_factory = connection_factory
        self._database = database
        self._schema = schema
        self._table = table
        self._batch_size = max(1, batch_size)
        self._buffer: list[tuple[Any, ...]] = []
        self._lock = threading.Lock()
        self._connection: Any = None
        self._table_checked = False

    @property
    def _fqn(self) -> str:
        """Fully qualified table name."""
        return f"{self._database}.{self._schema}.{self._table}"

    def _get_connection(self) -> Any:
        """Obtient ou recrée la connexion Snowflake."""
        if self._connection is None or self._connection.is_closed():
            self._connection = self._connection_factory()
        return self._connection

    def _ensure_table(self) -> None:
        """Crée la table de logs si elle n'existe pas."""
        if self._table_checked:
            return

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._fqn} (
                    ID NUMBER IDENTITY(1,1) PRIMARY KEY,
                    TIMESTAMP TIMESTAMP_NTZ NOT NULL,
                    LEVEL VARCHAR(20) NOT NULL,
                    LOGGER VARCHAR(200),
                    MESSAGE VARCHAR(4000),
                    EXTRA VARIANT,
                    EXCEPTION VARCHAR(4000),
                    MODULE VARCHAR(200),
                    FUNC_NAME VARCHAR(200),
                    LINE_NO INTEGER,
                    CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
                )
                """
            )
            cursor.close()
            self._table_checked = True
        except Exception:
            self.handleError(
                logging.LogRecord(
                    name="snowflake",
                    level=logging.ERROR,
                    pathname="",
                    lineno=0,
                    msg="Table creation failed",
                    args=(),
                    exc_info=None,
                )
            )

    def emit(self, record: logging.LogRecord) -> None:
        """Accumule un log record dans le buffer et flush si nécessaire."""
        try:
            self._ensure_table()

            # Extraire les extras
            from pyworkflow_engine.logging.formatters import _STANDARD_LOG_RECORD_KEYS

            extras: dict[str, Any] = {}
            for key, value in record.__dict__.items():
                if key not in _STANDARD_LOG_RECORD_KEYS and not key.startswith("_"):
                    extras[key] = str(value)

            # Exception
            exception_str: str | None = None
            if record.exc_info and record.exc_info[1] is not None:
                exception_str = str(record.exc_info[1])

            timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()

            row = (
                timestamp,
                record.levelname,
                record.name,
                record.getMessage()[:4000],
                json.dumps(extras, default=str) if extras else None,
                exception_str,
                record.module,
                record.funcName,
                record.lineno,
            )

            with self._lock:
                self._buffer.append(row)
                if len(self._buffer) >= self._batch_size:
                    self._flush_buffer()

        except Exception:
            self.handleError(record)

    def _flush_buffer(self) -> None:
        """Écrit le buffer en batch dans Snowflake."""
        if not self._buffer:
            return

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.executemany(
                f"""
                INSERT INTO {self._fqn}
                (TIMESTAMP, LEVEL, LOGGER, MESSAGE, EXTRA, EXCEPTION,
                 MODULE, FUNC_NAME, LINE_NO)
                VALUES (%s, %s, %s, %s, PARSE_JSON(%s), %s, %s, %s, %s)
                """,
                self._buffer,
            )
            cursor.close()
            self._buffer.clear()
        except Exception:
            # En cas d'erreur, garder le buffer pour retry
            # mais limiter sa taille pour éviter une fuite mémoire
            if len(self._buffer) > self._batch_size * 10:
                self._buffer = self._buffer[-self._batch_size :]
            self.handleError(
                logging.LogRecord(
                    name="snowflake",
                    level=logging.ERROR,
                    pathname="",
                    lineno=0,
                    msg="Snowflake flush failed",
                    args=(),
                    exc_info=None,
                )
            )

    def flush(self) -> None:
        """Force le flush du buffer vers Snowflake."""
        with self._lock:
            self._flush_buffer()

    def close(self) -> None:
        """Flush final et fermeture de la connexion."""
        self.flush()
        if self._connection is not None:
            try:
                if not self._connection.is_closed():
                    self._connection.close()
            except Exception:
                pass
        super().close()
