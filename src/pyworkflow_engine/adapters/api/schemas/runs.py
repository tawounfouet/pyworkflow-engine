"""Schemas Pydantic — DTOs pour les runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    """Corps de la requête POST /runs."""

    job_name: str
    context: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_name": "etl_pipeline",
                "context": {"env": "staging", "batch_size": 1000},
            }
        }
    }


class StepRunSchema(BaseModel):
    """Représentation API d'un step run."""

    step_name: str
    status: str
    executor_type: str = "local"
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    output: Any | None = None
    error: str | None = None


class RunSummary(BaseModel):
    """Résumé d'un run pour les listes (sans step_runs)."""

    job_run_id: str
    job_name: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    triggered_by: str = "api"


class RunDetail(RunSummary):
    """Détail complet d'un run (avec step_runs)."""

    job_version: str | None = None
    step_runs: list[StepRunSchema] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RunListResponse(BaseModel):
    """Réponse paginée pour GET /runs."""

    items: list[RunSummary]
    total: int
    page: int = 1
    page_size: int = 20
    has_next: bool = False


class ResumeRequest(BaseModel):
    """Corps de la requête POST /runs/{run_id}/resume."""

    outputs: dict[str, Any] = Field(default_factory=dict)
