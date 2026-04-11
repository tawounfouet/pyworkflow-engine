"""Configuration du GUI adapter NiceGUI."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GUIConfig:
    """Configuration du serveur NiceGUI.

    Attributes:
        host: Adresse d'écoute.
        port: Port du serveur.
        db_path: Chemin SQLite (mode standalone sans --app).
        title: Titre affiché dans l'onglet navigateur.
        dark_mode: Active le thème sombre par défaut.
        reload: Hot-reload (développement).
        show_browser: Ouvre automatiquement le navigateur au démarrage.
        refresh_interval: Intervalle de rafraîchissement automatique (secondes).
        favicon: Emoji ou URL de la favicon.
    """

    host: str = "127.0.0.1"
    port: int = 8080
    db_path: str = "workflow.db"
    title: str = "PyWorkflow Engine"
    dark_mode: bool = True
    reload: bool = False
    show_browser: bool = False
    refresh_interval: float = 3.0
    favicon: str = "⚙️"
    storage_secret: str = "pyworkflow-gui-secret"
