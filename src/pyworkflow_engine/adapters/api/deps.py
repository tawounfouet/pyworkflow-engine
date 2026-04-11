"""Dependency Injection — couche Depends() pour FastAPI.

Fournit l'accès à l'engine et à la configuration via le state de l'app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.api.config import APIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def get_engine(request: Request) -> WorkflowEngine:
    """Récupère l'instance WorkflowEngine depuis le state de l'app.

    L'engine est créée une seule fois au démarrage (lifespan)
    et partagée entre toutes les requêtes.
    """
    return request.app.state.engine


def get_config(request: Request) -> APIConfig:
    """Récupère la configuration API depuis le state."""
    return request.app.state.config


# ── Auth optionnel — API Key ────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> str | None:
    """Vérifie l'API Key si l'auth est activée.

    Si ``config.require_auth`` est ``False``, toute requête passe.
    Sinon, la clé ``X-API-Key`` doit correspondre à ``config.api_key``.
    """
    config: APIConfig = request.app.state.config
    if not config.require_auth:
        return None
    if api_key is None or api_key != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
