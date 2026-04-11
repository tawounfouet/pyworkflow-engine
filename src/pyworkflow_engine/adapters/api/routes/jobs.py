"""Routes — /api/v1/jobs — CRUD et analyse des jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from pyworkflow_engine.adapters.api.converters import job_to_detail, job_to_summary
from pyworkflow_engine.adapters.api.deps import get_engine, verify_api_key
from pyworkflow_engine.adapters.api.schemas.jobs import (
    ExecutionPlanResponse,
    JobDetail,
    JobSummary,
    ValidationResponse,
)
from pyworkflow_engine.facade import WorkflowEngine
from pyworkflow_engine.ports.storage import JobNotFoundError

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"],
    dependencies=[Depends(verify_api_key)],
)


@router.get(
    "",
    response_model=list[JobSummary],
    summary="Lister les jobs",
    description="Retourne la liste de tous les jobs enregistrés.",
)
def list_jobs(
    limit: int | None = None,
    offset: int = 0,
    engine: WorkflowEngine = Depends(get_engine),
) -> list[JobSummary]:
    """Liste tous les jobs avec pagination optionnelle."""
    jobs = engine.list_jobs(limit=limit, offset=offset)
    return [job_to_summary(j) for j in jobs]


@router.get(
    "/{name}",
    response_model=JobDetail,
    summary="Détail d'un job",
    description="Retourne le détail complet d'un job (steps, metadata).",
    responses={404: {"description": "Job introuvable"}},
)
def get_job(
    name: str,
    engine: WorkflowEngine = Depends(get_engine),
) -> JobDetail:
    """Récupère un job par son nom."""
    job = engine.get_job(name)
    if job is None:
        raise JobNotFoundError(
            f"Job '{name}' not found",
            details={"job_name": name},
        )
    return job_to_detail(job)


@router.get(
    "/{name}/plan",
    response_model=ExecutionPlanResponse,
    summary="Plan d'exécution",
    description="Génère le plan d'exécution (DAG) d'un job.",
    responses={404: {"description": "Job introuvable"}},
)
def get_execution_plan(
    name: str,
    engine: WorkflowEngine = Depends(get_engine),
) -> ExecutionPlanResponse:
    """Génère le plan d'exécution pour un job."""
    job = engine.get_job(name)
    if job is None:
        raise JobNotFoundError(
            f"Job '{name}' not found",
            details={"job_name": name},
        )
    plan = engine.get_execution_plan(job)

    # critical_path returns (path_list, length) tuple — extract just the path
    critical_path = plan.get("critical_path", [])
    if isinstance(critical_path, tuple):
        critical_path = list(critical_path[0]) if critical_path else []

    return ExecutionPlanResponse(
        job_name=plan["job_name"],
        execution_order=plan["execution_order"],
        parallel_groups=plan["parallel_groups"],
        critical_path=critical_path,
        entry_points=plan["entry_points"],
        exit_points=plan["exit_points"],
        stats=plan["stats"],
        validation_warnings=plan["validation_warnings"],
    )


@router.post(
    "/{name}/validate",
    response_model=ValidationResponse,
    summary="Valider un job",
    description="Valide la définition d'un job sans l'exécuter.",
    responses={404: {"description": "Job introuvable"}},
)
def validate_job(
    name: str,
    engine: WorkflowEngine = Depends(get_engine),
) -> ValidationResponse:
    """Valide un job et retourne les avertissements."""
    job = engine.get_job(name)
    if job is None:
        raise JobNotFoundError(
            f"Job '{name}' not found",
            details={"job_name": name},
        )
    warnings = engine.validate_job(job)
    return ValidationResponse(
        job_name=name,
        valid=len(warnings) == 0,
        warnings=warnings,
    )
