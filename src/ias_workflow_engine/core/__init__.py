"""
Core module — API publique du moteur de workflow.

Ce module expose les composants principaux du système de workflow
pour une utilisation directe sans dépendances externes.

Usage basique:
    >>> from ias_workflow_engine.core import Job, Step, StepType
    >>>
    >>> def hello_world():
    ...     return {"message": "Hello World!"}
    >>>
    >>> job = Job(
    ...     name="hello_job",
    ...     steps=[Step("hello", StepType.FUNCTION, callable=hello_world)]
    ... )

Pour l'exécution, voir `ias_workflow_engine.core.engine`.
"""

from __future__ import annotations

# Réexporter tous les modèles
from .models import *

# Importer les composants du moteur
from .engine import WorkflowEngine
from .dag import DAGResolver
from .context import WorkflowContext
from .exceptions import *

__all__ = [
    # Réexporter tout depuis models
    *models.__all__,
    # Composants du moteur
    "WorkflowEngine",
    "DAGResolver",
    "WorkflowContext",
    # Exceptions principales
    "WorkflowError",
    "WorkflowSuspended",
    "WorkflowFailed",
    "StepExecutionError",
    "DAGValidationError",
    "ContextError",
]
