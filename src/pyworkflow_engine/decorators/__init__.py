"""
pyworkflow_engine.decorators — API déclarative par décorateurs.

Fournit une alternative à la construction impérative de ``Job`` / ``Step``.
Les deux APIs coexistent sans conflit.

Usage rapide ::

    from pyworkflow_engine.decorators import step, job
    from pyworkflow_engine import WorkflowEngine

    @step(name="fetch")
    def fetch_data(source: str = "api") -> dict:
        return {"records": [1, 2, 3]}

    @step(name="transform", dependencies=["fetch"])
    def transform_data(records: list | None = None) -> dict:
        return {"out": [r * 10 for r in (records or [])]}

    @job(name="ETL Pipeline")
    def etl():
        data = fetch_data()
        transform_data(records=data["records"])

    engine = WorkflowEngine()
    result = engine.run(etl.build())

Voir ADR-005 pour les décisions architecturales.
"""

from pyworkflow_engine.decorators.job_decorator import JobBuilder, job
from pyworkflow_engine.decorators.step_decorator import StepSpec, step

__all__ = [
    "step",
    "job",
    "StepSpec",
    "JobBuilder",
]
