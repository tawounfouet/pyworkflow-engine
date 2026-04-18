"""step_progress — tableau de progression des steps d'un run."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.styles.theme import (
    STATUS_COLOR,
    STATUS_ICON,
    STATUS_LABEL,
    fmt_dt,
    fmt_ms,
)

if TYPE_CHECKING:
    from pyworkflow_engine.models.workflow.run import StepRun


def step_progress_table(step_runs: list[StepRun]) -> ui.aggrid:
    """Crée un tableau AG Grid montrant la progression des steps d'un run.

    Args:
        step_runs: Liste de ``StepRun`` du job run courant.

    Returns:
        L'instance ``ui.aggrid`` créée.
    """
    row_data = _build_row_data(step_runs)
    grid = (
        ui.aggrid(
            {
                "columnDefs": [
                    {"headerName": "Step", "field": "name", "flex": 1},
                    {
                        "headerName": "Statut",
                        "field": "status_html",
                        "width": 175,
                    },
                    {"headerName": "Démarré", "field": "started", "width": 155},
                    {
                        "headerName": "Durée",
                        "field": "duration",
                        "width": 100,
                        "type": "numericColumn",
                    },
                    {"headerName": "Erreur", "field": "error", "flex": 2},
                ],
                "rowData": row_data,
                "defaultColDef": {"resizable": True, "filter": False},
            },
            html_columns=[1],
            auto_size_columns=False,
        )
        .classes("w-full")
        .style("height: 300px")
    )

    grid._row_fingerprint = _fingerprint(row_data)  # type: ignore[attr-defined]
    return grid


def refresh_step_progress(grid: ui.aggrid, step_runs: list[StepRun]) -> None:
    """Met à jour les données via l'API AG Grid (no-op si rien n'a changé).

    Doit être appelé uniquement depuis un timer ou un callback (après mounted()).
    """
    new_data = _build_row_data(step_runs)
    fp = _fingerprint(new_data)
    if getattr(grid, "_row_fingerprint", None) == fp:
        return
    grid._row_fingerprint = fp  # type: ignore[attr-defined]
    grid.run_grid_method("setGridOption", "rowData", new_data)


def _fingerprint(rows: list[dict]) -> int:
    return hash(json.dumps(rows, sort_keys=True, default=str))


def _build_row_data(step_runs: list[StepRun]) -> list[dict]:
    from pyworkflow_engine.adapters.gui.styles.theme import status_badge_html

    rows = []
    for sr in step_runs:
        duration_ms: int | None = None
        if sr.start_time and sr.end_time:
            duration_ms = int((sr.end_time - sr.start_time).total_seconds() * 1000)
        rows.append(
            {
                "name": sr.step_name,
                "status_html": status_badge_html(sr.status),
                "started": fmt_dt(sr.start_time),
                "duration": fmt_ms(duration_ms),
                "error": sr.error or "",
            }
        )
    return rows
