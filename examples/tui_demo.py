"""Exemple minimal pour tester la TUI PyWorkflow.

Usage::

    pyworkflow --app examples.tui_demo:engine tui
"""

from __future__ import annotations

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.adapters.persistence.memory import InMemoryPersistence
from pyworkflow_engine.models import Job
from pyworkflow_engine.models.enums import ExecutorType, StepType
from pyworkflow_engine.models.step import Step

# ---------------------------------------------------------------------------
# Définition des jobs (enregistrés au niveau module)
# ---------------------------------------------------------------------------

etl_job = Job(
    name="etl_pipeline",
    description="Pipeline ETL — extraction, transformation, chargement.",
    steps=[
        Step(
            name="extract",
            step_type=StepType.FUNCTION,
            handler=lambda ctx: {"records": 100},
        ),
        Step(
            name="transform",
            step_type=StepType.FUNCTION,
            handler=lambda ctx: {
                "transformed": ctx.get("extract", {}).get("records", 0)
            },
            dependencies=["extract"],
        ),
        Step(
            name="load",
            step_type=StepType.FUNCTION,
            handler=lambda ctx: {"loaded": True},
            dependencies=["transform"],
        ),
    ],
    default_executor=ExecutorType.LOCAL,
)

monitoring_job = Job(
    name="health_check",
    description="Vérification de santé des services.",
    steps=[
        Step(
            name="check_db",
            step_type=StepType.FUNCTION,
            handler=lambda ctx: {"db_ok": True},
        ),
        Step(
            name="check_api",
            step_type=StepType.FUNCTION,
            handler=lambda ctx: {"api_ok": True},
        ),
        Step(
            name="report",
            step_type=StepType.FUNCTION,
            handler=lambda ctx: {"status": "healthy"},
            dependencies=["check_db", "check_api"],
        ),
    ],
)

# ---------------------------------------------------------------------------
# Instance WorkflowEngine — exposée au niveau module pour le loader CLI/TUI
# InMemoryPersistence permet à list_jobs() / get_job() de fonctionner sans
# base de données externe.
# ---------------------------------------------------------------------------

engine = WorkflowEngine()
engine.persistence = InMemoryPersistence()
engine.save_job(etl_job)
engine.save_job(monitoring_job)
