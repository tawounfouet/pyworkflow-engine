"""Schemas Pydantic — DTOs pour les jobs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StepSchema(BaseModel):
    """Représentation API d'un step."""

    name: str
    step_type: str
    depends_on: list[str] = Field(default_factory=list)
    retries: int = 0
    timeout: float | None = None
    executor_type: str = "local"
    executor_name: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "extract",
                "step_type": "function",
                "depends_on": [],
                "retries": 3,
                "timeout": 60.0,
                "executor_type": "local",
            }
        }
    }


class JobSummary(BaseModel):
    """Résumé d'un job pour les listes (léger, sans steps)."""

    name: str
    description: str = ""
    version: str | None = None
    step_count: int
    executor_type: str = "local"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class JobDetail(JobSummary):
    """Détail complet d'un job (avec steps et metadata)."""

    steps: list[StepSchema]
    timeout: float | None = None
    max_concurrent_steps: int = 10
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlanResponse(BaseModel):
    """Plan d'exécution d'un job (résultat de DAGResolver)."""

    job_name: str
    execution_order: list[str]
    parallel_groups: list[list[str]]
    critical_path: list[str]
    entry_points: list[str]
    exit_points: list[str]
    stats: dict[str, Any]
    validation_warnings: list[str]


class ValidationResponse(BaseModel):
    """Résultat de la validation d'un job."""

    job_name: str
    valid: bool
    warnings: list[str]
