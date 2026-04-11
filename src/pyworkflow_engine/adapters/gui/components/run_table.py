"""run_table — tableau AG Grid des job runs avec badges de statut."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

from nicegui import ui

from pyworkflow_engine.adapters.gui.styles.theme import (
    fmt_dt,
    fmt_ms,
    status_badge_html,
)

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine
    from pyworkflow_engine.models.runtime import JobRun


def run_table(
    runs: list[JobRun],
    on_select: Callable[[str], None] | None = None,
) -> ui.aggrid:
    """Crée un tableau AG Grid affichant une liste de runs.

    Args:
        runs: Liste de ``JobRun`` à afficher.
        on_select: Callback appelé avec le run_id quand une ligne est cliquée.

    Returns:
        L'instance ``ui.aggrid`` créée.
    """
    row_data = _build_row_data(runs)
    grid = (
        ui.aggrid(
            {
                "columnDefs": [
                    {"headerName": "Run ID", "field": "run_id", "width": 170},
                    {"headerName": "Job", "field": "job", "flex": 1},
                    {
                        "headerName": "Statut",
                        "field": "status_html",
                        "width": 175,
                    },
                    {"headerName": "Démarré", "field": "started", "width": 175},
                    {
                        "headerName": "Durée",
                        "field": "duration",
                        "width": 110,
                        "type": "numericColumn",
                    },
                ],
                "rowData": row_data,
                "rowSelection": {"mode": "singleRow"},
                "defaultColDef": {"resizable": True, "filter": True},
            },
            html_columns=[2],
            auto_size_columns=False,
        )
        .classes("w-full")
        .style("height: 400px")
    )

    if on_select:

        def _handle_row_click(e: dict) -> None:
            run_id = (e.args or {}).get("data", {}).get("_run_id", "")
            if run_id:
                on_select(run_id)

        grid.on("rowClicked", _handle_row_click)

    grid._row_fingerprint = _fingerprint(row_data)  # type: ignore[attr-defined]
    return grid


def refresh_run_table(grid: ui.aggrid, runs: list[JobRun]) -> None:
    """Met à jour les données via l'API AG Grid (no-op si rien n'a changé).

    Doit être appelé uniquement depuis un timer ou un callback (après mounted()).
    """
    new_data = _build_row_data(runs)
    fp = _fingerprint(new_data)
    if getattr(grid, "_row_fingerprint", None) == fp:
        return
    grid._row_fingerprint = fp  # type: ignore[attr-defined]
    grid.run_grid_method("setGridOption", "rowData", new_data)


def _fingerprint(rows: list[dict]) -> int:
    return hash(json.dumps(rows, sort_keys=True, default=str))


def _build_row_data(runs: list[JobRun]) -> list[dict]:
    rows = []
    for r in runs:
        duration_ms: int | None = None
        if r.start_time and r.end_time:
            duration_ms = int((r.end_time - r.start_time).total_seconds() * 1000)
        rows.append(
            {
                "_run_id": r.job_run_id,
                "run_id": r.job_run_id[:16] + "…",
                "job": r.job_name,
                "status_html": status_badge_html(r.status),
                "started": fmt_dt(r.start_time),
                "duration": fmt_ms(duration_ms),
            }
        )
    return rows
