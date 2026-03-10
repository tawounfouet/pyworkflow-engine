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

# Note: L'engine sera importé quand il sera implémenté
# from .engine import WorkflowEngine

__all__ = [
    # Réexporter tout depuis models
    *models.__all__,
    # Engine sera ajouté plus tard
    # "WorkflowEngine",
]
