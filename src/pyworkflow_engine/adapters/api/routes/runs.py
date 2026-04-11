"""Routes — /api/v1/runs — CRUD et actions sur les runs."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from pyworkflow_engine.adapters.api.converters import (
    run_to_detail,
    run_to_summary,
)
from pyworkflow_engine.adapters.api.deps import get_engine, verify_api_key
from pyworkflow_engine.adapters.api.schemas.runs import (
    ResumeRequest,
    RunCreate,
    RunDetail,
    RunListResponse,
    RunSummary,
    StepRunSchema,
)
from pyworkflow_engine.adapters.api.converters import _step_run_to_schema
from pyworkflow_engine.facade import WorkflowEngine
from pyworkflow_engine.ports.persistence import JobNotFoundError

router = APIRouter(
    prefix="/api/v1/runs",
    tags=["runs"],
    dependencies=[Depends(verify_api_key)],
)


@router.post(
    "",
    response_model=RunDetail,
    status_code=201,
    summary="Lancer un run",
    description="Exécute un job par son nom et retourne le résultat.",
    responses={
        404: {"description": "Job introuvable"},
        409: {"description": "Workflow suspendu"},
    },
)
async def create_run(
    body: RunCreate,
    engine: WorkflowEngine = Depends(get_engine),
) -> RunDetail:
    """Lance l'exécution d'un job avec persistence.

    Note Phase 1 : l'exécution est synchrone (bloquante via asyncio.to_thread).
    Phase 3 prévoit un background worker avec réponse 202 Accepted.
    """
    job_run = await asyncio.to_thread(
        engine.run_with_persistence,
        body.job_name,
        initial_context=body.context,
        run_id=body.run_id,
    )
    return run_to_detail(job_run)


@router.get(
    "",
    response_model=RunListResponse,
    summary="Lister les runs",
    description="Retourne la liste paginée des runs avec filtrage optionnel.",
)
def list_runs(
    page: int = Query(1, ge=1, description="Numéro de page"),
    page_size: int = Query(20, ge=1, le=100, description="Éléments par page"),
    job_name: str | None = Query(None, description="Filtre par nom de job"),
    status: str | None = Query(None, description="Filtre par statut"),
    engine: WorkflowEngine = Depends(get_engine),
) -> RunListResponse:
    """Liste les runs avec pagination et filtrage."""
    offset = (page - 1) * page_size

    # Récupérer un élément de plus pour savoir s'il y a une page suivante
    runs = engine.list_job_runs(
        job_name=job_name,
        status=status,
        limit=page_size + 1,
        offset=offset,
    )

    has_next = len(runs) > page_size
    if has_next:
        runs = runs[:page_size]

    # Calculer le total (on fait une requête sans limit/offset)
    all_runs = engine.list_job_runs(job_name=job_name, status=status)
    total = len(all_runs)

    return RunListResponse(
        items=[run_to_summary(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    summary="Détail d'un run",
    description="Retourne le détail complet d'un run (step_runs, contexte).",
    responses={404: {"description": "Run introuvable"}},
)
def get_run(
    run_id: str,
    engine: WorkflowEngine = Depends(get_engine),
) -> RunDetail:
    """Récupère un run par son identifiant."""
    job_run = engine.get_job_run(run_id)
    if job_run is None:
        raise JobNotFoundError(
            f"Run '{run_id}' not found",
            details={"run_id": run_id},
        )
    return run_to_detail(job_run)


@router.get(
    "/{run_id}/steps",
    response_model=list[StepRunSchema],
    summary="Steps d'un run",
    description="Retourne les step runs d'un run spécifique.",
    responses={404: {"description": "Run introuvable"}},
)
def get_run_steps(
    run_id: str,
    engine: WorkflowEngine = Depends(get_engine),
) -> list[StepRunSchema]:
    """Récupère les step runs d'un run."""
    job_run = engine.get_job_run(run_id)
    if job_run is None:
        raise JobNotFoundError(
            f"Run '{run_id}' not found",
            details={"run_id": run_id},
        )
    return [_step_run_to_schema(sr) for sr in job_run.step_runs]


@router.post(
    "/{run_id}/cancel",
    response_model=RunSummary,
    summary="Annuler un run",
    description="Annule un run suspendu.",
    responses={
        404: {"description": "Run introuvable"},
        409: {"description": "Run non annulable (état terminal)"},
    },
)
def cancel_run(
    run_id: str,
    engine: WorkflowEngine = Depends(get_engine),
) -> RunSummary:
    """Annule un run suspendu."""
    cancelled = engine.cancel(run_id)
    if not cancelled:
        # Vérifier si le run existe pour distinguer 404 vs 409
        job_run = engine.get_job_run(run_id)
        if job_run is None:
            raise JobNotFoundError(
                f"Run '{run_id}' not found",
                details={"run_id": run_id},
            )
        # Run existe mais n'est pas annulable (état terminal)
        from pyworkflow_engine.exceptions import WorkflowCancelled

        raise WorkflowCancelled(
            f"Run '{run_id}' cannot be cancelled (status: {job_run.status.value})",
            cancel_reason=f"Status {job_run.status.value} is not cancellable",
        )

    # Le run a été annulé — récupérer l'état mis à jour
    job_run = engine.get_job_run(run_id)
    if job_run is not None:
        return run_to_summary(job_run)

    # Fallback si le run n'est plus dans la persistence (cas rare)
    return RunSummary(
        job_run_id=run_id,
        job_name="",
        status="cancelled",
    )


@router.post(
    "/{run_id}/resume",
    response_model=RunDetail,
    summary="Reprendre un run",
    description="Reprend l'exécution d'un run suspendu.",
    responses={
        404: {"description": "Run introuvable"},
        409: {"description": "Run non resumable"},
    },
)
async def resume_run(
    run_id: str,
    body: ResumeRequest | None = None,
    engine: WorkflowEngine = Depends(get_engine),
) -> RunDetail:
    """Reprend un run suspendu avec des outputs optionnels."""
    outputs = body.outputs if body else None
    job_run = await asyncio.to_thread(
        engine.resume,
        run_id,
        step_outputs=outputs,
    )
    return run_to_detail(job_run)
