"""Routes — /api/v1/health — health check et métriques."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from pyworkflow_engine.adapters.api.deps import get_engine
from pyworkflow_engine.adapters.api.schemas.common import HealthResponse
from pyworkflow_engine.facade import WorkflowEngine

router = APIRouter(
    prefix="/api/v1/health",
    tags=["health"],
)


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health check",
    description="Vérifie la santé du serveur API et du backend de persistence.",
)
def health_check(
    engine: WorkflowEngine = Depends(get_engine),
) -> HealthResponse:
    """Retourne l'état de santé du serveur."""
    persistence = engine.persistence
    storage_status = "healthy"
    storage_backend = "none"
    stats = None

    if persistence is not None:
        storage_backend = type(persistence).__name__
        try:
            health = persistence.health_check()
            storage_status = health.get("status", "healthy")
            stats = persistence.get_statistics()
        except Exception:
            storage_status = "unhealthy"

    return HealthResponse(
        status="healthy",
        version="0.10.0",
        storage_backend=storage_backend,
        storage_status=storage_status,
        timestamp=datetime.now(UTC),
        stats=stats,
    )
