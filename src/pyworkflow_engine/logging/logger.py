"""
Logger principal — stdlib logging uniquement, zero dépendance.

Suit les best practices pour les bibliothèques Python (PEP 282) :
- NullHandler par défaut → la lib est silencieuse sauf configuration explicite
- Namespace hiérarchique → ``pyworkflow_engine.core.engine``
- Compatible structlog si installé (voir adapters/structlog/)

Design :
    Le core utilise ``logging.getLogger(__name__)`` partout.
    L'utilisateur final configure le logging à son niveau (application).
    On fournit ``configure_logging()`` comme helper optionnel.
"""

from __future__ import annotations

import logging
import logging.handlers
import queue
from typing import Any

from .config import LoggingConfig
from .formatters import StructuredFormatter, JSONFormatter

# ── Namespace racine du package ──────────────────────────────────────────────
_ROOT_LOGGER_NAME = "pyworkflow_engine"
_root_logger = logging.getLogger(_ROOT_LOGGER_NAME)

# PEP 282 best practice : NullHandler par défaut pour les libraries
_root_logger.addHandler(logging.NullHandler())

# État global de configuration (évite les reconfigurations multiples)
_configured = False
_queue_listener: logging.handlers.QueueListener | None = None


def get_logger(name: str | None = None) -> logging.Logger:
    """Obtient un logger dans le namespace ``pyworkflow_engine``.

    Args:
        name: Sous-namespace du logger. Si None, retourne le logger racine.
              Exemples : ``"core.engine"``, ``"executors.thread"``.

    Returns:
        Logger stdlib configuré dans le bon namespace.

    Examples:
        >>> logger = get_logger("core.engine")
        >>> logger.name
        'pyworkflow_engine.core.engine'

        >>> logger = get_logger()
        >>> logger.name
        'pyworkflow_engine'
    """
    if name is None:
        return _root_logger
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")


def configure_logging(config: LoggingConfig | None = None) -> None:
    """Configure le système de logging pour l'application.

    Cette fonction est idempotente : un second appel reconfigure
    proprement en nettoyant les handlers précédents.

    Args:
        config: Configuration de logging. Si None, utilise les défauts.

    Examples:
        >>> configure_logging(LoggingConfig(level="DEBUG", json_output=True))
        >>> configure_logging(LoggingConfig(log_file="app.log", enable_queue=True))
    """
    global _configured, _queue_listener

    if config is None:
        config = LoggingConfig()

    # Nettoyer la configuration précédente
    _cleanup()

    # Niveau de log
    _root_logger.setLevel(getattr(logging, config.level.upper(), logging.INFO))
    _root_logger.propagate = config.propagate

    # Construire les handlers cibles
    target_handlers: list[logging.Handler] = []

    # ── Console handler ──────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    if config.json_output:
        console_handler.setFormatter(JSONFormatter(extra_fields=config.extra_fields))
    else:
        console_handler.setFormatter(
            StructuredFormatter(extra_fields=config.extra_fields)
        )
    target_handlers.append(console_handler)

    # ── File handler (rotatif) ───────────────────────────────────────────
    if config.log_file is not None:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=config.log_file,
            maxBytes=config.log_file_max_bytes,
            backupCount=config.log_file_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter(extra_fields=config.extra_fields))
        target_handlers.append(file_handler)

    # ── Queue handler (async non-bloquant) ───────────────────────────────
    if config.enable_queue:
        log_queue: queue.Queue[Any] = queue.Queue(-1)  # unbounded
        queue_handler = logging.handlers.QueueHandler(log_queue)
        _root_logger.addHandler(queue_handler)

        _queue_listener = logging.handlers.QueueListener(
            log_queue, *target_handlers, respect_handler_level=True
        )
        _queue_listener.start()
    else:
        for handler in target_handlers:
            _root_logger.addHandler(handler)

    _configured = True


def _cleanup() -> None:
    """Nettoie tous les handlers existants (sauf NullHandler)."""
    global _queue_listener, _configured

    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None

    for handler in _root_logger.handlers[:]:
        if not isinstance(handler, logging.NullHandler):
            _root_logger.removeHandler(handler)
            handler.close()

    _configured = False


def shutdown_logging() -> None:
    """Arrête proprement le système de logging.

    Appeler en fin de programme pour flusher les queues et fermer les fichiers.
    """
    _cleanup()
