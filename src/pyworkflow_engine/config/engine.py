"""
EngineConfig — paramètres d'exécution du moteur de workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta


@dataclass(frozen=True)
class EngineConfig:
    """Paramètres d'exécution du ``WorkflowRunner``.

    Args:
        max_retries: Nombre maximum de tentatives par step (0 = pas de retry).
            Chaque ``Step`` peut surcharger cette valeur via ``step.retry_count``.
        retry_delay_seconds: Délai entre deux tentatives, en secondes.
        default_timeout_seconds: Timeout global par step (``None`` = pas de limite).
        parallel: Si ``True``, les steps sans dépendances mutuelles s'exécutent
            en parallèle via ``concurrent.futures.ThreadPoolExecutor``.
        max_workers: Nombre maximum de threads par groupe parallèle.
            Ignoré si ``parallel=False``. ``None`` = valeur par défaut du système.

    Examples:
        >>> cfg = EngineConfig(parallel=True, max_workers=8)
        >>> cfg.parallel
        True
        >>> cfg = EngineConfig(max_retries=3, retry_delay_seconds=2.0)
    """

    max_retries: int = 0
    retry_delay_seconds: float = 1.0
    default_timeout_seconds: float | None = None
    parallel: bool = False
    max_workers: int | None = None

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("EngineConfig.max_retries must be >= 0")
        if self.retry_delay_seconds < 0:
            raise ValueError("EngineConfig.retry_delay_seconds must be >= 0")
        if self.pool_size_valid is not None and self.pool_size_valid < 1:
            raise ValueError("EngineConfig.max_workers must be >= 1 if set")

    @property
    def pool_size_valid(self) -> int | None:
        """Alias interne pour la validation."""
        return self.max_workers

    @property
    def retry_delay(self) -> timedelta:
        """``retry_delay_seconds`` exprimé en ``timedelta``."""
        return timedelta(seconds=self.retry_delay_seconds)
