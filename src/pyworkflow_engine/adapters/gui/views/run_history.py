"""Vue Run History — historique filtrable des runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.run_table import (
    run_table,
    refresh_run_table,
)
from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.models.enums import RunStatus

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_run_history(
    engine: WorkflowEngine,
    config: GUIConfig,
    job_filter: str | None = None,
) -> None:
    """Construit la page historique des runs (/runs).

    Args:
        engine: Instance du moteur de workflow.
        config: Configuration GUI.
        job_filter: Pré-filtre sur le nom de job (query param ``?job=``).
    """
    page_toolbar("Historique des runs", icon="history", icon_color="secondary")

    # ── Filtres ────────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-4 flex-wrap"):
            job_input = ui.input(
                "Filtrer par job",
                placeholder="Nom du job…",
                value=job_filter or "",
            ).classes("min-w-[200px]")
            status_select = ui.select(
                options=[""] + [s.value for s in RunStatus],
                value="",
                label="Statut",
            ).classes("min-w-[160px]")
            limit_input = ui.number(
                "Limite", value=100, min=10, max=1000, step=10
            ).classes("w-24")
            ui.button("Appliquer", icon="search", on_click=lambda: refresh()).props(
                "color=primary"
            )

    # ── Table runs ─────────────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        runs_count = ui.label("").classes("text-caption text-grey-6 q-mb-xs")
        try:
            initial_runs = _fetch_runs(engine, job_filter, None, 100)
        except Exception:
            initial_runs = []
        runs_count.set_text(f"{len(initial_runs)} run(s) trouvé(s)")
        grid = run_table(
            initial_runs,
            on_select=lambda run_id: ui.navigate.to(f"/run/{run_id}"),
        )

    def refresh() -> None:
        job_name = job_input.value.strip() or None
        status_val = status_select.value or None
        limit = int(limit_input.value or 100)
        try:
            runs = _fetch_runs(engine, job_name, status_val, limit)
        except Exception:
            runs = []
        runs_count.set_text(f"{len(runs)} run(s) trouvé(s)")
        refresh_run_table(grid, runs)

    # No auto-timer: run history is historical, manual refresh is sufficient.
    # The "Appliquer" button and the on_click lambda above handle user-driven refresh.


def _fetch_runs(
    engine: WorkflowEngine,
    job_name: str | None,
    status: str | None,
    limit: int,
) -> list:
    kwargs: dict = {"limit": limit}
    if job_name:
        kwargs["job_name"] = job_name
    if status:
        kwargs["status"] = status
    return engine.list_job_runs(**kwargs)
