"""
PyWorkflow Engine — modèles du domaine Logging.

Modèles de persistence pour le système de logging :

    WorkflowLog       — Entrée de log persistée (corrélée aux exécutions)
    WorkflowLogQuery  — Paramètres de requête (read-model)
"""

from __future__ import annotations

from pyworkflow_engine.models.logging.log_entry import WorkflowLog, WorkflowLogQuery

__all__ = [
    "WorkflowLog",
    "WorkflowLogQuery",
]
