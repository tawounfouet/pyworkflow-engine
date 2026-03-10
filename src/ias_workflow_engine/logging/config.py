"""
Configuration du logging — dataclasses pures, zero dépendance.

Utilise des dataclasses stdlib au lieu de Pydantic pour rester
dans le contrat zero-dépendance du core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LoggingConfig:
    """Configuration immuable pour le système de logging.

    Tous les champs ont des défauts sensibles pour une utilisation
    immédiate sans configuration.

    Attributes:
        level: Niveau de log minimum (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: Si True, les logs console sont formatés en JSON structuré.
        log_file: Chemin du fichier de log. None = pas de fichier.
        log_file_max_bytes: Taille max d'un fichier de log avant rotation.
        log_file_backup_count: Nombre de fichiers de backup à conserver.
        enable_queue: Si True, utilise QueueHandler pour un logging asynchrone non-bloquant.
        extra_fields: Champs additionnels inclus dans chaque log entry.
        propagate: Si True, propage les logs au logger parent.
        logger_name: Nom racine du logger pour le package.
    """

    level: str = "INFO"
    json_output: bool = False
    log_file: str | None = None
    log_file_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    log_file_backup_count: int = 5
    enable_queue: bool = False
    extra_fields: dict[str, Any] = field(default_factory=dict)
    propagate: bool = False
    logger_name: str = "ias_workflow_engine"

    def with_overrides(self, **kwargs: Any) -> LoggingConfig:
        """Crée une nouvelle config avec des valeurs surchargées.

        Returns:
            Nouvelle instance LoggingConfig avec les overrides appliqués.
        """
        from dataclasses import asdict

        current = asdict(self)
        current.update(kwargs)
        return LoggingConfig(**current)
