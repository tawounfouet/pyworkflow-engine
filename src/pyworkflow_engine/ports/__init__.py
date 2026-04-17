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
    - :mod:`ports.storage` — ``BaseStorage``, ``StorageError``,
      ``JobNotFoundError``, ``TransactionError``, ``TransactionContext``
    - :mod:`ports.executor`    — ``BaseExecutor``, ``ExecutorRegistry``
    - :mod:`ports.trigger`     — ``BaseTrigger``, ``TriggerState``
    - :mod:`ports.checkpoint`  — ``BaseCheckpointStore``, ``CheckpointRecord``,
      ``CheckpointNotFoundError`` (ADR-021)
    - :mod:`ports.persistable` — ``PersistableModel``, ``TableMeta``,
      ``ColumnDef``, ``ColumnType``, ``ModelRegistry`` (ADR-017)
"""

from __future__ import annotations

from pyworkflow_engine.ports.checkpoint import (
    BaseCheckpointStore,
    CheckpointNotFoundError,
    CheckpointRecord,
)
from pyworkflow_engine.ports.executor import BaseExecutor, ExecutorRegistry
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)
from pyworkflow_engine.ports.storage import (
    BaseStorage,
    JobNotFoundError,
    StorageError,
    TransactionContext,
    TransactionError,
)
from pyworkflow_engine.ports.trigger import BaseTrigger, TriggerState

__all__ = [
    # Persistence port
    "BaseStorage",
    "StorageError",
    "JobNotFoundError",
    "TransactionError",
    "TransactionContext",
    # Executor port
    "BaseExecutor",
    "ExecutorRegistry",
    # Trigger port
    "BaseTrigger",
    "TriggerState",
    # Checkpoint port (ADR-021)
    "BaseCheckpointStore",
    "CheckpointRecord",
    "CheckpointNotFoundError",
    # Persistable port (ADR-017)
    "PersistableModel",
    "TableMeta",
    "ColumnDef",
    "ColumnType",
    "ModelRegistry",
]
