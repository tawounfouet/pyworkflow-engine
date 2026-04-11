"""Routes — /api/v1/executors — liste des executors enregistrés."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from pyworkflow_engine.adapters.api.deps import get_engine, verify_api_key
from pyworkflow_engine.adapters.api.schemas.executors import ExecutorInfo
from pyworkflow_engine.facade import WorkflowEngine

router = APIRouter(
    prefix="/api/v1/executors",
    tags=["executors"],
    dependencies=[Depends(verify_api_key)],
)


@router.get(
    "",
    response_model=list[ExecutorInfo],
    summary="Lister les executors",
    description="Retourne la liste des executors enregistrés dans le moteur.",
)
def list_executors(
    engine: WorkflowEngine = Depends(get_engine),
) -> list[ExecutorInfo]:
    """Liste tous les executors enregistrés."""
    names = engine.list_executors()
    result = []
    for name in names:
        executor = engine.get_executor(name)
        executor_type = type(executor).__name__ if executor else "unknown"
        result.append(ExecutorInfo(name=name, executor_type=executor_type))
    return result
