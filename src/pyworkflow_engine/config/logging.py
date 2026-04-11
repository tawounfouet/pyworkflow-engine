"""
LoggingConfig — paramètres de logging du moteur de workflow.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
VALID_FORMATS = ("text", "json")


@dataclass(frozen=True)
class LoggingConfig:
    """Paramètres de logging pour ``WorkflowEngine``.

    Quand ``WorkflowConfig`` est passé à ``WorkflowEngine``, ce config
    est appliqué automatiquement au démarrage.

    Args:
        level: Niveau de log minimum. Défaut : ``"INFO"``.
        format: Format de sortie console. ``"text"`` (lisible) ou ``"json"``
            (structuré, compatible ELK / Datadog).
        log_dir: Dossier pour les fichiers de log rotatifs. ``None`` = pas
            de fichier. Le fichier sera ``{log_dir}/pyworkflow.log``.
        log_file_max_mb: Taille max d'un fichier de log avant rotation (Mo).
        log_file_backup_count: Nombre de fichiers de backup conservés.
        log_to_db: Si ``True``, persiste les logs dans la table
            ``workflow_logs`` de la DB configurée dans ``StorageConfig``.
            Ignoré si ``StorageConfig.db_path`` est ``None``.

    Examples:
        >>> cfg = LoggingConfig(level="DEBUG", format="json")
        >>> cfg.level
        'DEBUG'

        >>> # Logging complet : console + fichier + SQLite
        >>> full = LoggingConfig(
        ...     level="DEBUG",
        ...     log_dir="logs",
        ...     log_to_db=True,
        ... )
        >>> full.log_to_db
        True

        >>> LoggingConfig(level="VERBOSE")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: LoggingConfig.level must be one of ...
    """

    level: str = "INFO"
    format: str = "text"
    log_dir: str | None = None
    log_file_max_mb: int = 10
    log_file_backup_count: int = 5
    log_to_db: bool = False

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
        if self.log_file_max_mb < 1:
            raise ValueError("LoggingConfig.log_file_max_mb must be >= 1")
        if self.log_file_backup_count < 0:
            raise ValueError("LoggingConfig.log_file_backup_count must be >= 0")
