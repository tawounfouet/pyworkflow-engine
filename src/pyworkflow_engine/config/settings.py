"""
pyworkflow_engine.config.settings — configuration centralisée style Django.

Toutes les valeurs sont lisibles comme attributs du singleton ``settings``.
Elles peuvent être surchargées par des variables d'environnement ou de façon
programmatique via ``settings.configure(**kwargs)``.

Usage minimal (valeurs par défaut) :

    from pyworkflow_engine.config.settings import settings
    engine = WorkflowEngine(config=settings.workflow_config)

Surcharge programmatique (avant toute autre utilisation) :

    settings.configure(
        DATABASE="prod.db",
        LOGGING_LEVEL="WARNING",
        ENGINE_PARALLEL=True,
        ENGINE_MAX_WORKERS=8,
    )

Surcharge par variables d'environnement :

    PYWORKFLOW_DB=prod.db
    PYWORKFLOW_LOG_LEVEL=WARNING
    PYWORKFLOW_LOG_DIR=logs
    PYWORKFLOW_LOG_TO_DB=true
    PYWORKFLOW_ENGINE_PARALLEL=true
    PYWORKFLOW_ENGINE_MAX_WORKERS=8
    PYWORKFLOW_GUI_HOST=0.0.0.0
    PYWORKFLOW_GUI_PORT=9090
    PYWORKFLOW_GUI_DARK_MODE=false
    PYWORKFLOW_GUI_REFRESH_INTERVAL=5.0

Les variables d'environnement sont lues à l'instanciation et peuvent être
écrasées par ``settings.configure()``.
"""

from __future__ import annotations

import os
from typing import Any


