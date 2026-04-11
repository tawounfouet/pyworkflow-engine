"""Gestion des erreurs — mapping exceptions domain → HTTP.

Traduit la hiérarchie d'exceptions du projet en réponses JSON standardisées.
L'ordre dans EXCEPTION_MAP respecte l'héritage : les sous-classes sont
testées avant les classes parentes grâce à ``isinstance()``.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from pyworkflow_engine.exceptions import (
    DAGValidationError,
    StepExecutionError,
    WorkflowCancelled,
    WorkflowError,
    WorkflowFailed,
    WorkflowSuspended,
    WorkflowTimeoutError,
    WorkflowValidationError,
)
from pyworkflow_engine.ports.persistence import (
    JobNotFoundError,
    PersistenceError,
)

# Ordre important : sous-classes avant classes parentes
EXCEPTION_MAP: list[tuple[type[Exception], int, str]] = [
    (JobNotFoundError, 404, "JOB_NOT_FOUND"),
    (DAGValidationError, 422, "DAG_VALIDATION_ERROR"),
    (WorkflowValidationError, 422, "VALIDATION_ERROR"),
    (WorkflowSuspended, 409, "WORKFLOW_SUSPENDED"),
    (WorkflowCancelled, 409, "WORKFLOW_CANCELLED"),
    (WorkflowTimeoutError, 504, "TIMEOUT"),
    (StepExecutionError, 500, "STEP_EXECUTION_ERROR"),
    (WorkflowFailed, 500, "WORKFLOW_FAILED"),
    (PersistenceError, 503, "PERSISTENCE_ERROR"),
    (WorkflowError, 500, "INTERNAL_ERROR"),
    (ValueError, 400, "BAD_REQUEST"),
]


async def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Traduit les exceptions domain en réponses JSON standardisées."""
    for exc_type, status, code in EXCEPTION_MAP:
        if isinstance(exc, exc_type):
            return JSONResponse(
                status_code=status,
                content={
                    "error": code,
                    "message": str(exc),
                    "detail": getattr(exc, "details", None),
                },
            )
    # Fallback — exception non mappée
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "detail": None,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Enregistre les handlers d'exception sur l'app FastAPI."""
    # Enregistrer un handler pour chaque type d'exception dans la map
    registered: set[type] = set()
    for exc_type, _, _ in EXCEPTION_MAP:
        if exc_type not in registered:
            app.add_exception_handler(exc_type, domain_exception_handler)
            registered.add(exc_type)
