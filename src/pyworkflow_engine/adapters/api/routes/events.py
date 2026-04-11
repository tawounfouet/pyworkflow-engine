"""Routes — /api/v1/events — Server-Sent Events (SSE).

Suivi temps réel mono-directionnel des runs via SSE polling.
Phase 1 : polling interne sur la persistence.
Phase 3 : EventBus pour un vrai push.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from pyworkflow_engine.adapters.api.converters import run_to_json, runs_to_json
from pyworkflow_engine.adapters.api.deps import get_engine, verify_api_key
from pyworkflow_engine.facade import WorkflowEngine
from pyworkflow_engine.models.enums import TERMINAL_STATUSES

try:
    from sse_starlette.sse import EventSourceResponse
except ImportError:
    EventSourceResponse = None  # type: ignore[assignment, misc]

router = APIRouter(
    prefix="/api/v1/events",
    tags=["events"],
    dependencies=[Depends(verify_api_key)],
)


@router.get(
    "/stream",
    summary="Stream SSE d'événements",
    description=(
        "Stream Server-Sent Events pour le suivi temps réel. "
        "Si ``run_id`` est fourni, le stream se ferme automatiquement "
        "quand le run atteint un état terminal."
    ),
)
async def event_stream(
    run_id: str | None = Query(None, description="Filtre par run ID"),
    interval: float = Query(2.0, ge=0.5, le=30.0, description="Intervalle polling (s)"),
    engine: WorkflowEngine = Depends(get_engine),
):
    """Stream SSE d'événements — suivi de run en temps réel."""
    if EventSourceResponse is None:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=501,
            content={
                "error": "SSE_NOT_AVAILABLE",
                "message": (
                    "SSE requires 'sse-starlette'. "
                    "Install with: pip install pyworkflow-engine[api]"
                ),
            },
        )

    async def generate():
        while True:
            if run_id:
                job_run = engine.get_job_run(run_id)
                if job_run is None:
                    yield {"event": "error", "data": '{"error": "RUN_NOT_FOUND"}'}
                    return
                yield {
                    "event": "run_update",
                    "data": run_to_json(job_run),
                }
                if job_run.status in TERMINAL_STATUSES:
                    yield {
                        "event": "run_completed",
                        "data": run_to_json(job_run),
                    }
                    return
            else:
                # Stream global — derniers runs modifiés
                runs = engine.list_job_runs(limit=10)
                yield {
                    "event": "runs_snapshot",
                    "data": runs_to_json(runs),
                }
            await asyncio.sleep(interval)

    return EventSourceResponse(generate())
