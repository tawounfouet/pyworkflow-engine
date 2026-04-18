"""Configuration de l'API REST PyWorkflow Engine.

Tous les champs ont des valeurs par défaut sensées.
Surchargeable via les flags CLI ``pyworkflow api serve`` ou variables d'environnement.

Variables d'environnement reconnues :
    PYWORKFLOW_API_KEY      Clé d'API secrète (active require_auth automatiquement).
    PYWORKFLOW_CORS_ORIGINS Origines CORS séparées par des virgules
                            (ex. "https://app.example.com,https://admin.example.com").
                            Défaut : "*" (développement local uniquement).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _default_cors_origins() -> list[str]:
    raw = os.environ.get("PYWORKFLOW_CORS_ORIGINS", "")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["*"]


def _default_api_key() -> str | None:
    return os.environ.get("PYWORKFLOW_API_KEY") or None


@dataclass
class APIConfig:
    """Configuration du serveur API.

    Attributes:
        host: Adresse d'écoute du serveur.
        port: Port du serveur.
        db_path: Chemin du fichier SQLite.
        cors_origins: Liste des origines CORS autorisées.
            Par défaut ``["*"]`` (développement local uniquement).
            En production, fournir des origines explicites via
            ``PYWORKFLOW_CORS_ORIGINS`` ou ce paramètre.
            Note : ``allow_origins=["*"]`` combiné à ``allow_credentials=True``
            est invalide selon la spec CORS — les navigateurs le rejettent.
        require_auth: Si True, le header ``X-API-Key`` est obligatoire.
            Activé automatiquement si ``api_key`` est fourni.
        api_key: Clé API secrète. Peut être fournie via la variable
            d'environnement ``PYWORKFLOW_API_KEY``.
        page_size_default: Nombre d'éléments par page par défaut.
        page_size_max: Nombre maximum d'éléments par page.
        sse_interval: Intervalle de polling SSE en secondes.
        ws_interval: Intervalle de polling WebSocket en secondes.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "workflow.db"
    cors_origins: list[str] = field(default_factory=_default_cors_origins)
    api_key: str | None = field(default_factory=_default_api_key)
    require_auth: bool = False
    rate_limit: str | None = None
    """Limite de débit globale au format slowapi, ex. ``"100/minute"`` ou
    ``"1000/hour"``.  ``None`` désactive le rate limiting (défaut).
    Nécessite ``pip install pyworkflow-engine[api]`` (slowapi inclus)."""
    page_size_default: int = 20
    page_size_max: int = 100
    sse_interval: float = 2.0
    ws_interval: float = 1.0

    def __post_init__(self) -> None:
        # Active require_auth automatiquement si une clé est configurée
        if self.api_key and not self.require_auth:
            self.require_auth = True
