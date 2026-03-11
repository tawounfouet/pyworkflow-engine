"""
IAS Workflow Engine — Module Logging.

Architecture en 3 couches respectant le principe zero-dépendance :

    Couche 1 (core)    : stdlib logging uniquement → get_logger(), JSON formatter
    Couche 2 (contrib) : handlers avancés stdlib → QueueHandler, SQLite, fichier rotatif
    Couche 3 (adapter) : structlog opt-in → pip install ias-workflow-engine[structlog]

Usage basique (zero dépendance) :

    from pyworkflow_engine.logging import get_logger

    logger = get_logger("my_workflow")
    logger.info("Workflow started", extra={"job_id": "abc-123"})

Usage avancé avec configuration :

    from pyworkflow_engine.logging import configure_logging, LoggingConfig

    configure_logging(LoggingConfig(
        level="DEBUG",
        json_output=True,
        log_file="workflows.log",
    ))
"""

from .logger import get_logger, configure_logging, shutdown_logging
from .config import LoggingConfig
from .utils import logged_operation, StepLogBridge, LoggingConfigBuilder

__all__ = [
    "get_logger",
    "configure_logging",
    "shutdown_logging",
    "LoggingConfig",
    "logged_operation",
    "StepLogBridge",
    "LoggingConfigBuilder",
]
