"""Application factory — crée et configure l'app FastAPI.

Usage::

    from pyworkflow_engine.adapters.api.app import create_app
    app = create_app(engine)
    # uvicorn.run(app, host="0.0.0.0", port=8000)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from pyworkflow_engine.adapters.api.config import APIConfig
from pyworkflow_engine.adapters.api.errors import register_exception_handlers
from pyworkflow_engine.adapters.api.middleware import (
    RequestIDMiddleware,
    TimingMiddleware,
)


def create_app(
    engine: Any,
    config: APIConfig | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Crée une application FastAPI configurée.

    Args:
        engine: Instance WorkflowEngine (avec persistence configurée).
        config: Configuration API. Valeurs par défaut si absent.
        **kwargs: Arguments additionnels passés à FastAPI().

    Returns:
        Application FastAPI prête à être servie par uvicorn.
    """
    config = config or APIConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Startup — stocke engine + config dans app.state
        app.state.engine = engine
        app.state.config = config
        yield
        # Shutdown — cleanup si nécessaire
        if hasattr(engine, "shutdown_executors"):
            engine.shutdown_executors()

    app = FastAPI(
        title="PyWorkflow Engine API",
        description="REST API for workflow orchestration — zero infrastructure",
        version="0.10.0",
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        **kwargs,
    )

    # Middleware (ordre = du plus externe au plus interne)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    from pyworkflow_engine.adapters.api.routes import (
        events,
        executors,
        health,
        jobs,
        runs,
        websocket,
    )

    app.include_router(jobs.router)
    app.include_router(runs.router)
    app.include_router(executors.router)
    app.include_router(events.router)
    app.include_router(websocket.router)
    app.include_router(health.router)

    # Root redirect → Swagger UI
    @app.get("/", include_in_schema=False)
    async def _root() -> RedirectResponse:
        return RedirectResponse(url="/api/v1/docs")

    return app
