"""Vue Pipelines — liste des pipelines + détail d'une pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.dag_graph import (
    dag_graph,
    pipeline_dag_graph,
)
from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.adapters.gui.styles.theme import fmt_dt, fmt_ms

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_pipelines_page(engine: WorkflowEngine, config: GUIConfig) -> None:
    """Construit la page liste des pipelines (/pipelines)."""
    page_toolbar("Pipelines", icon="account_tree", icon_color="teal")

    pipelines = _list_pipelines(engine)

    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center justify-between q-mb-sm"):
            ui.label(f"{len(pipelines)} pipeline(s) enregistrée(s)").classes(
                "text-caption text-grey-6"
            )
            ui.button(
                "Rafraîchir",
                icon="refresh",
                on_click=lambda: ui.navigate.reload(),
            ).props("flat dense")

        if not pipelines:
            ui.label("Aucune pipeline enregistrée.").classes("text-grey-6 q-pa-md")
            return

        ui.aggrid(
            {
                "columnDefs": [
                    {
                        "headerName": "Nom",
                        "field": "name",
                        "flex": 2,
                        "cellStyle": {
                            "cursor": "pointer",
                            "color": "var(--q-primary)",
                            "fontWeight": "500",
                        },
                    },
                    {"headerName": "Description", "field": "description", "flex": 3},
                    {
                        "headerName": "Stages",
                        "field": "stages",
                        "width": 90,
                        "type": "numericColumn",
                    },
                    {"headerName": "Version", "field": "version", "width": 100},
                    {"headerName": "Priorité", "field": "priority", "width": 110},
                    {"headerName": "Owner", "field": "owner", "width": 160},
                    {
                        "headerName": "Activée",
                        "field": "enabled",
                        "width": 90,
                        "cellRenderer": "agCheckboxCellRenderer",
                    },
                    {"headerName": "Cron", "field": "schedule", "width": 140},
                    {"headerName": "Tags", "field": "tags", "flex": 1},
                ],
                "rowData": [
                    {
                        "name": p.name,
                        "description": p.description or "—",
                        "stages": p.stage_count,
                        "version": p.version,
                        "priority": (
                            p.priority.value
                            if hasattr(p.priority, "value")
                            else str(p.priority)
                        ),
                        "owner": p.owner or "—",
                        "enabled": p.enabled,
                        "schedule": p.schedule or "—",
                        "tags": ", ".join(p.tags) if p.tags else "—",
                    }
                    for p in pipelines
                ],
                "defaultColDef": {"resizable": True, "filter": True, "sortable": True},
                "domLayout": "normal",
                "rowSelection": {"mode": "singleRow"},
            },
            auto_size_columns=False,
        ).classes("w-full").style("height: 480px").on(
            "cellClicked",
            lambda e: (
                ui.navigate.to(
                    f"/pipeline/{(e.args or {}).get('data', {}).get('name', '')}"
                )
                if (e.args or {}).get("data", {}).get("name")
                else None
            ),
        )


def build_pipeline_detail_page(
    engine: WorkflowEngine, config: GUIConfig, pipeline_name: str
) -> None:
    """Construit la page détail d'une pipeline (/pipeline/{name})."""
    page_toolbar(
        pipeline_name,
        icon="account_tree",
        icon_color="teal",
        back_url="/pipelines",
        subtitle="Détail de la pipeline",
    )

    pipeline = _get_pipeline(engine, pipeline_name)
    if pipeline is None:
        ui.label(f"Pipeline « {pipeline_name} » introuvable.").classes(
            "text-negative text-h6"
        )
        return

    # ── Métadonnées + Actions ─────────────────────────────────────────────
    with ui.row().classes("w-full gap-4 q-mb-md"):
        with ui.card().classes("flex-1"):
            ui.label("Métadonnées").classes("text-subtitle1 text-bold q-mb-sm")
            _meta_row("Nom", pipeline.name)
            _meta_row("Version", pipeline.version)
            _meta_row("Owner", pipeline.owner or "—")
            _meta_row(
                "Priorité",
                (
                    pipeline.priority.value
                    if hasattr(pipeline.priority, "value")
                    else str(pipeline.priority)
                ),
            )
            _meta_row("Cron", pipeline.schedule or "—")
            _meta_row("Tags", ", ".join(pipeline.tags) if pipeline.tags else "—")
            _meta_row("Activée", "Oui" if pipeline.enabled else "Non")
            _meta_row("Description", pipeline.description or "—")

        with ui.card().classes("min-w-[200px]"):
            ui.label("Actions").classes("text-subtitle1 text-bold q-mb-sm")
            result_label = ui.label("").classes("text-caption")

            def _run_pipeline() -> None:
                try:
                    pr = engine.run_pipeline_with_storage(pipeline)
                    result_label.set_text(
                        f"Pipeline démarrée : {pr.pipeline_run_id[:14]}…"
                    )
                    result_label.classes(remove="text-negative", add="text-positive")
                    ui.notify(
                        f"Pipeline {pr.pipeline_run_id[:14]}… terminée ✓",
                        type="positive",
                    )
                    ui.navigate.to(f"/pipeline-runs?pipeline={pipeline.name}")
                except Exception as exc:
                    result_label.set_text(str(exc))
                    result_label.classes(remove="text-positive", add="text-negative")
                    ui.notify(str(exc), type="negative")

            ui.button("▶  Lancer", on_click=_run_pipeline, color="positive").classes(
                "w-full"
            )
            ui.button(
                "📋  Historique",
                color="primary",
                on_click=lambda: ui.navigate.to(
                    f"/pipeline-runs?pipeline={pipeline.name}"
                ),
            ).classes("w-full q-mt-sm").props("outline")

    # ── DAG Pipeline ──────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        ui.label("DAG — Séquencement des stages").classes(
            "text-subtitle1 text-bold q-mb-sm"
        )
        pipeline_dag_graph(pipeline)

    # ── Stages + DAG par job ──────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        ui.label("Stages").classes("text-subtitle1 text-bold q-mb-sm")
        if not pipeline.stages:
            ui.label("Aucun stage défini.").classes("text-grey-6")
        else:
            for i, stage in enumerate(pipeline.stages):
                with ui.expansion(
                    f"#{i + 1}  {stage.job_name}",
                    icon="play_circle",
                ).classes("w-full q-mb-xs border rounded"):
                    # Stage metadata chips
                    with ui.row().classes("gap-2 q-mb-sm flex-wrap"):
                        if not stage.enabled:
                            ui.badge("Désactivé", color="grey").props("outline")
                        if stage.continue_on_failure:
                            ui.badge("Continue si échec", color="orange").props(
                                "outline"
                            )
                        if stage.initial_context:
                            ui.badge(
                                f"ctx: {stage.initial_context}", color="blue"
                            ).props("outline")
                        if stage.context_mapping:
                            ui.badge(
                                f"mapping: {stage.context_mapping}", color="teal"
                            ).props("outline")

                    # Job-level step DAG
                    job = engine.get_job(stage.job_name)
                    if job is not None:
                        ui.label("DAG des steps").classes(
                            "text-caption text-grey-6 q-mb-xs"
                        )
                        dag_graph(job)

                        # Steps mini-table
                        with ui.expansion("Voir les steps", icon="list").classes(
                            "w-full q-mt-sm"
                        ):
                            ui.aggrid(
                                {
                                    "columnDefs": [
                                        {
                                            "headerName": "Nom",
                                            "field": "name",
                                            "flex": 2,
                                        },
                                        {
                                            "headerName": "Type",
                                            "field": "type",
                                            "width": 120,
                                        },
                                        {
                                            "headerName": "Dépendances",
                                            "field": "deps",
                                            "flex": 2,
                                        },
                                        {
                                            "headerName": "Timeout",
                                            "field": "timeout",
                                            "width": 100,
                                        },
                                    ],
                                    "rowData": [
                                        {
                                            "name": s.name,
                                            "type": s.step_type.value,
                                            "deps": (
                                                ", ".join(s.dependencies)
                                                if s.dependencies
                                                else "—"
                                            ),
                                            "timeout": (
                                                str(s.timeout) if s.timeout else "—"
                                            ),
                                        }
                                        for s in job.steps
                                    ],
                                    "domLayout": "autoHeight",
                                    "defaultColDef": {"resizable": True},
                                },
                                auto_size_columns=False,
                            ).classes("w-full")
                    else:
                        ui.label(
                            f"Job « {stage.job_name} » non trouvé dans le registre."
                        ).classes("text-caption text-grey-5 q-mt-xs")


def _list_pipelines(engine: WorkflowEngine) -> list:
    """Récupère la liste des pipelines depuis le backend de persistence."""
    try:
        return engine.list_pipelines()
    except Exception:
        return []


def _get_pipeline(engine: WorkflowEngine, name: str):
    """Récupère une pipeline par nom."""
    try:
        return engine.get_pipeline(name)
    except Exception:
        return None


def _meta_row(label: str, value: str) -> None:
    with ui.row().classes("items-start gap-2 q-mb-xs"):
        ui.label(label + " :").classes("text-caption text-grey-6 w-28")
        ui.label(value).classes("text-body2")
