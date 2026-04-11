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
    description="Vérifie la santé du serveur API et du backend de stockage.",
)
def health_check(
    engine: WorkflowEngine = Depends(get_engine),
) -> HealthResponse:
    """Retourne l'état de santé du serveur."""
    storage = engine.storage
    storage_status = "healthy"
    storage_backend = "none"
    stats = None

    if storage is not None:
        storage_backend = type(storage).__name__
        try:
            health = storage.health_check()
            storage_status = health.get("status", "healthy")
            stats = storage.get_statistics()
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
