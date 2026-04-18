"""job_table — tableau AG Grid des jobs enregistrés."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

from nicegui import ui

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine


def job_table(
    engine: WorkflowEngine,
    on_select: Callable[[str], None] | None = None,
    height: str = "calc(100vh - 220px)",
) -> ui.aggrid:
    """Crée un tableau AG Grid listant tous les jobs enregistrés.

    Args:
        engine: Instance du moteur de workflow.
        on_select: Callback appelé avec le nom du job quand une ligne est cliquée.
        height: Hauteur CSS du tableau (ex: ``"300px"``, ``"calc(100vh - 220px)"``).
            Par défaut remplit la hauteur disponible de la page.

    Returns:
        L'instance ``ui.aggrid`` créée (pour pouvoir la rafraîchir).
    """
    row_data = _build_row_data(engine)
    grid = (
        ui.aggrid(
            {
                "columnDefs": [
                    {
                        "headerName": "Nom",
                        "field": "name",
                        "flex": 1,
                        "cellStyle": {"cursor": "pointer", "color": "var(--q-primary)"},
                    },
                    {
                        "headerName": "Steps",
                        "field": "steps",
                        "width": 90,
                        "type": "numericColumn",
                    },
                    {"headerName": "Version", "field": "version", "width": 100},
                    {"headerName": "Executor", "field": "executor", "width": 130},
                    {"headerName": "Priorité", "field": "priority", "width": 110},
                    {"headerName": "Description", "field": "description", "flex": 2},
                ],
                "rowData": row_data,
                "rowSelection": {"mode": "singleRow"},
                "defaultColDef": {
                    "sortable": True,
                    "resizable": True,
                    "filter": True,
                },
            },
            auto_size_columns=False,
        )
        .classes("w-full")
        .style(f"height: {height}")
    )

    if on_select:

        def _handle_cell_click(e: dict) -> None:
            name = (e.args or {}).get("data", {}).get("name", "")
            if name:
                on_select(name)

        grid.on("cellClicked", _handle_cell_click)

    grid._row_fingerprint = _fingerprint(row_data)  # type: ignore[attr-defined]
    return grid


def refresh_job_table(grid: ui.aggrid, engine: WorkflowEngine) -> None:
    """Met à jour les données via l'API AG Grid (no-op si rien n'a changé).

    Utilise ``run_grid_method`` qui appelle ``api.setGridOption`` directement
    sur le client — pas de destroy/recreate, pas de flash.
    Doit être appelé uniquement depuis un timer ou un callback (après mounted()).
    """
    new_data = _build_row_data(engine)
    fp = _fingerprint(new_data)
    if getattr(grid, "_row_fingerprint", None) == fp:
        return
    grid._row_fingerprint = fp  # type: ignore[attr-defined]
    grid.run_grid_method("setGridOption", "rowData", new_data)


def _fingerprint(rows: list[dict]) -> int:
    return hash(json.dumps(rows, sort_keys=True, default=str))


def _build_row_data(engine: WorkflowEngine) -> list[dict]:
    return [
        {
            "name": j.name,
            "steps": len(j.steps),
            "version": j.version or "—",
            "executor": (j.default_executor.value if j.default_executor else "local"),
            "priority": j.priority.name,
            "description": j.description or "—",
        }
        for j in engine.list_jobs()
    ]
