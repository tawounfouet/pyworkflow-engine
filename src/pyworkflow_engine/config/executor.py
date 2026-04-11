"""
ExecutorConfig — stratégie d'exécution des steps.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_STRATEGIES = ("local", "thread_pool", "process_pool", "async")


@dataclass(frozen=True)
class ExecutorConfig:
    """Stratégie d'exécution par défaut des steps.

    Args:
        strategy: Type d'executor utilisé pour les steps sans executor explicite.
            Valeurs acceptées : ``"local"``, ``"thread_pool"``, ``"process_pool"``,
            ``"async"``.
        pool_size: Taille du pool pour les executors ``thread_pool`` et
            ``process_pool``.
        max_workers: Alias de ``pool_size`` pour compatibilité avec l'API
            ``WorkflowEngine(max_workers=…)``. Prend le dessus sur ``pool_size``
            si les deux sont fournis.

    Examples:
        >>> cfg = ExecutorConfig(strategy="thread_pool", pool_size=8)
        >>> cfg.effective_workers
        8
        >>> ExecutorConfig(strategy="invalid")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: ExecutorConfig.strategy must be one of ...
    """

    strategy: str = "local"
    pool_size: int = 4
    max_workers: int | None = None

    def __post_init__(self) -> None:
        if self.strategy not in VALID_STRATEGIES:
            raise ValueError(
                f"ExecutorConfig.strategy must be one of {VALID_STRATEGIES}, "
                f"got '{self.strategy}'"
            )
        if self.pool_size < 1:
            raise ValueError("ExecutorConfig.pool_size must be >= 1")
        if self.max_workers is not None and self.max_workers < 1:
            raise ValueError("ExecutorConfig.max_workers must be >= 1 if set")

    @property
    def effective_workers(self) -> int:
        """Nombre effectif de workers (``max_workers`` prime sur ``pool_size``)."""
        return self.max_workers if self.max_workers is not None else self.pool_size
