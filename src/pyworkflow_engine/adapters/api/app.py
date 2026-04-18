"""Application factory — crée et configure l'app FastAPI.

Usage::

    from pyworkflow_engine.adapters.api.app import create_app
    app = create_app(engine)
    # uvicorn.run(app, host="0.0.0.0", port=8000)
"""

from __future__ import annotations

import logging
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

_logger = logging.getLogger(__name__)


def _setup_rate_limiting(app: FastAPI, config: APIConfig) -> None:
    """Configure slowapi si disponible et activé dans la config.

    Le rate limiter est optionnel : si ``slowapi`` n'est pas installé ou si
    ``config.rate_limit`` est None, aucune limite n'est appliquée.
    Les routes individuelles peuvent décorer leurs handlers avec
    ``@limiter.limit("10/minute")`` pour des limites plus fines.
    """
    if not config.rate_limit:
        return
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.util import get_remote_address

        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=[config.rate_limit],
        )
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
        _logger.info("Rate limiting enabled: %s per IP", config.rate_limit)
    except ImportError:
        _logger.warning(
            "rate_limit=%r configured but 'slowapi' is not installed. "
            "Install it with: pip install pyworkflow-engine[api]",
            config.rate_limit,
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

        # Avertissements de sécurité au démarrage
        if not config.require_auth:
            _logger.warning(
                "PyWorkflow API running WITHOUT authentication. "
                "Set require_auth=True and api_key=<secret> (or env PYWORKFLOW_API_KEY) "
                "before exposing this API on a non-trusted network."
            )
        if config.cors_origins == ["*"]:
            _logger.warning(
                "CORS allow_origins=['*'] — suitable for local development only. "
                "Set cors_origins to specific origins for production deployments."
            )

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

    # Rate limiting (opt-in via config.rate_limit, requires slowapi)
    _setup_rate_limiting(app, config)

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
