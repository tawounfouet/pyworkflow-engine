"""
WorkflowConfig — point d'entrée unique de la configuration de pyworkflow-engine.

Usage minimal :

    >>> from pyworkflow_engine.config import WorkflowConfig
    >>> cfg = WorkflowConfig()  # Toutes les valeurs par défaut

Usage avancé :

    >>> from pyworkflow_engine.config import WorkflowConfig, EngineConfig, ExecutorConfig
    >>> cfg = WorkflowConfig(
    ...     engine=EngineConfig(parallel=True, max_workers=8, max_retries=3),
    ...     executor=ExecutorConfig(strategy="thread_pool"),
    ... )
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyworkflow_engine.config.engine import EngineConfig
from pyworkflow_engine.config.executor import ExecutorConfig
from pyworkflow_engine.config.logging import LoggingConfig


@dataclass(frozen=True)
class WorkflowConfig:
    """Configuration complète de ``WorkflowEngine``.

    Composée de trois sous-configs indépendantes, toutes optionnelles
    (les valeurs par défaut sont sensées pour une utilisation en développement).

    Args:
        engine: Paramètres d'exécution (retry, timeout, parallélisme).
        executor: Stratégie et dimensionnement des executors.
        logging: Niveau et format des logs.

    Examples:
        >>> cfg = WorkflowConfig()
        >>> cfg.engine.parallel
        False
        >>> cfg.engine.max_retries
        0
        >>> cfg.executor.strategy
        'local'
        >>> cfg.logging.level
        'INFO'

        >>> # Configuration pour la production
        >>> prod = WorkflowConfig(
        ...     engine=EngineConfig(parallel=True, max_workers=16, max_retries=3),
        ...     executor=ExecutorConfig(strategy="thread_pool", pool_size=16),
        ...     logging=LoggingConfig(level="WARNING", format="json"),
        ... )
    """

    engine: EngineConfig = field(default_factory=EngineConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
