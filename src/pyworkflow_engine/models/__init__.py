"""
PyWorkflow Engine - couche domaine (modeles).

Expose l'API publique des modeles de workflow.

Enums :
    TriggerType, StepType, ExecutorType, RunStatus, Priority

Design-time (definitions) :
    Step, SubJob, Job, Pipeline, PipelineStage

Runtime (instances d'execution) :
    StepLog, StepRun, JobRun, PipelineRun, StageRun

Serialisation :
    Chaque classe expose to_dict() / from_dict() directement.
    Les fonctions libres ci-dessous sont de minces delegues conserves
    pour la compatibilite des backends de persistence.
"""

from __future__ import annotations

from typing import Any

from .workflow.connector import ConnectorOutcome, ConnectorRef
from .enums import (
    ACTIVE_STATUSES,
    SUSPENDED_STATUSES,
    TERMINAL_STATUSES,
    ExecutorType,
    Priority,
    RunStatus,
    StepType,
    TriggerType,
    can_cancel,
    can_resume,
    is_active,
    is_suspended,
    is_terminal,
)
from .workflow.job import Job
from .pipeline.pipeline import Pipeline, PipelineStage
from .pipeline.pipeline_run import PipelineRun, StageRun
from .workflow.run import JobRun, StepLog, StepRun, generate_id, utc_now
from .workflow.step import Step, SubJob

# ---------------------------------------------------------------------------
# Thin wrapper functions -- delegate to model.to_dict() / Model.from_dict()
# ---------------------------------------------------------------------------


def step_to_dict(step: Step) -> dict[str, Any]:
    return step.to_dict()


def dict_to_step(data: dict[str, Any]) -> Step:
    return Step.from_dict(data)


def sub_job_to_dict(sub_job: SubJob) -> dict[str, Any]:
    return sub_job.to_dict()


def dict_to_sub_job(data: dict[str, Any]) -> SubJob:
    return SubJob.from_dict(data)


def job_to_dict(job: Job) -> dict[str, Any]:
    return job.to_dict()


def dict_to_job(data: dict[str, Any]) -> Job:
    return Job.from_dict(data)


def step_log_to_dict(log: StepLog) -> dict[str, Any]:
    return log.to_dict()


def dict_to_step_log(data: dict[str, Any]) -> StepLog:
    return StepLog.from_dict(data)


def step_run_to_dict(step_run: StepRun) -> dict[str, Any]:
    return step_run.to_dict()


def dict_to_step_run(data: dict[str, Any]) -> StepRun:
    return StepRun.from_dict(data)


def job_run_to_dict(job_run: JobRun) -> dict[str, Any]:
    return job_run.to_dict()


def dict_to_job_run(data: dict[str, Any]) -> JobRun:
    return JobRun.from_dict(data)


def pipeline_to_dict(pipeline: Pipeline) -> dict[str, Any]:
    return pipeline.to_dict()


def dict_to_pipeline(data: dict[str, Any]) -> Pipeline:
    return Pipeline.from_dict(data)


def pipeline_stage_to_dict(stage: PipelineStage) -> dict[str, Any]:
    return stage.to_dict()


def dict_to_pipeline_stage(data: dict[str, Any]) -> PipelineStage:
    return PipelineStage.from_dict(data)


def pipeline_run_to_dict(pipeline_run: PipelineRun) -> dict[str, Any]:
    return pipeline_run.to_dict()


def dict_to_pipeline_run(data: dict[str, Any]) -> PipelineRun:
    return PipelineRun.from_dict(data)


def stage_run_to_dict(stage_run: StageRun) -> dict[str, Any]:
    return stage_run.to_dict()


def dict_to_stage_run(data: dict[str, Any]) -> StageRun:
    return StageRun.from_dict(data)


__all__ = [
    # Enums
    "TriggerType",
    "StepType",
    "ExecutorType",
    "RunStatus",
    "Priority",
    # Status helpers
    "TERMINAL_STATUSES",
    "SUSPENDED_STATUSES",
    "ACTIVE_STATUSES",
    "is_terminal",
    "is_suspended",
    "is_active",
    "can_resume",
    "can_cancel",
    # Design-time
    "Step",
    "SubJob",
    "Job",
    "Pipeline",
    "PipelineStage",
    # Runtime
    "StepLog",
    "StepRun",
    "JobRun",
    "PipelineRun",
    "StageRun",
    "utc_now",
    "generate_id",
    # Serialization wrappers
    "step_to_dict",
    "dict_to_step",
    "sub_job_to_dict",
    "dict_to_sub_job",
    "job_to_dict",
    "dict_to_job",
    "step_log_to_dict",
    "dict_to_step_log",
    "step_run_to_dict",
    "dict_to_step_run",
    "job_run_to_dict",
    "dict_to_job_run",
    "pipeline_to_dict",
    "dict_to_pipeline",
    "pipeline_stage_to_dict",
    "dict_to_pipeline_stage",
    "pipeline_run_to_dict",
    "dict_to_pipeline_run",
    "stage_run_to_dict",
    "dict_to_stage_run",
    # Connector (bridge pyconnectors — ADR-016)
    "ConnectorRef",
    "ConnectorOutcome",
]
