"""Vue Jobs — liste des jobs + détail DAG interactif."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.dag_graph import dag_graph
from pyworkflow_engine.adapters.gui.components.job_table import (
    job_table,
    refresh_job_table,
)
from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.adapters.gui.styles.theme import fmt_ms

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_jobs_page(engine: WorkflowEngine, config: GUIConfig) -> None:
    """Construit la page liste des jobs (/jobs)."""
    page_toolbar("Jobs enregistrés", icon="work", icon_color="primary")

    with ui.card().classes("w-full"):
        with ui.row().classes("items-center justify-end q-mb-sm"):
            ui.button("Rafraîchir", icon="refresh", on_click=lambda: refresh()).props(
                "flat dense"
            )

        grid = job_table(
            engine,
            on_select=lambda name: ui.navigate.to(f"/job/{name}"),
        )

    def refresh() -> None:
        refresh_job_table(grid, engine)

    # Jobs change rarely — only refresh on manual button click, not via timer.
    # (Timer would fire before client connects and blank the grid.)


def build_job_detail_page(
    engine: WorkflowEngine, config: GUIConfig, job_name: str
) -> None:
    """Construit la page détail d'un job (/job/{name})."""
    page_toolbar(
        job_name,
        icon="work",
        icon_color="primary",
        back_url="/jobs",
        subtitle="Détail du job",
    )

    job = engine.get_job(job_name)
    if job is None:
        ui.label(f"Job « {job_name} » introuvable.").classes("text-negative text-h6")
        return

    # ── Metadata + Actions ────────────────────────────────────────────────
    with ui.row().classes("w-full gap-4 q-mb-md"):
        with ui.card().classes("flex-1"):
            ui.label("Métadonnées").classes("text-subtitle1 text-bold q-mb-sm")
            _meta_row("Nom", job.name)
            _meta_row("Version", job.version or "—")
            _meta_row(
                "Executor",
                job.default_executor.value if job.default_executor else "local",
            )
            _meta_row("Priorité", job.priority.name)
            _meta_row("Steps", str(len(job.steps)))
            _meta_row("Description", job.description or "—")

        with ui.card().classes("min-w-[200px]"):
            ui.label("Actions").classes("text-subtitle1 text-bold q-mb-sm")
            result_label = ui.label("").classes("text-caption")

            def _run_job() -> None:
                try:
                    jr = engine.run_with_storage(job_name)
                    result_label.set_text(f"Run démarré : {jr.job_run_id[:14]}…")
                    result_label.classes(remove="text-negative", add="text-positive")
                    ui.notify(f"Run {jr.job_run_id[:14]}… démarré ✓", type="positive")
                    ui.navigate.to(f"/run/{jr.job_run_id}")
                except Exception as exc:
                    result_label.set_text(str(exc))
                    result_label.classes(remove="text-positive", add="text-negative")
                    ui.notify(str(exc), type="negative")

            ui.button("▶  Lancer", on_click=_run_job, color="positive").classes(
                "w-full"
            )
            ui.button(
                "📋  Historique",
                color="primary",
                on_click=lambda: ui.navigate.to(f"/runs?job={job_name}"),
            ).classes("w-full q-mt-sm").props("outline")

    # ── DAG Mermaid ───────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        ui.label("DAG — Graphe de dépendances").classes(
            "text-subtitle1 text-bold q-mb-sm"
        )
        dag_graph(job)

    # ── Steps table ───────────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("Steps").classes("text-subtitle1 text-bold q-mb-sm")
        ui.aggrid(
            {
                "columnDefs": [
                    {"headerName": "Nom", "field": "name", "flex": 1},
                    {"headerName": "Type", "field": "type", "width": 130},
                    {"headerName": "Executor", "field": "executor", "width": 120},
                    {"headerName": "Dépendances", "field": "deps", "flex": 1},
                    {"headerName": "Timeout", "field": "timeout", "width": 110},
                    {
                        "headerName": "Retry",
                        "field": "retry",
                        "width": 80,
                        "type": "numericColumn",
                    },
                ],
                "rowData": [
                    {
                        "name": s.name,
                        "type": s.step_type.value,
                        "executor": (
                            s.executor_type.value
                            if hasattr(s, "executor_type") and s.executor_type
                            else "—"
                        ),
                        "deps": ", ".join(s.dependencies) if s.dependencies else "—",
                        "timeout": str(s.timeout) if s.timeout else "—",
                        "retry": s.retry_count if hasattr(s, "retry_count") else 0,
                    }
                    for s in job.steps
                ],
                "domLayout": "normal",
                "defaultColDef": {"resizable": True, "filter": True},
            },
            auto_size_columns=False,
        ).classes("w-full").style("height: 300px")


def _meta_row(label: str, value: str) -> None:
    with ui.row().classes("items-start gap-2 q-mb-xs"):
        ui.label(label + " :").classes("text-caption text-grey-6 w-28")
        ui.label(value).classes("text-body2")
