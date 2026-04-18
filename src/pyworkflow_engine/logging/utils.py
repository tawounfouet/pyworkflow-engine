"""
Utilitaires de logging — helpers stdlib pour le workflow engine.

Fournit des patterns de haut niveau au-dessus du stdlib logging :
- ``logged_operation`` : context manager pour tracer durée et succès/échec
- ``StepLogBridge`` : handler qui connecte le logging stdlib aux StepLog
- ``LoggingConfigBuilder`` : builder fluide pour construire une LoggingConfig
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

from pyworkflow_engine.logging.config import LoggingConfig


@contextmanager
def logged_operation(
    logger: logging.Logger,
    operation: str,
    **extra: Any,
) -> Generator[logging.Logger, None, None]:
    """Context manager pour tracer automatiquement une opération.

    Log le début, la durée et le résultat (succès ou échec) d'une opération.
    Utilise ``time.monotonic()`` pour une mesure de durée fiable.

    Args:
        logger: Logger stdlib à utiliser.
        operation: Nom/description de l'opération.
        **extra: Champs additionnels inclus dans chaque log entry.

    Yields:
        Le logger pour permettre des logs supplémentaires dans le bloc.

    Raises:
        Exception: Re-raise toute exception après l'avoir loggée.

    Examples:
        >>> from pyworkflow_engine.logging import get_logger
        >>> logger = get_logger("my_workflow")
        >>> with logged_operation(logger, "data processing", job_id="abc"):
        ...     process_data()
        # Logs: "Starting: data processing", puis "Completed: data processing (1.23s)"

        >>> with logged_operation(logger, "risky op") as log:
        ...     log.info("intermediate step")
        ...     do_risky_thing()
        # Si exception: "Failed: risky op (0.45s)" avec exc_info
    """
    logger.info("Starting: %s", operation, extra=extra)
    t0 = time.monotonic()
    try:
        yield logger
        elapsed = time.monotonic() - t0
        logger.info("Completed: %s (%.2fs)", operation, elapsed, extra=extra)
    except Exception:
        elapsed = time.monotonic() - t0
        logger.error(
            "Failed: %s (%.2fs)", operation, elapsed, extra=extra, exc_info=True
        )
        raise


class StepLogBridge(logging.Handler):
    """Handler qui redirige les logs stdlib vers StepRun.add_log().

    Connecte le dual-logging du projet : les logs émis via le stdlib
    ``logging`` sont automatiquement capturés dans les ``StepLog``
    du ``StepRun`` correspondant, et donc persistés avec les données
    d'exécution du workflow.

    Thread-safe : hérite du lock de ``logging.Handler``.

    Args:
        step_run: Instance StepRun cible pour les logs.
        source: Préfixe source pour les StepLog (défaut: "logging").

    Examples:
        >>> from pyworkflow_engine.models.workflow.run import StepRun
        >>> step_run = StepRun(step_name="process_data", job_run_id="job-1")
        >>> bridge = StepLogBridge(step_run)
        >>> logger = logging.getLogger("my_step")
        >>> logger.addHandler(bridge)
        >>> logger.info("Processing row 42")
        >>> # → step_run.logs contient le StepLog correspondant
    """

    def __init__(self, step_run: Any, source: str = "logging") -> None:
        super().__init__()
        self._step_run = step_run
        self._source = source

    def emit(self, record: logging.LogRecord) -> None:
        """Convertit un LogRecord stdlib en StepLog et l'ajoute au StepRun."""
        try:
            # Extraire les données extra du record
            from pyworkflow_engine.logging.formatters import _STANDARD_LOG_RECORD_KEYS

            data: dict[str, Any] = {}
            for key, value in record.__dict__.items():
                if key not in _STANDARD_LOG_RECORD_KEYS and not key.startswith("_"):
                    data[key] = value

            self._step_run.add_log(
                level=record.levelname,
                message=record.getMessage(),
                data=data if data else None,
            )
        except Exception:
            self.handleError(record)


class LoggingConfigBuilder:
    """Builder fluide pour construire une LoggingConfig.

    Offre une API chaînable comme alternative au constructeur direct
    de ``LoggingConfig``, inspirée du ``LoggerBuilder`` de database_logger.

    Examples:
        >>> config = (LoggingConfigBuilder()
        ...     .level("DEBUG")
        ...     .json_output()
        ...     .log_file("workflow.log")
        ...     .extra_fields(env="prod", service="etl")
        ...     .build())
        >>> configure_logging(config)

        >>> config = (LoggingConfigBuilder()
        ...     .level("INFO")
        ...     .with_queue()
        ...     .log_file("app.log", max_bytes=50*1024*1024, backup_count=10)
        ...     .build())
    """

    def __init__(self) -> None:
        self._kwargs: dict[str, Any] = {}

    def level(self, level: str) -> LoggingConfigBuilder:
        """Définit le niveau de log minimum.

        Args:
            level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        """
        self._kwargs["level"] = level
        return self

    def json_output(self, enabled: bool = True) -> LoggingConfigBuilder:
        """Active/désactive la sortie JSON structurée.

        Args:
            enabled: True pour JSON, False pour format lisible humain.
        """
        self._kwargs["json_output"] = enabled
        return self

    def log_file(
        self,
        path: str | Path,
        *,
        max_bytes: int | None = None,
        backup_count: int | None = None,
    ) -> LoggingConfigBuilder:
        """Configure la sortie fichier avec rotation.

        Args:
            path: Chemin du fichier de log.
            max_bytes: Taille max avant rotation.
            backup_count: Nombre de fichiers de backup.
        """
        self._kwargs["log_file"] = str(path)
        if max_bytes is not None:
            self._kwargs["log_file_max_bytes"] = max_bytes
        if backup_count is not None:
            self._kwargs["log_file_backup_count"] = backup_count
        return self

    def with_queue(self, enabled: bool = True) -> LoggingConfigBuilder:
        """Active le logging asynchrone via QueueHandler.

        Args:
            enabled: True pour activer le queue-based async logging.
        """
        self._kwargs["enable_queue"] = enabled
        return self

    def extra_fields(self, **fields: Any) -> LoggingConfigBuilder:
        """Ajoute des champs additionnels à chaque log entry.

        Args:
            **fields: Paires clé-valeur incluses dans tous les logs.
        """
        existing = self._kwargs.get("extra_fields", {})
        existing.update(fields)
        self._kwargs["extra_fields"] = existing
        return self

    def propagate(self, enabled: bool = True) -> LoggingConfigBuilder:
        """Configure la propagation vers le logger parent.

        Args:
            enabled: True pour propager au logger parent.
        """
        self._kwargs["propagate"] = enabled
        return self

    def logger_name(self, name: str) -> LoggingConfigBuilder:
        """Définit le nom racine du logger.

        Args:
            name: Nom du logger racine.
        """
        self._kwargs["logger_name"] = name
        return self

    def build(self) -> LoggingConfig:
        """Construit la LoggingConfig immuable.

        Returns:
            Instance LoggingConfig avec les paramètres configurés.
        """
        return LoggingConfig(**self._kwargs)
