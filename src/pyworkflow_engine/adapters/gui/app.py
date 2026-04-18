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
        self._wire_ai_storage()
        self._register_known_pipelines()
        self._setup_pages()

    def _wire_ai_storage(self) -> None:
        """Branche UnifiedStorage sur le moteur si un fichier DB est configuré."""
        # ...existing code...

    def _register_known_pipelines(self) -> None:
        """Enregistre toutes les pipelines connues dans ``pl_pipelines``.

        Importe chaque module pipeline, reconstruit l'objet ``Pipeline`` via
        ``build_pipeline()`` (ou ``@pipeline.build()``), et persiste la
        définition dans le backend — sans exécuter quoi que ce soit.

        Échoue silencieusement si un module n'est pas importable (dépendances
        optionnelles manquantes, jobs non installés, etc.).
        """
        if not hasattr(self.engine, "save_pipeline"):
            return
        if getattr(self.engine, "_storage", None) is None:
            return

        _candidates = [
            # (module, attribute, mode)
            # mode "runner"  → attribute is a build_pipeline() fn returning PipelineRunner
            # mode "builder" → attribute is a PipelineBuilder (has .build())
            # mode "factory" → attribute is a callable returning a Pipeline directly
            ("pipelines.daily.books_to_dwh", "build_pipeline", "runner"),
            ("pipelines.daily.stripe_to_dwh", "build_pipeline", "runner"),
            ("pipelines.daily.strava_daily_coaching", "build_pipeline", "factory"),
            ("pipelines.weekly.countries_to_dwh", "countries_to_dwh", "builder"),
        ]

        import importlib
        import logging

        _log = logging.getLogger("pyworkflow_engine.gui.app")

        for module_path, fn_name, mode in _candidates:
            try:
                mod = importlib.import_module(module_path)
                obj = getattr(mod, fn_name, None)
                if obj is None:
                    continue

                if mode == "runner":
                    # build_pipeline() → PipelineRunner → .to_pipeline()
                    pipeline_obj = obj().to_pipeline()
                elif mode == "builder":
                    # PipelineBuilder decorated with @pipeline → .build()
                    pipeline_obj = obj.build()
                else:
                    # factory: build_pipeline() returns a Pipeline directly
                    pipeline_obj = obj()

                self.engine.save_pipeline(pipeline_obj)
                _log.debug("Pipeline enregistrée : %s", pipeline_obj.name)
            except Exception as exc:  # noqa: BLE001
                _log.debug(
                    "Impossible d'enregistrer la pipeline %s : %s", module_path, exc
                )

    # ── Page registration ─────────────────────────────────────────────────

    def _setup_pages(self) -> None:
        """Enregistre toutes les routes NiceGUI."""
        engine = self.engine
        config = self.config

        # Lazy imports to avoid pulling nicegui at module import time
        from pyworkflow_engine.adapters.gui.views.agents import (
            build_agent_detail_page,
            build_agents_page,
        )
        from pyworkflow_engine.adapters.gui.views.conversations import (
            build_conversation_detail,
            build_conversations_page,
        )
        from pyworkflow_engine.adapters.gui.views.dashboard import build_dashboard
        from pyworkflow_engine.adapters.gui.views.executions import (
            build_execution_detail,
            build_executions_page,
        )
        from pyworkflow_engine.adapters.gui.views.jobs import (
            build_job_detail_page,
            build_jobs_page,
        )
        from pyworkflow_engine.adapters.gui.views.logs import build_logs_page
        from pyworkflow_engine.adapters.gui.views.pipeline_runs import (
            build_pipeline_run_detail,
            build_pipeline_runs_page,
        )
        from pyworkflow_engine.adapters.gui.views.pipelines import (
            build_pipeline_detail_page,
            build_pipelines_page,
        )
        from pyworkflow_engine.adapters.gui.views.run_detail import build_run_detail
        from pyworkflow_engine.adapters.gui.views.run_history import build_run_history
        from pyworkflow_engine.adapters.gui.views.scheduler import build_scheduler_page
        from pyworkflow_engine.adapters.gui.views.settings import build_settings

        # ── Workflow ──────────────────────────────────────────────────────

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

        @ui.page("/scheduler")
        def _page_scheduler() -> None:
            _apply_theme(config)
            _layout(config, active="/scheduler")
            build_scheduler_page(engine, config)

        # ── Pipelines ─────────────────────────────────────────────────────

        @ui.page("/pipelines")
        def _page_pipelines() -> None:
            _apply_theme(config)
            _layout(config, active="/pipelines")
            build_pipelines_page(engine, config)

        @ui.page("/pipeline/{pipeline_name}")
        def _page_pipeline_detail(pipeline_name: str) -> None:
            _apply_theme(config)
            _layout(config, active="/pipelines")
            build_pipeline_detail_page(engine, config, pipeline_name)

        @ui.page("/pipeline-runs")
        def _page_pipeline_runs(pipeline: str = "") -> None:
            _apply_theme(config)
            _layout(config, active="/pipeline-runs")
            build_pipeline_runs_page(engine, config, pipeline_filter=pipeline or None)

        @ui.page("/pipeline-run/{run_id}")
        def _page_pipeline_run_detail(run_id: str) -> None:
            _apply_theme(config)
            _layout(config, active="/pipeline-runs")
            build_pipeline_run_detail(engine, config, run_id)

        # ── IA ────────────────────────────────────────────────────────────

        @ui.page("/agents")
        def _page_agents() -> None:
            _apply_theme(config)
            _layout(config, active="/agents")
            build_agents_page(engine, config)

        @ui.page("/agent/{agent_id}")
        def _page_agent_detail(agent_id: str) -> None:
            _apply_theme(config)
            _layout(config, active="/agents")
            build_agent_detail_page(engine, config, agent_id)

        @ui.page("/executions")
        def _page_executions(agent: str = "") -> None:
            _apply_theme(config)
            _layout(config, active="/executions")
            build_executions_page(engine, config, agent_filter=agent or None)

        @ui.page("/execution/{exec_id}")
        def _page_execution_detail(exec_id: str) -> None:
            _apply_theme(config)
            _layout(config, active="/executions")
            build_execution_detail(engine, config, exec_id)

        @ui.page("/conversations")
        def _page_conversations(agent: str = "") -> None:
            _apply_theme(config)
            _layout(config, active="/conversations")
            build_conversations_page(engine, config, agent_filter=agent or None)

        @ui.page("/conversation/{conv_id}")
        def _page_conversation_detail(conv_id: str) -> None:
            _apply_theme(config)
            _layout(config, active="/conversations")
            build_conversation_detail(engine, config, conv_id)

        # ── Misc ──────────────────────────────────────────────────────────

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
    with ui.header().classes(
        "items-center justify-between bg-grey-9 text-white q-px-md"
    ):
        with ui.row().classes("items-center gap-2"):
            ui.icon("account_tree").classes("text-primary text-h5")
            ui.label(config.title).classes("text-subtitle1 text-bold")
        # ── Navigation principale ──────────────────────────────────────────
        with ui.row().classes("items-center gap-0"):
            # Workflow
            _nav_btn("Dashboard", "/", active, icon="dashboard")
            _nav_btn("Jobs", "/jobs", active, icon="work")
            _nav_btn("Historique", "/runs", active, icon="history")
            _nav_btn("Logs", "/logs", active, icon="article")
            _nav_btn("Scheduler", "/scheduler", active, icon="schedule")
            _nav_separator()
            # Pipelines
            _nav_btn("Pipelines", "/pipelines", active, icon="account_tree")
            _nav_btn("Pipeline Runs", "/pipeline-runs", active, icon="timeline")
            _nav_separator()
            # IA
            _nav_btn("Agents", "/agents", active, icon="smart_toy")
            _nav_btn("Exécutions", "/executions", active, icon="bolt")
            _nav_btn("Conversations", "/conversations", active, icon="chat")
            _nav_separator()
            # Misc
            _nav_btn("Paramètres", "/settings", active, icon="settings")

    with ui.footer().classes("bg-grey-9 text-grey-5 text-caption text-center"):
        ui.label("PyWorkflow Engine — GUI adapter (NiceGUI)")


def _nav_btn(label: str, path: str, active: str, icon: str = "") -> None:
    is_active = active == path or (path != "/" and active.startswith(path))
    btn = ui.button(
        label,
        icon=icon or None,
        on_click=lambda p=path: ui.navigate.to(p),
    ).props("flat dense no-caps")
    btn.classes("text-primary text-bold" if is_active else "text-grey-4")


def _nav_separator() -> None:
    ui.label("·").classes("text-grey-6 q-mx-xs")
