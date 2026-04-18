"""
PyWorkflow Engine — couche orchestration.

Ce package contient les composants d'exécution des workflows :

- ``runner``          : WorkflowRunner — exécute les steps dans l'ordre topologique
- ``parallel_runner`` : ParallelRunner — exécute les steps par groupes parallèles
- ``retry``           : RetryHandler — gère les tentatives de réexécution
- ``suspension``      : SuspensionManager — suspension/reprise persistence-aware
- ``dag``             : DAGResolver (re-export depuis core/dag)
- ``context``         : WorkflowContext (re-export depuis core/context)
"""

from __future__ import annotations

from .context import WorkflowContext

# Re-exports for convenience
from .dag import DAGResolver
from .parallel_runner import ParallelRunner
from .pipeline_runner import PipelineRunner
from .retry import RetryHandler
from .runner import WorkflowRunner
from .suspension import SuspensionManager

__all__ = [
    "WorkflowRunner",
    "ParallelRunner",
    "PipelineRunner",
    "RetryHandler",
    "SuspensionManager",
    "DAGResolver",
    "WorkflowContext",
]
