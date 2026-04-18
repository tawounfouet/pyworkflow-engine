"""Convertisseurs domain models → schemas Pydantic.

Fonctions pures sans side effects — testables unitairement sans mock.
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.adapters.api.schemas.jobs import (
    JobDetail,
    JobSummary,
    StepSchema,
)
from pyworkflow_engine.adapters.api.schemas.runs import (
    RunDetail,
    RunSummary,
    StepRunSchema,
)
from pyworkflow_engine.models import Job, JobRun
from pyworkflow_engine.models.workflow.run import StepRun


def job_to_summary(job: Job) -> JobSummary:
    """Convertit un Job domain en JobSummary DTO."""
    return JobSummary(
        name=job.name,
        description=job.description,
        version=job.version,
        step_count=len(job.steps),
        executor_type=job.default_executor.value,
        enabled=job.enabled,
        tags=list(job.tags) if job.tags else [],
    )


def job_to_detail(job: Job) -> JobDetail:
    """Convertit un Job domain en JobDetail DTO (avec steps)."""
    return JobDetail(
        name=job.name,
        description=job.description,
        version=job.version,
        step_count=len(job.steps),
        executor_type=job.default_executor.value,
        enabled=job.enabled,
        tags=list(job.tags) if job.tags else [],
        steps=[_step_to_schema(s) for s in job.steps],
        timeout=job.timeout.total_seconds() if job.timeout else None,
        max_concurrent_steps=job.max_concurrent_steps,
        metadata=dict(job.metadata) if job.metadata else {},
    )


def run_to_summary(run: JobRun) -> RunSummary:
    """Convertit un JobRun domain en RunSummary DTO."""
    duration_ms = None
    if run.start_time and run.end_time:
        duration_ms = int((run.end_time - run.start_time).total_seconds() * 1000)
    return RunSummary(
        job_run_id=run.job_run_id,
        job_name=run.job_name,
        status=run.status.value,
        started_at=run.start_time,
        completed_at=run.end_time,
        duration_ms=duration_ms,
        triggered_by=run.triggered_by,
    )


def run_to_detail(run: JobRun) -> RunDetail:
    """Convertit un JobRun domain en RunDetail DTO (avec step_runs)."""
    duration_ms = None
    if run.start_time and run.end_time:
        duration_ms = int((run.end_time - run.start_time).total_seconds() * 1000)
    return RunDetail(
        job_run_id=run.job_run_id,
        job_name=run.job_name,
        job_version=run.job_version,
        status=run.status.value,
        started_at=run.start_time,
        completed_at=run.end_time,
        duration_ms=duration_ms,
        triggered_by=run.triggered_by,
        step_runs=[_step_run_to_schema(sr) for sr in run.step_runs],
        context=dict(run.input_data) if run.input_data else {},
        error=run.error,
    )


def run_to_json(run: JobRun) -> str:
    """Sérialise un JobRun en JSON string (pour SSE/WebSocket)."""
    return run_to_detail(run).model_dump_json()


def runs_to_json(runs: list[JobRun]) -> str:
    """Sérialise une liste de JobRun en JSON string (pour SSE)."""
    import json

    return json.dumps([run_to_summary(r).model_dump(mode="json") for r in runs])


def _step_to_schema(step: Any) -> StepSchema:
    """Convertit un Step domain en StepSchema DTO."""
    return StepSchema(
        name=step.name,
        step_type=step.step_type.value if step.step_type else "function",
        depends_on=list(step.dependencies) if step.dependencies else [],
        retries=step.retry_count,
        timeout=step.timeout.total_seconds() if step.timeout else None,
        executor_type=step.executor_type.value if step.executor_type else "local",
    )


def _step_run_to_schema(sr: StepRun) -> StepRunSchema:
    """Convertit un StepRun domain en StepRunSchema DTO."""
    return StepRunSchema(
        step_name=sr.step_name,
        status=sr.status.value,
        executor_type=sr.executor_type.value if sr.executor_type else "local",
        start_time=sr.start_time,
        end_time=sr.end_time,
        duration_ms=sr.duration_ms,
        retry_count=sr.retry_count,
        output=sr.output_data if sr.output_data else None,
        error=sr.error,
    )
