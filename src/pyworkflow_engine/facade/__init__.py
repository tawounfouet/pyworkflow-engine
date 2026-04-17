"""Façade package — point d'entrée public du moteur.

Structure :
    facade/engine.py  — WorkflowEngine (assemblage principal)
    facade/jobs.py    — JobsFacade (CRUD jobs/runs + exécution avec persistence)
    facade/ai.py      — AIFacade (agents, conversations, storage IA)

Usage standard (inchangé) ::

    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.facade import WorkflowEngine  # aussi valide

Accès aux sous-façades ::

    from pyworkflow_engine.facade import AIFacade, JobsFacade
    # ou directement via l'engine :
    engine.jobs.run(my_job)
    engine.ai.create_agent(name="Bot", model="claude-3-5-sonnet")
"""

from pyworkflow_engine.facade.ai import AIFacade
from pyworkflow_engine.facade.workflow_engine import WorkflowEngine
from pyworkflow_engine.facade.jobs import JobsFacade

__all__ = ["WorkflowEngine", "AIFacade", "JobsFacade"]
