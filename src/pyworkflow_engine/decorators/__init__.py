"""
pyworkflow_engine.decorators — API déclarative par décorateurs.

Fournit une alternative à la construction impérative de ``Job`` / ``Step``
/ ``Pipeline``. Les deux APIs coexistent sans conflit.

Usage rapide ::

    from pyworkflow_engine.decorators import step, job, stage, pipeline
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

    @stage(job=etl)
    def etl_stage():
        '''ETL stage in a pipeline.'''

    @pipeline(name="my-pipeline", schedule="0 1 * * 0")
    def my_pipeline():
        etl_stage()

    p = my_pipeline.build()

Voir ADR-005 / ADR-014 pour les décisions architecturales.
"""

from pyworkflow_engine.decorators.job_decorator import JobBuilder, job
from pyworkflow_engine.decorators.pipeline_decorator import (
    PipelineBuilder,
    StageSpec,
    pipeline,
    stage,
)
from pyworkflow_engine.decorators.step_decorator import StepSpec, step

__all__ = [
    # Step / Job (ADR-005)
    "step",
    "job",
    "StepSpec",
    "JobBuilder",
    # Pipeline / Stage (ADR-014)
    "stage",
    "pipeline",
    "StageSpec",
    "PipelineBuilder",
]
