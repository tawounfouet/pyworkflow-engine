"""
LoggingConfig — paramètres de logging du moteur de workflow.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
VALID_FORMATS = ("text", "json")


@dataclass(frozen=True)
class LoggingConfig:
    """Paramètres de logging pour ``pyworkflow_engine``.

    Args:
        level: Niveau de log. L'un de ``DEBUG``, ``INFO``, ``WARNING``,
            ``ERROR``, ``CRITICAL``. Défaut : ``INFO``.
        format: Format de sortie. ``"text"`` pour un format lisible humain,
            ``"json"`` pour une sortie structurée compatible avec les agrégateurs
            de logs (ELK, Datadog, Cloud Logging…).

    Examples:
        >>> cfg = LoggingConfig(level="DEBUG", format="json")
        >>> cfg.level
        'DEBUG'
        >>> LoggingConfig(level="VERBOSE")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: LoggingConfig.level must be one of ...
    """

    level: str = "INFO"
    format: str = "text"

    def __post_init__(self) -> None:
        if self.level not in VALID_LEVELS:
            raise ValueError(
                f"LoggingConfig.level must be one of {VALID_LEVELS}, "
                f"got '{self.level}'"
            )
        if self.format not in VALID_FORMATS:
            raise ValueError(
                f"LoggingConfig.format must be one of {VALID_FORMATS}, "
                f"got '{self.format}'"
            )
