"""
PyWorkflow Engine — couche ports (interfaces pures).

Ce package regroupe les **contrats abstraits** (ABC, Protocol, Enum de contrat
et exceptions de contrat) que toute implémentation d'adapter doit respecter.

Règle hexagonale fondamentale :
    - ``ports/`` ne contient **aucune implémentation** concrète.
    - ``engine/`` et ``models/`` (domaine) dépendent de ``ports/``.
    - ``adapters/`` implémente les interfaces définies dans ``ports/``.
    - ``facade.py`` assemble domaine + ports + adapters.

Contenu :
    - :mod:`ports.persistence` — ``BasePersistence``, ``PersistenceError``,
      ``JobNotFoundError``, ``TransactionError``, ``TransactionContext``
    - :mod:`ports.executor`    — ``BaseExecutor``, ``ExecutorRegistry``
    - :mod:`ports.trigger`     — ``BaseTrigger``, ``TriggerState``
"""

from __future__ import annotations

from pyworkflow_engine.ports.executor import BaseExecutor, ExecutorRegistry
from pyworkflow_engine.ports.persistence import (
    BasePersistence,
    JobNotFoundError,
    PersistenceError,
    TransactionContext,
    TransactionError,
)
from pyworkflow_engine.ports.trigger import BaseTrigger, TriggerState

__all__ = [
    # Persistence port
    "BasePersistence",
    "PersistenceError",
    "JobNotFoundError",
    "TransactionError",
    "TransactionContext",
    # Executor port
    "BaseExecutor",
    "ExecutorRegistry",
    # Trigger port
    "BaseTrigger",
    "TriggerState",
]
