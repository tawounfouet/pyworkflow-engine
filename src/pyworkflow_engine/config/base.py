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
from pyworkflow_engine.config.storage import StorageConfig


@dataclass(frozen=True)
class WorkflowConfig:
    """Configuration complète de ``WorkflowEngine``.

    Composée de quatre sous-configs indépendantes, toutes optionnelles.
    Quand ``persistence.db_path`` est fourni, le moteur crée automatiquement
    le backend SQLite et, si ``logging.log_to_db=True``, branche le handler
    de logs sur la même base.

    Args:
        engine: Paramètres d'exécution (retry, timeout, parallélisme).
        executor: Stratégie et dimensionnement des executors.
        logging: Niveau, format, fichier et stockage DB des logs.
        persistence: Backend de persistence (chemin SQLite).

    Examples:
        >>> cfg = WorkflowConfig()
        >>> cfg.engine.parallel
        False
        >>> cfg.persistence.db_path is None
        True

        >>> # Configuration clé en main — DB + logs fichier + logs en BD
        >>> from pyworkflow_engine.config import (
        ...     WorkflowConfig, StorageConfig, LoggingConfig
        ... )
        >>> cfg = WorkflowConfig(
        ...     (StorageConfig)(db_path="workflow.db"),
        ...     logging=LoggingConfig(
        ...         level="DEBUG",
        ...         log_dir="logs",
        ...         log_to_db=True,
        ...     ),
        ... )
        >>> cfg.persistence.db_path
        'workflow.db'
        >>> cfg.logging.log_to_db
        True
    """

    engine: EngineConfig = field(default_factory=EngineConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
