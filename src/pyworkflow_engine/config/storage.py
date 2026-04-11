"""
StorageConfig — configuration du backend de persistence.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_BACKENDS = ("sqlite", "memory", "json")


@dataclass(frozen=True)
class StorageConfig:
    """Configuration du backend de persistence pour ``WorkflowEngine``.

    Quand ``db_path`` est fourni dans ``WorkflowConfig``, le moteur crée
    automatiquement un ``SQLiteStorage`` sans configuration manuelle.

    Args:
        db_path: Chemin vers le fichier SQLite. ``None`` = pas de persistence
            (exécution en mémoire, aucun run ni job persisté).
        backend: Type de backend. Seul ``"sqlite"`` est auto-provisionné ;
            pour ``"memory"`` ou ``"json"``, fournir le backend manuellement.

    Examples:
        >>> cfg = StorageConfig(db_path="workflow.db")
        >>> cfg.db_path
        'workflow.db'

        >>> cfg = StorageConfig()  # sans persistence
        >>> cfg.db_path is None
        True
    """

    db_path: str | None = None
    backend: str = "sqlite"

    def __post_init__(self) -> None:
        if self.backend not in VALID_BACKENDS:
            raise ValueError(
                f"StorageConfig.backend must be one of {VALID_BACKENDS}, "
                f"got '{self.backend}'"
            )
