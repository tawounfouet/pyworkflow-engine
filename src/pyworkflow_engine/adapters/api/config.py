"""Configuration de l'API REST PyWorkflow Engine.

Tous les champs ont des valeurs par défaut sensées.
Surchargeable via les flags CLI ``pyworkflow api serve``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class APIConfig:
    """Configuration du serveur API.

    Attributes:
        host: Adresse d'écoute du serveur.
        port: Port du serveur.
        db_path: Chemin du fichier SQLite.
        cors_origins: Liste des origines CORS autorisées.
        require_auth: Si True, l'API Key est obligatoire.
        api_key: Clé API (active l'authentification si fournie).
        page_size_default: Nombre d'éléments par page par défaut.
        page_size_max: Nombre maximum d'éléments par page.
        sse_interval: Intervalle de polling SSE en secondes.
        ws_interval: Intervalle de polling WebSocket en secondes.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "workflow.db"
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    require_auth: bool = False
    api_key: str | None = None
    page_size_default: int = 20
    page_size_max: int = 100
    sse_interval: float = 2.0
    ws_interval: float = 1.0
