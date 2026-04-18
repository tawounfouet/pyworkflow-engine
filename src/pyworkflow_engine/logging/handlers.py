"""
Handlers avancés — stdlib uniquement.

Handlers supplémentaires pour des cas d'usage avancés,
tous basés sur la stdlib (sqlite3, logging.handlers).

- ``RepositoryLogHandler`` : persiste les logs via Repository[WorkflowLog] (ADR-018)
- ``SQLiteLogHandler`` : **DEPRECATED** — persiste les logs dans une base SQLite (sqlite3 stdlib)
- ``create_queue_handler`` : helper pour logging asynchrone via QueueHandler

Note : Pour un handler SQLAlchemy, voir ``adapters/sqlalchemy/log_models.py``.
       Pour un handler structlog, voir ``adapters/structlog/``.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import queue
import sqlite3
import threading
import warnings
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

    from pyworkflow_engine.adapters.storage.repository import Repository
    from pyworkflow_engine.models.logging.log_entry import WorkflowLog


class RepositoryLogHandler(logging.Handler):
    """Persiste les logs via ``Repository[WorkflowLog]`` (ADR-018, décision 4).

    Remplace ``SQLiteLogHandler`` en déléguant la persistence au pattern
    unifié ``PersistableModel`` + ``Repository[T]`` (ADR-017).

    Thread-safe grâce au lock hérité de ``logging.Handler``.

    Champs de corrélation (``correlation_id``, ``job_run_id``, ``step_run_id``,
    ``execution_id``, ``pipeline_run_id``, ``agent_id``) sont extraits
    automatiquement des extras du ``LogRecord`` si présents.

    Args:
        repository: ``Repository[WorkflowLog]`` pré-configuré.
        batch_size: Nombre de logs à accumuler avant un flush en batch.
            Si 1 (défaut), chaque log est écrit immédiatement.

    Examples:
        >>> from pyworkflow_engine.adapters.storage.unified import UnifiedStorage
        >>> storage = UnifiedStorage("logs.db")
        >>> storage.migrate()
        >>> handler = RepositoryLogHandler(storage.logs, batch_size=10)
        >>> logger = logging.getLogger("my_workflow")
        >>> logger.addHandler(handler)
        >>> logger.info("Step started", extra={"job_run_id": "run-123"})
        >>> handler.flush()
    """

    # Champs de corrélation reconnus dans les extras du LogRecord
    _CORRELATION_FIELDS: frozenset[str] = frozenset(
        {
            "correlation_id",
            "job_run_id",
            "step_run_id",
            "execution_id",
            "pipeline_run_id",
            "agent_id",
        }
    )

    def __init__(
        self,
        repository: Repository[WorkflowLog],
        *,
        batch_size: int = 1,
    ) -> None:
        super().__init__()
        self._repository = repository
        self._batch_size = max(1, batch_size)
        self._buffer: list[WorkflowLog] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """Convertit un ``LogRecord`` en ``WorkflowLog`` et le persiste."""
        try:
            from pyworkflow_engine.logging.formatters import _STANDARD_LOG_RECORD_KEYS
            from pyworkflow_engine.models.logging.log_entry import WorkflowLog

            # Séparer corrélation et extras arbitraires
            correlation: dict[str, Any] = {}
            extras: dict[str, Any] = {}

            for key, value in record.__dict__.items():
                if key in self._CORRELATION_FIELDS:
                    correlation[key] = str(value)
                elif key not in _STANDARD_LOG_RECORD_KEYS and not key.startswith("_"):
                    extras[key] = str(value)

            # Exception info
            exception_str: str | None = None
            if record.exc_info and record.exc_info[1] is not None:
                exception_str = (
                    self.format(record) if self.formatter else str(record.exc_info[1])
                )

            timestamp = datetime.fromtimestamp(record.created, tz=UTC)

            log_entry = WorkflowLog(
                id=str(uuid4()),
                timestamp=timestamp,
                level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
                module=record.module,
                func_name=record.funcName,
                line_no=record.lineno,
                exception=exception_str,
                extra=extras,
                **correlation,
            )

            with self._lock:
                self._buffer.append(log_entry)
                if len(self._buffer) >= self._batch_size:
                    self._flush_buffer()

        except Exception:
            self.handleError(record)

    def _flush_buffer(self) -> None:
        """Écrit le buffer en batch via le Repository."""
        if not self._buffer:
            return

        for entry in self._buffer:
            self._repository.create(entry)
        self._buffer.clear()

    def flush(self) -> None:
        """Force le flush du buffer."""
        with self._lock:
            self._flush_buffer()

    def close(self) -> None:
        """Flush final et fermeture."""
        self.flush()
        super().close()


class SQLiteLogHandler(logging.Handler):
    """Persiste les logs dans une base SQLite.

    .. deprecated:: 0.12.0
        Utilisez :class:`RepositoryLogHandler` avec ``Repository[WorkflowLog]``
        à la place. ``SQLiteLogHandler`` sera supprimé dans une version future.

    Utilise ``sqlite3`` de la stdlib — zero dépendance externe.
    Thread-safe grâce à un lock interne et ``check_same_thread=False``.

    La table ``workflow_logs`` est créée automatiquement si elle n'existe pas.

    Args:
        db_path: Chemin vers le fichier SQLite. ``:memory:`` pour en-mémoire.
        table_name: Nom de la table de logs.
        batch_size: Nombre de logs à accumuler avant un flush en batch.
            Si 1, chaque log est écrit immédiatement.

    Examples:
        >>> handler = SQLiteLogHandler("logs.db")
        >>> logger = logging.getLogger("test")
        >>> logger.addHandler(handler)
        >>> logger.warning("Something happened", extra={"job_id": "abc"})
    """

    def __init__(
        self,
        db_path: str | Path = "workflow_logs.db",
        table_name: str = "workflow_logs",
        batch_size: int = 1,
    ) -> None:
        warnings.warn(
            "SQLiteLogHandler is deprecated. "
            "Use RepositoryLogHandler with Repository[WorkflowLog] instead "
            "(see ADR-018, décision 4).",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__()
        self._db_path = str(db_path)
        self._table_name = table_name
        self._batch_size = max(1, batch_size)
        self._buffer: list[tuple[Any, ...]] = []
        self._lock = threading.Lock()

        # Connexion SQLite thread-safe
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self) -> None:
        """Crée la table de logs si elle n'existe pas."""
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                logger TEXT NOT NULL,
                message TEXT NOT NULL,
                extra TEXT,
                exception TEXT,
                module TEXT,
                func_name TEXT,
                line_no INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        # Index sur timestamp et level pour les requêtes courantes
        self._conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self._table_name}_timestamp
            ON {self._table_name} (timestamp)
        """
        )
        self._conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self._table_name}_level
            ON {self._table_name} (level)
        """
        )
        self._conn.commit()

    def emit(self, record: logging.LogRecord) -> None:
        """Écrit un log record dans SQLite."""
        try:
            # Extraire les extras
            extras: dict[str, Any] = {}
            from pyworkflow_engine.logging.formatters import _STANDARD_LOG_RECORD_KEYS

            for key, value in record.__dict__.items():
                if key not in _STANDARD_LOG_RECORD_KEYS and not key.startswith("_"):
                    extras[key] = str(value)

            # Exception info
            exception_str: str | None = None
            if record.exc_info and record.exc_info[1] is not None:
                exception_str = (
                    self.format(record) if self.formatter else str(record.exc_info[1])
                )

            timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()

            row = (
                timestamp,
                record.levelname,
                record.name,
                record.getMessage(),
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
        """Écrit le buffer en batch dans SQLite."""
        if not self._buffer:
            return

        self._conn.executemany(
            f"""
            INSERT INTO {self._table_name}
            (timestamp, level, logger, message, extra, exception, module, func_name, line_no)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._buffer,
        )
        self._conn.commit()
        self._buffer.clear()

    def flush(self) -> None:
        """Force le flush du buffer."""
        with self._lock:
            self._flush_buffer()

    def close(self) -> None:
        """Flush final et fermeture de la connexion."""
        self.flush()
        self._conn.close()
        super().close()

    def query_logs(
        self,
        level: str | None = None,
        logger_name: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Requête les logs stockés.

        Args:
            level: Filtrer par niveau (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            logger_name: Filtrer par nom de logger (supporte le LIKE avec %).
            since: Logs postérieurs à cette date.
            limit: Nombre max de résultats.

        Returns:
            Liste de dicts représentant les log entries.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if level is not None:
            conditions.append("level = ?")
            params.append(level.upper())
        if logger_name is not None:
            conditions.append("logger LIKE ?")
            params.append(f"%{logger_name}%")
        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(since.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        cursor = self._conn.execute(
            f"SELECT * FROM {self._table_name} {where} ORDER BY id DESC LIMIT ?",
            params,
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def create_queue_handler(
    *target_handlers: logging.Handler,
) -> tuple[logging.handlers.QueueHandler, logging.handlers.QueueListener]:
    """Crée un couple QueueHandler/QueueListener pour du logging async.

    Le QueueHandler est non-bloquant : les logs sont mis en queue
    et traités dans un thread séparé par le QueueListener.

    Args:
        *target_handlers: Handlers cibles qui recevront les logs
            depuis le thread du QueueListener.

    Returns:
        Tuple (queue_handler, queue_listener). Le listener doit être
        démarré avec ``listener.start()`` et arrêté avec ``listener.stop()``.

    Examples:
        >>> console = logging.StreamHandler()
        >>> db_handler = SQLiteLogHandler("logs.db")
        >>> q_handler, q_listener = create_queue_handler(console, db_handler)
        >>> q_listener.start()
        >>> logger = logging.getLogger("test")
        >>> logger.addHandler(q_handler)
        >>> # ... logs are processed asynchronously ...
        >>> q_listener.stop()
    """
    log_queue: queue.Queue[Any] = queue.Queue(-1)
    handler = logging.handlers.QueueHandler(log_queue)
    listener = logging.handlers.QueueListener(
        log_queue, *target_handlers, respect_handler_level=True
    )
    return handler, listener