def _bool(val: str | bool | None, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(val: str | int | None, default: int) -> int:
    if isinstance(val, int):
        return val
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _float(val: str | float | None, default: float) -> float:
    if isinstance(val, float):
        return val
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class Settings:
    """Singleton de configuration globale de pyworkflow-engine.

    Attributes:
        DATABASE: Chemin du fichier SQLite partagé.
        LOGGING_LEVEL: Niveau de log (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        LOGGING_FORMAT: Format de sortie console (``"text"`` ou ``"json"``).
        LOGGING_DIR: Dossier pour les fichiers de log rotatifs. ``None`` =
            pas de fichier.
        LOGGING_TO_DB: Persiste les logs dans la table ``workflow_logs`` de
            la DB si ``True``.
        LOGGING_FILE_MAX_MB: Taille max d'un fichier de log avant rotation.
        LOGGING_FILE_BACKUP_COUNT: Nombre de fichiers de backup conservés.
        ENGINE_PARALLEL: Active l'exécution parallèle des steps indépendants.
        ENGINE_MAX_WORKERS: Nombre maximum de workers parallèles.
        ENGINE_MAX_RETRIES: Nombre maximum de retries par step.
        ENGINE_TIMEOUT: Timeout global par step (secondes). ``None`` = illimité.
        GUI_HOST: Adresse d'écoute du serveur NiceGUI.
        GUI_PORT: Port du serveur NiceGUI.
        GUI_DARK_MODE: Active le thème sombre par défaut.
        GUI_TITLE: Titre affiché dans l'onglet navigateur.
        GUI_FAVICON: Emoji ou URL de la favicon.
        GUI_REFRESH_INTERVAL: Intervalle de rafraîchissement automatique (s).
        GUI_SHOW_BROWSER: Ouvre automatiquement le navigateur au démarrage.
        GUI_RELOAD: Hot-reload (développement uniquement).
        GUI_STORAGE_SECRET: Clé secrète pour le stockage de session NiceGUI.
    """

    # ── Persistence ──────────────────────────────────────────────────────────
    DATABASE: str | None = None

    # ── Logging ──────────────────────────────────────────────────────────────
    LOGGING_LEVEL: str = "INFO"
    LOGGING_FORMAT: str = "text"
    LOGGING_DIR: str | None = None
    LOGGING_TO_DB: bool = False
    LOGGING_FILE_MAX_MB: int = 10
    LOGGING_FILE_BACKUP_COUNT: int = 5

    # ── Engine ───────────────────────────────────────────────────────────────
    ENGINE_PARALLEL: bool = False
    ENGINE_MAX_WORKERS: int = 4
    ENGINE_MAX_RETRIES: int = 3
    ENGINE_TIMEOUT: float | None = None

    # ── GUI ──────────────────────────────────────────────────────────────────
    GUI_HOST: str = "127.0.0.1"
    GUI_PORT: int = 8080
    GUI_DARK_MODE: bool = True
    GUI_TITLE: str = "PyWorkflow Engine"
    GUI_FAVICON: str = "⚙️"
    GUI_REFRESH_INTERVAL: float = 3.0
    GUI_SHOW_BROWSER: bool = False
    GUI_RELOAD: bool = False
    GUI_STORAGE_SECRET: str = "pyworkflow-gui-secret"

    def __init__(self) -> None:
        self._apply_env()

    # ── Surcharge ─────────────────────────────────────────────────────────────

    def configure(self, **kwargs: Any) -> None:
        """Surcharge programmatique des paramètres.

        Doit être appelé avant toute utilisation de ``workflow_config`` ou
        ``gui_config``, idéalement en début de module.

        Args:
            **kwargs: Paires ``NOM_PARAMETRE=valeur`` correspondant aux
                attributs de classe (ex. ``DATABASE="prod.db"``).

        Raises:
            AttributeError: Si un paramètre inconnu est passé.

        Examples:
            >>> settings.configure(DATABASE="test.db", ENGINE_PARALLEL=True)
        """
        _valid = {k for k in vars(type(self)) if k.isupper()}
        for key, value in kwargs.items():
            if key not in _valid:
                raise AttributeError(
                    f"Settings has no attribute '{key}'. "
                    f"Valid keys: {sorted(_valid)}"
                )
            setattr(self, key, value)

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def workflow_config(self):
        """Retourne un :class:`WorkflowConfig` construit depuis les settings courants.

        Returns:
            WorkflowConfig: Configuration complète du moteur.

        Examples:
            >>> from pyworkflow_engine.config.settings import settings
            >>> cfg = settings.workflow_config
            >>> cfg.persistence.db_path == settings.DATABASE
            True
        """
        from pyworkflow_engine.config.base import WorkflowConfig
        from pyworkflow_engine.config.engine import EngineConfig
        from pyworkflow_engine.config.executor import ExecutorConfig
        from pyworkflow_engine.config.logging import LoggingConfig
        from pyworkflow_engine.config.storage import StorageConfig

        return WorkflowConfig(
            engine=EngineConfig(
                parallel=self.ENGINE_PARALLEL,
                max_workers=(
                    self.ENGINE_MAX_WORKERS if self.ENGINE_MAX_WORKERS != 4 else None
                ),
                max_retries=self.ENGINE_MAX_RETRIES,
                default_timeout_seconds=self.ENGINE_TIMEOUT,
            ),
            executor=ExecutorConfig(
                max_workers=self.ENGINE_MAX_WORKERS,
            ),
            logging=LoggingConfig(
                level=self.LOGGING_LEVEL,
                format=self.LOGGING_FORMAT,
                log_dir=self.LOGGING_DIR,
                log_file_max_mb=self.LOGGING_FILE_MAX_MB,
                log_file_backup_count=self.LOGGING_FILE_BACKUP_COUNT,
                log_to_db=self.LOGGING_TO_DB,
            ),
            storage=StorageConfig(
                db_path=self.DATABASE,
            ),
        )

    @property
    def gui_config(self):
        """Retourne un :class:`GUIConfig` construit depuis les settings courants.

        Returns:
            GUIConfig: Configuration du serveur NiceGUI.

        Examples:
            >>> from pyworkflow_engine.config.settings import settings
            >>> cfg = settings.gui_config
            >>> cfg.port == settings.GUI_PORT
            True
        """
        from pyworkflow_engine.adapters.gui.config import GUIConfig

        db = self.DATABASE or "workflow.db"
        return GUIConfig(
            host=self.GUI_HOST,
            port=self.GUI_PORT,
            db_path=db,
            title=self.GUI_TITLE,
            dark_mode=self.GUI_DARK_MODE,
            reload=self.GUI_RELOAD,
            show_browser=self.GUI_SHOW_BROWSER,
            refresh_interval=self.GUI_REFRESH_INTERVAL,
            favicon=self.GUI_FAVICON,
            storage_secret=self.GUI_STORAGE_SECRET,
        )

    # ── Env vars ──────────────────────────────────────────────────────────────

    def _apply_env(self) -> None:
        """Lit les variables d'environnement PYWORKFLOW_* et met à jour les attributs."""
        _e = os.environ.get

        db = _e("PYWORKFLOW_DB")
        if db:
            self.DATABASE = db

        log_level = _e("PYWORKFLOW_LOG_LEVEL")
        if log_level:
            self.LOGGING_LEVEL = log_level.upper()

        log_format = _e("PYWORKFLOW_LOG_FORMAT")
        if log_format:
            self.LOGGING_FORMAT = log_format.lower()

        log_dir = _e("PYWORKFLOW_LOG_DIR")
        if log_dir:
            self.LOGGING_DIR = log_dir

        log_to_db = _e("PYWORKFLOW_LOG_TO_DB")
        if log_to_db is not None:
            self.LOGGING_TO_DB = _bool(log_to_db)

        log_max_mb = _e("PYWORKFLOW_LOG_FILE_MAX_MB")
        if log_max_mb is not None:
            self.LOGGING_FILE_MAX_MB = _int(log_max_mb, self.LOGGING_FILE_MAX_MB)

        log_backup = _e("PYWORKFLOW_LOG_FILE_BACKUP_COUNT")
        if log_backup is not None:
            self.LOGGING_FILE_BACKUP_COUNT = _int(
                log_backup, self.LOGGING_FILE_BACKUP_COUNT
            )

        parallel = _e("PYWORKFLOW_ENGINE_PARALLEL")
        if parallel is not None:
            self.ENGINE_PARALLEL = _bool(parallel)

        max_workers = _e("PYWORKFLOW_ENGINE_MAX_WORKERS")
        if max_workers is not None:
            self.ENGINE_MAX_WORKERS = _int(max_workers, self.ENGINE_MAX_WORKERS)

        max_retries = _e("PYWORKFLOW_ENGINE_MAX_RETRIES")
        if max_retries is not None:
            self.ENGINE_MAX_RETRIES = _int(max_retries, self.ENGINE_MAX_RETRIES)

        timeout = _e("PYWORKFLOW_ENGINE_TIMEOUT")
        if timeout is not None:
            self.ENGINE_TIMEOUT = _float(timeout, 0.0) or None

        gui_host = _e("PYWORKFLOW_GUI_HOST")
        if gui_host:
            self.GUI_HOST = gui_host

        gui_port = _e("PYWORKFLOW_GUI_PORT")
        if gui_port is not None:
            self.GUI_PORT = _int(gui_port, self.GUI_PORT)

        gui_dark = _e("PYWORKFLOW_GUI_DARK_MODE")
        if gui_dark is not None:
            self.GUI_DARK_MODE = _bool(gui_dark, self.GUI_DARK_MODE)

        gui_refresh = _e("PYWORKFLOW_GUI_REFRESH_INTERVAL")
        if gui_refresh is not None:
            self.GUI_REFRESH_INTERVAL = _float(gui_refresh, self.GUI_REFRESH_INTERVAL)

        gui_title = _e("PYWORKFLOW_GUI_TITLE")
        if gui_title:
            self.GUI_TITLE = gui_title

        gui_port_val = _e("PYWORKFLOW_GUI_SHOW_BROWSER")
        if gui_port_val is not None:
            self.GUI_SHOW_BROWSER = _bool(gui_port_val)

        gui_secret = _e("PYWORKFLOW_GUI_STORAGE_SECRET")
        if gui_secret:
            self.GUI_STORAGE_SECRET = gui_secret

    def __repr__(self) -> str:
        lines = [
            f"DATABASE={self.DATABASE!r}",
            f"LOGGING_LEVEL={self.LOGGING_LEVEL!r}",
            f"LOGGING_FORMAT={self.LOGGING_FORMAT!r}",
            f"LOGGING_DIR={self.LOGGING_DIR!r}",
            f"LOGGING_TO_DB={self.LOGGING_TO_DB!r}",
            f"ENGINE_PARALLEL={self.ENGINE_PARALLEL!r}",
            f"ENGINE_MAX_WORKERS={self.ENGINE_MAX_WORKERS!r}",
            f"ENGINE_MAX_RETRIES={self.ENGINE_MAX_RETRIES!r}",
            f"ENGINE_TIMEOUT={self.ENGINE_TIMEOUT!r}",
            f"GUI_HOST={self.GUI_HOST!r}",
            f"GUI_PORT={self.GUI_PORT!r}",
            f"GUI_DARK_MODE={self.GUI_DARK_MODE!r}",
            f"GUI_REFRESH_INTERVAL={self.GUI_REFRESH_INTERVAL!r}",
        ]
        body = "\n  ".join(lines)
        return f"Settings(\n  {body}\n)"


#: Singleton global — importez-le directement.
settings = Settings()
