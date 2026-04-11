"""WorkflowGUI — application NiceGUI pour PyWorkflow Engine.

Usage::

    from pyworkflow_engine.adapters.gui import WorkflowGUI
    from pyworkflow_engine import WorkflowEngine

    engine = WorkflowEngine(storage=my_backend)
    gui = WorkflowGUI(engine)
    gui.run(port=8080)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import app as _nicegui_app
from nicegui import ui

from pyworkflow_engine.adapters.gui.config import GUIConfig
from pyworkflow_engine.adapters.gui.state import GUIState

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine


class WorkflowGUI:
    """Interface web interactive pour PyWorkflow Engine (NiceGUI).

    Args:
        engine: Instance ``WorkflowEngine`` à superviser.
        config: Configuration optionnelle. Un ``GUIConfig()`` par défaut
                est créé si non fourni.

    Example::

        gui = WorkflowGUI(engine, GUIConfig(port=8080, dark_mode=True))
        gui.run()
    """

    def __init__(
        self,
        engine: WorkflowEngine,
        config: GUIConfig | None = None,
    ) -> None:
        self.engine = engine
        self.config = config or GUIConfig()
        self.state = GUIState(engine=engine, config=self.config)
        self._setup_pages()

    # ── Page registration ─────────────────────────────────────────────────

    def _setup_pages(self) -> None:
        """Enregistre toutes les routes NiceGUI."""
        engine = self.engine
        config = self.config

        # Lazy imports to avoid pulling nicegui at module import time
        from pyworkflow_engine.adapters.gui.views.dashboard import build_dashboard
        from pyworkflow_engine.adapters.gui.views.jobs import (
            build_job_detail_page,
            build_jobs_page,
        )
        from pyworkflow_engine.adapters.gui.views.logs import build_logs_page
        from pyworkflow_engine.adapters.gui.views.run_detail import build_run_detail
        from pyworkflow_engine.adapters.gui.views.run_history import build_run_history
        from pyworkflow_engine.adapters.gui.views.settings import build_settings

        @ui.page("/")
        def _page_root() -> None:
            _apply_theme(config)
            _layout(config, active="/")
            build_dashboard(engine, config)

        @ui.page("/dashboard")
        def _page_dashboard() -> None:
            _apply_theme(config)
            _layout(config, active="/")
            build_dashboard(engine, config)

        @ui.page("/jobs")
        def _page_jobs() -> None:
            _apply_theme(config)
            _layout(config, active="/jobs")
            build_jobs_page(engine, config)

        @ui.page("/job/{job_name}")
        def _page_job_detail(job_name: str) -> None:
            _apply_theme(config)
            _layout(config, active="/jobs")
            build_job_detail_page(engine, config, job_name)

        @ui.page("/runs")
        def _page_runs(job: str = "") -> None:
            _apply_theme(config)
            _layout(config, active="/runs")
            build_run_history(engine, config, job_filter=job or None)

        @ui.page("/run/{run_id}")
        def _page_run_detail(run_id: str) -> None:
            _apply_theme(config)
            _layout(config, active="/runs")
            build_run_detail(engine, config, run_id)

        @ui.page("/logs")
        def _page_logs() -> None:
            _apply_theme(config)
            _layout(config, active="/logs")
            build_logs_page(engine, config)

        @ui.page("/settings")
        def _page_settings() -> None:
            _apply_theme(config)
            _layout(config, active="/settings")
            build_settings(engine, config)

    # ── Public API ────────────────────────────────────────────────────────

    def run(self, **kwargs: object) -> None:
        """Démarre le serveur NiceGUI.

        Les kwargs surchargent les valeurs de ``config``.
        Passe-partout vers ``ui.run()``.

        Args:
            **kwargs: Options ``ui.run()`` : ``host``, ``port``, ``title``,
                      ``dark``, ``reload``, ``show``, ``storage_secret``, …
        """
        params = dict(
            host=self.config.host,
            port=self.config.port,
            title=self.config.title,
            favicon=self.config.favicon,
            dark=self.config.dark_mode,
            reload=self.config.reload,
            show=self.config.show_browser,
            storage_secret=self.config.storage_secret,
        )
        params.update(kwargs)
        ui.run(**params)  # type: ignore[arg-type]


# ── Shared layout helpers ─────────────────────────────────────────────────


def _apply_theme(config: GUIConfig) -> None:
    """Active le mode sombre si configuré."""
    if config.dark_mode:
        ui.dark_mode().enable()


def _layout(config: GUIConfig, active: str = "/") -> None:
    """Injecte l'en-tête, le pied de page et la barre latérale."""
    from pyworkflow_engine.adapters.gui.components.sidebar import sidebar

    with ui.header().classes("items-center justify-between bg-grey-9 text-white"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("account_tree").classes("text-primary text-h5")
            ui.label(config.title).classes("text-subtitle1 text-bold")
        with ui.row().classes("items-center gap-1"):
            _nav_btn("Dashboard", "/", active)
            _nav_btn("Jobs", "/jobs", active)
            _nav_btn("Historique", "/runs", active)
            _nav_btn("Logs", "/logs", active)
            _nav_btn("Paramètres", "/settings", active)

    with ui.footer().classes("bg-grey-9 text-grey-5 text-caption text-center"):
        ui.label("PyWorkflow Engine — GUI adapter (NiceGUI)")


def _nav_btn(label: str, path: str, active: str) -> None:
    is_active = active == path or (path != "/" and active.startswith(path))
    ui.button(label, on_click=lambda p=path: ui.navigate.to(p)).props(
        "flat dense"
    ).classes("text-white" if not is_active else "text-primary text-bold")
