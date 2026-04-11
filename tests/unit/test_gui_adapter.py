"""Tests unitaires pour le GUI adapter NiceGUI (ADR-010).

Stratégie :
- Aucun navigateur, aucun serveur lancé.
- ``nicegui.ui`` est mocké pour les tests de composants/vues afin d'isoler
  la logique Python des appels de rendu NiceGUI.
- Les tests de ``GUIConfig``, ``GUIState`` et des helpers de ``styles/theme``
  ne nécessitent aucun mock : ce sont de la logique pure Python.
- ``WorkflowGUI.__init__`` est testé en mockant ``ui.page`` pour éviter
  tout démarrage de serveur.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


UTC = timezone.utc


def _dt(h: int = 12, m: int = 0, s: int = 0) -> datetime:
    return datetime(2026, 4, 11, h, m, s, tzinfo=UTC)


# ── Minimal fakes (no nicegui dependency) ────────────────────────────────────


class _FakeJobRun:
    def __init__(self, run_id: str = "run-abc-123", job_name: str = "my_job"):
        self.job_run_id = run_id
        self.job_name = job_name
        from pyworkflow_engine.models.enums import RunStatus

        self.status = RunStatus.SUCCESS
        self.start_time = _dt(10, 0, 0)
        self.end_time = _dt(10, 0, 5)
        self.step_runs: list = []


class _FakeStepRun:
    def __init__(
        self,
        step_name: str = "extract",
        status_val: str = "success",
        error: str | None = None,
    ):
        self.step_run_id = "sr-001"
        self.step_name = step_name
        self.job_run_id = "run-abc-123"
        from pyworkflow_engine.models.enums import RunStatus

        self.status = RunStatus(status_val)
        self.start_time = _dt(10, 0, 0)
        self.end_time = _dt(10, 0, 3)
        self.error = error
        self.logs: list = []


class _FakeJob:
    def __init__(self, name: str = "etl_job"):
        self.name = name
        self.steps: list = []
        self.version = "1.0"
        self.description = "Test job"
        self.default_executor = None
        from pyworkflow_engine.models.enums import Priority

        self.priority = Priority.NORMAL


# ── Engine mock ───────────────────────────────────────────────────────────────


def _make_engine(jobs=None, runs=None) -> MagicMock:
    engine = MagicMock()
    engine.list_jobs.return_value = jobs or []
    engine.list_job_runs.return_value = runs or []
    engine.list_executors.return_value = []
    engine.get_job.return_value = None
    engine.get_job_run.return_value = None
    return engine


# ===========================================================================
# GUIConfig
# ===========================================================================


class TestGUIConfig:
    """Tests de la dataclass GUIConfig."""

    def test_defaults(self):
        from pyworkflow_engine.adapters.gui.config import GUIConfig

        cfg = GUIConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8080
        assert cfg.db_path == "workflow.db"
        assert cfg.title == "PyWorkflow Engine"
        assert cfg.dark_mode is True
        assert cfg.reload is False
        assert cfg.show_browser is False
        assert cfg.refresh_interval == 3.0
        assert cfg.favicon == "⚙️"
        assert cfg.storage_secret == "pyworkflow-gui-secret"

    def test_custom_values(self):
        from pyworkflow_engine.adapters.gui.config import GUIConfig

        cfg = GUIConfig(
            host="0.0.0.0", port=9090, dark_mode=False, refresh_interval=5.0
        )
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 9090
        assert cfg.dark_mode is False
        assert cfg.refresh_interval == 5.0

    def test_is_dataclass(self):
        import dataclasses
        from pyworkflow_engine.adapters.gui.config import GUIConfig

        assert dataclasses.is_dataclass(GUIConfig)


# ===========================================================================
# GUIState
# ===========================================================================


class TestGUIState:
    """Tests de GUIState."""

    def test_defaults(self):
        from pyworkflow_engine.adapters.gui.state import GUIState

        state = GUIState()
        assert state.selected_job is None
        assert state.selected_run_id is None
        assert state.notifications == []

    def test_select_job(self):
        from pyworkflow_engine.adapters.gui.state import GUIState

        state = GUIState()
        state.select_job("etl_pipeline")
        assert state.selected_job == "etl_pipeline"

    def test_select_run(self):
        from pyworkflow_engine.adapters.gui.state import GUIState

        state = GUIState()
        state.select_run("run-xyz-999")
        assert state.selected_run_id == "run-xyz-999"

    def test_push_and_pop_notifications(self):
        from pyworkflow_engine.adapters.gui.state import GUIState

        state = GUIState()
        state.push_notification("msg1")
        state.push_notification("msg2")
        assert len(state.notifications) == 2
        popped = state.pop_notifications()
        assert popped == ["msg1", "msg2"]
        assert state.notifications == []

    def test_pop_notifications_empty(self):
        from pyworkflow_engine.adapters.gui.state import GUIState

        state = GUIState()
        assert state.pop_notifications() == []

    def test_engine_and_config_stored(self):
        from pyworkflow_engine.adapters.gui.config import GUIConfig
        from pyworkflow_engine.adapters.gui.state import GUIState

        engine = _make_engine()
        cfg = GUIConfig(port=7070)
        state = GUIState(engine=engine, config=cfg)
        assert state.engine is engine
        assert state.config.port == 7070


# ===========================================================================
# styles/theme helpers
# ===========================================================================


class TestThemeHelpers:
    """Tests des helpers purs de styles/theme.py."""

    def test_fmt_dt_none(self):
        from pyworkflow_engine.adapters.gui.styles.theme import fmt_dt

        assert fmt_dt(None) == "—"

    def test_fmt_dt_value(self):
        from pyworkflow_engine.adapters.gui.styles.theme import fmt_dt

        dt = datetime(2026, 4, 11, 14, 30, 0, tzinfo=UTC)
        result = fmt_dt(dt)
        assert "2026-04-11" in result
        assert "14:30:00" in result

    def test_fmt_ms_none(self):
        from pyworkflow_engine.adapters.gui.styles.theme import fmt_ms

        assert fmt_ms(None) == "—"

    def test_fmt_ms_millis(self):
        from pyworkflow_engine.adapters.gui.styles.theme import fmt_ms

        assert fmt_ms(500) == "500 ms"

    def test_fmt_ms_seconds(self):
        from pyworkflow_engine.adapters.gui.styles.theme import fmt_ms

        assert "s" in fmt_ms(2500)

    def test_fmt_ms_minutes(self):
        from pyworkflow_engine.adapters.gui.styles.theme import fmt_ms

        assert "min" in fmt_ms(120_000)

    def test_status_badge_html_contains_label(self):
        from pyworkflow_engine.adapters.gui.styles.theme import status_badge_html
        from pyworkflow_engine.models.enums import RunStatus

        html = status_badge_html(RunStatus.SUCCESS)
        assert "SUCCESS" in html
        assert "<span" in html

    def test_status_badge_html_all_statuses(self):
        """Tous les statuts de RunStatus doivent produire du HTML sans exception."""
        from pyworkflow_engine.adapters.gui.styles.theme import status_badge_html
        from pyworkflow_engine.models.enums import RunStatus

        for status in RunStatus:
            html = status_badge_html(status)
            assert "<span" in html, f"status_badge_html failed for {status}"

    def test_status_color_covers_all(self):
        from pyworkflow_engine.adapters.gui.styles.theme import STATUS_COLOR
        from pyworkflow_engine.models.enums import RunStatus

        for status in RunStatus:
            assert status in STATUS_COLOR, f"Missing STATUS_COLOR entry for {status}"

    def test_status_icon_covers_all(self):
        from pyworkflow_engine.adapters.gui.styles.theme import STATUS_ICON
        from pyworkflow_engine.models.enums import RunStatus

        for status in RunStatus:
            assert status in STATUS_ICON, f"Missing STATUS_ICON entry for {status}"

    def test_status_label_covers_all(self):
        from pyworkflow_engine.adapters.gui.styles.theme import STATUS_LABEL
        from pyworkflow_engine.models.enums import RunStatus

        for status in RunStatus:
            assert status in STATUS_LABEL, f"Missing STATUS_LABEL entry for {status}"

    def test_styles_init_re_exports(self):
        """styles/__init__.py doit ré-exporter tous les helpers."""
        from pyworkflow_engine.adapters.gui import styles
        from pyworkflow_engine.adapters.gui.styles import (
            STATUS_COLOR,
            STATUS_ICON,
            STATUS_LABEL,
            fmt_dt,
            fmt_ms,
            status_badge_html,
        )

        assert callable(fmt_dt)
        assert callable(fmt_ms)
        assert callable(status_badge_html)
        assert isinstance(STATUS_COLOR, dict)


# ===========================================================================
# components — pure-Python data helpers (no ui calls)
# ===========================================================================


class TestJobTableData:
    """Tests du helper _build_row_data de job_table."""

    def test_empty_engine(self):
        from pyworkflow_engine.adapters.gui.components.job_table import _build_row_data

        engine = _make_engine(jobs=[])
        rows = _build_row_data(engine)
        assert rows == []

    def test_row_fields(self):
        from pyworkflow_engine.adapters.gui.components.job_table import _build_row_data

        job = _FakeJob("pipeline_a")
        engine = _make_engine(jobs=[job])
        rows = _build_row_data(engine)
        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "pipeline_a"
        assert row["steps"] == 0
        assert row["version"] == "1.0"
        assert row["description"] == "Test job"

    def test_multiple_jobs(self):
        from pyworkflow_engine.adapters.gui.components.job_table import _build_row_data

        jobs = [_FakeJob(f"job_{i}") for i in range(5)]
        engine = _make_engine(jobs=jobs)
        rows = _build_row_data(engine)
        assert len(rows) == 5
        assert [r["name"] for r in rows] == [f"job_{i}" for i in range(5)]


class TestRunTableData:
    """Tests du helper _build_row_data de run_table."""

    def test_empty_runs(self):
        from pyworkflow_engine.adapters.gui.components.run_table import _build_row_data

        rows = _build_row_data([])
        assert rows == []

    def test_row_fields(self):
        from pyworkflow_engine.adapters.gui.components.run_table import _build_row_data

        run = _FakeJobRun("run-abc-000-111-222-333", "etl")
        rows = _build_row_data([run])
        assert len(rows) == 1
        row = rows[0]
        # Full ID stored privately for click handler
        assert row["_run_id"] == "run-abc-000-111-222-333"
        # Displayed ID is truncated
        assert "…" in row["run_id"]
        assert row["job"] == "etl"
        assert "2026" in row["started"]
        assert row["duration"] != "—"  # both start and end set

    def test_duration_none_when_no_times(self):
        from pyworkflow_engine.adapters.gui.components.run_table import _build_row_data

        run = _FakeJobRun()
        run.start_time = None
        run.end_time = None
        rows = _build_row_data([run])
        assert rows[0]["duration"] == "—"

    def test_status_html_contains_span(self):
        from pyworkflow_engine.adapters.gui.components.run_table import _build_row_data

        run = _FakeJobRun()
        rows = _build_row_data([run])
        assert "<span" in rows[0]["status_html"]


class TestStepProgressData:
    """Tests du helper _build_row_data de step_progress."""

    def test_empty(self):
        from pyworkflow_engine.adapters.gui.components.step_progress import (
            _build_row_data,
        )

        assert _build_row_data([]) == []

    def test_row_fields(self):
        from pyworkflow_engine.adapters.gui.components.step_progress import (
            _build_row_data,
        )

        sr = _FakeStepRun("load", "success")
        rows = _build_row_data([sr])
        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "load"
        assert row["error"] == ""
        assert "<span" in row["status_html"]

    def test_error_field_populated(self):
        from pyworkflow_engine.adapters.gui.components.step_progress import (
            _build_row_data,
        )

        sr = _FakeStepRun("transform", "failed", error="NullPointerException")
        rows = _build_row_data([sr])
        assert rows[0]["error"] == "NullPointerException"

    def test_duration_calculated(self):
        from pyworkflow_engine.adapters.gui.components.step_progress import (
            _build_row_data,
        )

        sr = _FakeStepRun()
        sr.start_time = _dt(10, 0, 0)
        sr.end_time = _dt(10, 0, 3)
        rows = _build_row_data([sr])
        assert rows[0]["duration"] != "—"


class TestDagGraph:
    """Tests du helper _build_diagram de dag_graph."""

    def test_no_steps_produces_header(self):
        from pyworkflow_engine.adapters.gui.components.dag_graph import _build_diagram

        job = _FakeJob()
        diagram = _build_diagram(job)
        assert "graph LR" in diagram

    def test_step_without_deps_links_start(self):
        from pyworkflow_engine.adapters.gui.components.dag_graph import _build_diagram

        job = _FakeJob()
        step = MagicMock()
        step.name = "extract"
        step.dependencies = []
        job.steps = [step]
        diagram = _build_diagram(job)
        assert "START" in diagram
        assert "extract" in diagram

    def test_dep_produces_edge(self):
        from pyworkflow_engine.adapters.gui.components.dag_graph import _build_diagram

        job = _FakeJob()
        s1 = MagicMock()
        s1.name = "extract"
        s1.dependencies = []
        s2 = MagicMock()
        s2.name = "transform"
        s2.dependencies = ["extract"]
        job.steps = [s1, s2]
        diagram = _build_diagram(job)
        assert "extract" in diagram
        assert "transform" in diagram
        assert "-->" in diagram

    def test_mermaid_id_sanitisation(self):
        from pyworkflow_engine.adapters.gui.components.dag_graph import _mid

        assert _mid("step-one") == "step_one"
        assert _mid("step one") == "step_one"
        assert _mid("step.one") == "step_one"
        assert _mid("a-b c.d") == "a_b_c_d"


# ===========================================================================
# WorkflowGUI constructor (mock ui.page)
# ===========================================================================


class TestWorkflowGUI:
    """Tests du constructeur WorkflowGUI (sans lancer de serveur)."""

    def _make_gui(self, engine=None):
        from pyworkflow_engine.adapters.gui.config import GUIConfig
        from pyworkflow_engine.adapters.gui.app import WorkflowGUI

        cfg = GUIConfig(port=8888)
        eng = engine or _make_engine()
        with patch("pyworkflow_engine.adapters.gui.app.ui") as mock_ui:
            mock_ui.page = MagicMock(return_value=lambda f: f)
            gui = WorkflowGUI(eng, cfg)
        return gui, eng, cfg

    def test_constructor_stores_engine_and_config(self):
        gui, engine, cfg = self._make_gui()
        assert gui.engine is engine
        assert gui.config is cfg
        assert gui.config.port == 8888

    def test_constructor_creates_state(self):
        from pyworkflow_engine.adapters.gui.state import GUIState

        gui, engine, cfg = self._make_gui()
        assert isinstance(gui.state, GUIState)
        assert gui.state.engine is engine
        assert gui.state.config is cfg

    def test_default_config_created_when_none(self):
        from pyworkflow_engine.adapters.gui.app import WorkflowGUI
        from pyworkflow_engine.adapters.gui.config import GUIConfig

        with patch("pyworkflow_engine.adapters.gui.app.ui") as mock_ui:
            mock_ui.page = MagicMock(return_value=lambda f: f)
            gui = WorkflowGUI(_make_engine())
        assert isinstance(gui.config, GUIConfig)
        assert gui.config.port == 8080  # default


# ===========================================================================
# __init__.py lazy-import guard
# ===========================================================================


class TestGuiInitLazyImport:
    def test_getattr_workflowgui_returns_class(self):
        import pyworkflow_engine.adapters.gui as gui_pkg

        cls = gui_pkg.WorkflowGUI
        assert cls.__name__ == "WorkflowGUI"

    def test_getattr_unknown_raises_attribute_error(self):
        import pyworkflow_engine.adapters.gui as gui_pkg

        with pytest.raises(AttributeError):
            _ = gui_pkg.NonExistentSymbol  # type: ignore[attr-defined]


# ===========================================================================
# CLI gui command
# ===========================================================================


class TestGuiCliCommand:
    """Tests de la sous-commande CLI 'pyworkflow gui'."""

    def test_module_importable(self):
        from pyworkflow_engine.adapters.cli.commands import gui

        assert hasattr(gui, "app")
        assert hasattr(gui, "launch_gui")

    def test_app_is_typer(self):
        import typer
        from pyworkflow_engine.adapters.cli.commands.gui import app

        assert isinstance(app, typer.Typer)

    def test_registered_in_main(self):
        """Le sous-command 'gui' doit apparaître dans la liste des commandes."""
        from pyworkflow_engine.adapters.cli.main import app as cli_app

        command_names = [c.name for c in cli_app.registered_groups]
        assert "gui" in command_names

    def test_gui_help_output(self):
        """Le sous-command 'gui' doit afficher une aide correcte."""
        from typer.testing import CliRunner
        from pyworkflow_engine.adapters.cli.main import app as cli_app

        runner = CliRunner()
        result = runner.invoke(cli_app, ["gui", "--help"])
        assert result.exit_code == 0
        output = result.output.lower()
        # Must mention port and host options
        assert "--port" in result.output
        assert "--host" in result.output


# ===========================================================================
# views/__init__.py re-exports
# ===========================================================================


class TestViewsInit:
    def test_all_builders_importable(self):
        from pyworkflow_engine.adapters.gui.views import (
            build_dashboard,
            build_job_detail_page,
            build_jobs_page,
            build_run_detail,
            build_run_history,
            build_settings,
        )

        for fn in (
            build_dashboard,
            build_job_detail_page,
            build_jobs_page,
            build_run_detail,
            build_run_history,
            build_settings,
        ):
            assert callable(fn)


# ===========================================================================
# components/__init__.py re-exports
# ===========================================================================


class TestComponentsInit:
    def test_public_api_importable(self):
        from pyworkflow_engine.adapters.gui.components import (
            status_badge,
            page_toolbar,
            sidebar,
        )

        assert callable(status_badge)
        assert callable(page_toolbar)
        assert callable(sidebar)
