"""
Configuration structlog ↔ stdlib bridge.

Branche les processeurs structlog sur le système logging stdlib du core.
Ainsi, tous les ``logging.getLogger()`` du core bénéficient de structlog
sans que le core ne connaisse structlog.

Requires: pip install structlog
"""

from __future__ import annotations

import logging
from typing import Any


def configure_structlog(
    *,
    level: str = "INFO",
    json_output: bool = False,
    processors: list[Any] | None = None,
    context_class: type | None = None,
) -> None:
    """Configure structlog comme processeur des logs stdlib du core.

    Cette fonction branche structlog sur le ``logging`` stdlib :
    - Les logs émis via ``logging.getLogger("pyworkflow_engine.*")``
      sont interceptés et formatés par structlog.
    - Le core reste blissfully unaware de structlog.

    Args:
        level: Niveau de log minimum.
        json_output: Si True, output JSON. Sinon, output console coloré.
        processors: Liste custom de structlog processors. Si None, utilise
            les defaults sensibles (timestamper, level, contextvars, etc.).
        context_class: Classe de contexte structlog. Par défaut dict.

    Raises:
        ImportError: Si structlog n'est pas installé.

    Examples:
        >>> configure_structlog(level="DEBUG", json_output=True)
        >>> configure_structlog(processors=[
        ...     structlog.processors.add_log_level,
        ...     structlog.processors.TimeStamper(fmt="iso"),
        ...     structlog.dev.ConsoleRenderer(),
        ... ])
    """
    try:
        import structlog
    except ImportError as e:
        raise ImportError(
            "structlog is required for this adapter. "
            "Install with: pip install ias-workflow-engine[structlog]"
        ) from e

    # Processors par défaut
    if processors is None:
        shared_processors: list[Any] = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
        ]

        if json_output:
            shared_processors.append(structlog.processors.JSONRenderer())
        else:
            shared_processors.append(structlog.dev.ConsoleRenderer())

        processors = shared_processors

    # Configurer structlog pour wraper le logging stdlib
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=context_class or dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Formatter structlog pour les handlers stdlib existants
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *(
                [structlog.processors.JSONRenderer()]
                if json_output
                else [structlog.dev.ConsoleRenderer()]
            ),
        ],
    )

    # Appliquer le formatter structlog au logger racine du package
    root_logger = logging.getLogger("pyworkflow_engine")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remplacer les handlers existants par un handler avec formatter structlog
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Nettoyer les handlers non-NullHandler
    for existing in root_logger.handlers[:]:
        if not isinstance(existing, logging.NullHandler):
            root_logger.removeHandler(existing)

    root_logger.addHandler(handler)
