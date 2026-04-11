"""Vue Dashboard — vue d'ensemble jobs + runs récents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.job_table import (
    job_table,
    refresh_job_table,
)
from pyworkflow_engine.adapters.gui.components.run_table import (
    run_table,
    refresh_run_table,
)
from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.models.enums import RunStatus, SUSPENDED_STATUSES

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_dashboard(engine: WorkflowEngine, config: GUIConfig) -> None:
    """Construit la page Dashboard (route / et /dashboard)."""
    page_toolbar("Dashboard", icon="dashboard", icon_color="primary")

    # ── KPI cards ──────────────────────────────────────────────────────────
    with ui.row().classes("w-full gap-4 q-mb-md"):
        kpi_jobs = _kpi_card("Jobs", "work", "primary")
        kpi_runs = _kpi_card("Runs total", "bar_chart", "secondary")
        kpi_running = _kpi_card("En cours", "sync", "warning")
        kpi_suspended = _kpi_card("Suspendus", "pause_circle", "info")

    # ── Jobs table ─────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center q-mb-sm"):
            ui.icon("work").classes("text-primary text-h6")
            ui.label("Jobs enregistrés").classes("text-h6 q-ml-sm")
        jobs_grid = job_table(
            engine,
            on_select=lambda name: ui.navigate.to(f"/job/{name}"),
        )

    # ── Recent runs table ──────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center q-mb-sm"):
            ui.icon("history").classes("text-secondary text-h6")
            ui.label("Runs récents").classes("text-h6 q-ml-sm")
        try:
            initial_runs = engine.list_job_runs(limit=20)
        except Exception:
            initial_runs = []
        runs_grid = run_table(
            initial_runs,
            on_select=lambda run_id: ui.navigate.to(f"/run/{run_id}"),
        )

    # ── Refresh logic ──────────────────────────────────────────────────────
    def _update_kpis(jobs: list, runs: list) -> None:
        running = sum(1 for r in runs if r.status == RunStatus.RUNNING)
        suspended = sum(1 for r in runs if r.status in SUSPENDED_STATUSES)
        kpi_jobs.set_text(str(len(jobs)))
        kpi_runs.set_text(str(len(runs)))
        kpi_running.set_text(str(running))
        kpi_suspended.set_text(str(suspended))

    def refresh() -> None:
        jobs = engine.list_jobs()
        try:
            runs = engine.list_job_runs(limit=20)
        except Exception:
            runs = []
        _update_kpis(jobs, runs)
        refresh_job_table(jobs_grid, engine)
        refresh_run_table(runs_grid, runs)

    # Populate KPI labels immediately (labels are server-side, safe to set now).
    # The grids already have rowData from their constructors — don't touch them
    # before the client websocket is open or AG Grid will show "No Rows To Show".
    try:
        _initial_jobs = engine.list_jobs()
        _initial_runs = engine.list_job_runs(limit=20)
    except Exception:
        _initial_jobs, _initial_runs = [], []
    _update_kpis(_initial_jobs, _initial_runs)

    ui.timer(config.refresh_interval, refresh)


def _kpi_card(title: str, icon: str, color: str) -> ui.label:
    """Crée une petite carte KPI et retourne le label de valeur."""
    with ui.card().classes("flex-1 min-w-[140px]"):
        with ui.column().classes("gap-1"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon).classes(f"text-{color} text-h5")
                ui.label(title).classes("text-caption text-grey-6")
            value_label = ui.label("…").classes("text-h4 text-bold")
    return value_label
