"""Vue Pipeline Runs — historique et détail des exécutions de pipelines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.status_badge import status_badge
from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.adapters.gui.styles.theme import (
    STATUS_COLOR,
    fmt_dt,
    fmt_ms,
    status_badge_html,
)
from pyworkflow_engine.models.enums import RunStatus

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_pipeline_runs_page(
    engine: WorkflowEngine,
    config: GUIConfig,
    pipeline_filter: str | None = None,
) -> None:
    """Construit la page historique des pipeline runs (/pipeline-runs)."""
    page_toolbar("Historique des pipelines", icon="timeline", icon_color="teal")

    # ── Filtres ────────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-4 flex-wrap"):
            pipeline_input = ui.input(
                "Filtrer par pipeline",
                placeholder="Nom de la pipeline…",
                value=pipeline_filter or "",
            ).classes("min-w-[220px]")
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

    # ── Table pipeline runs ────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        runs_count = ui.label("").classes("text-caption text-grey-6 q-mb-xs")
        try:
            initial_runs = _fetch_pipeline_runs(engine, pipeline_filter, None, 100)
        except Exception:
            initial_runs = []
        runs_count.set_text(f"{len(initial_runs)} pipeline run(s) trouvé(s)")
        grid = _pipeline_run_table(
            initial_runs,
            on_select=lambda rid: ui.navigate.to(f"/pipeline-run/{rid}"),
        )

    def refresh() -> None:
        pipeline_name = pipeline_input.value.strip() or None
        status_val = status_select.value or None
        limit = int(limit_input.value or 100)
        try:
            runs = _fetch_pipeline_runs(engine, pipeline_name, status_val, limit)
        except Exception:
            runs = []
        runs_count.set_text(f"{len(runs)} pipeline run(s) trouvé(s)")
        _refresh_pipeline_run_table(grid, runs)


def build_pipeline_run_detail(
    engine: WorkflowEngine, config: GUIConfig, run_id: str
) -> None:
    """Construit la page de détail d'un pipeline run (/pipeline-run/{run_id})."""
    page_toolbar(
        run_id[:16] + "…",
        icon="timeline",
        icon_color="teal",
        back_url="/pipeline-runs",
        subtitle="Détail du pipeline run",
    )

    pipeline_run = _get_pipeline_run(engine, run_id)
    if pipeline_run is None:
        ui.label(f"Pipeline run « {run_id} » introuvable.").classes(
            "text-negative text-h6"
        )
        return

    # ── Header ─────────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-6 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label("Statut").classes("text-caption text-grey-6")
                status_badge(pipeline_run.status)

            _info_cell("Pipeline", pipeline_run.pipeline_name)
            _info_cell("Version", pipeline_run.pipeline_version)
            _info_cell("Démarré par", pipeline_run.triggered_by)
            _info_cell("Créé le", fmt_dt(pipeline_run.created_at))
            _info_cell("Démarré", fmt_dt(pipeline_run.start_time))
            _info_cell(
                "Durée",
                fmt_ms(pipeline_run.duration_ms),
            )

        if pipeline_run.error:
            with ui.row().classes("q-mt-sm"):
                ui.icon("error").classes("text-negative")
                ui.label(pipeline_run.error).classes(
                    "text-caption text-negative q-ml-xs"
                )

    # ── Progression ────────────────────────────────────────────────────────
    if pipeline_run.stage_runs:
        with ui.card().classes("w-full q-mb-md"):
            ui.label("Progression").classes("text-subtitle1 text-bold q-mb-sm")
            total = len(pipeline_run.stage_runs)
            done = sum(
                1 for sr in pipeline_run.stage_runs if sr.status == RunStatus.SUCCESS
            )
            failed = sum(
                1 for sr in pipeline_run.stage_runs if sr.status == RunStatus.FAILED
            )
            pct = (done / total * 100) if total else 0
            with ui.row().classes("items-center gap-3 q-mb-sm"):
                ui.linear_progress(value=pct / 100).classes("flex-1")
                ui.label(f"{done}/{total} stages terminés").classes("text-caption")
                if failed:
                    ui.label(f"({failed} en échec)").classes(
                        "text-caption text-negative"
                    )

    # ── Stages ─────────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        ui.label("Stages").classes("text-subtitle1 text-bold q-mb-sm")
        if not pipeline_run.stage_runs:
            ui.label("Aucun stage trouvé.").classes("text-grey-6")
        else:
            for sr in sorted(pipeline_run.stage_runs, key=lambda x: x.stage_index):
                _stage_expansion(sr)

    # ── Contexte ───────────────────────────────────────────────────────────
    if pipeline_run.context:
        with ui.card().classes("w-full"):
            ui.label("Contexte propagé").classes("text-subtitle1 text-bold q-mb-sm")
            ui.code(str(pipeline_run.context), language="python").classes("w-full")


def _pipeline_run_table(runs: list, on_select=None) -> ui.aggrid:
    """Crée un tableau AG Grid pour les pipeline runs."""
    grid = (
        ui.aggrid(
            {
                "columnDefs": [
                    {"headerName": "_run_id", "field": "_run_id", "hide": True},
                    {"headerName": "Pipeline", "field": "pipeline_name", "flex": 2},
                    {
                        "headerName": "Statut",
                        "field": "status_html",
                        "flex": 1,
                        "cellRenderer": "html",
                    },
                    {"headerName": "Stages", "field": "stages", "width": 90},
                    {
                        "headerName": "Déclenché par",
                        "field": "triggered_by",
                        "width": 130,
                    },
                    {"headerName": "Créé le", "field": "created_at", "width": 160},
                    {"headerName": "Durée", "field": "duration", "width": 100},
                ],
                "rowData": _runs_to_rows(runs),
                "defaultColDef": {
                    "resizable": True,
                    "filter": True,
                    "sortable": True,
                },
                "domLayout": "normal",
                "rowSelection": {"mode": "singleRow"},
            },
            html_columns=[2],
            auto_size_columns=False,
        )
        .classes("w-full")
        .style("height: 480px")
    )
    if on_select:
        grid.on(
            "rowClicked",
            lambda e: (
                on_select((e.args or {}).get("data", {}).get("_run_id", ""))
                if (e.args or {}).get("data", {}).get("_run_id")
                else None
            ),
        )
    return grid


def _refresh_pipeline_run_table(grid: ui.aggrid, runs: list) -> None:
    grid.options["rowData"] = _runs_to_rows(runs)
    grid.update()


def _runs_to_rows(runs: list) -> list[dict]:
    return [
        {
            "_run_id": r.pipeline_run_id,
            "pipeline_name": r.pipeline_name,
            "status_html": status_badge_html(r.status),
            "stages": len(r.stage_runs),
            "triggered_by": r.triggered_by or "manual",
            "created_at": fmt_dt(r.created_at),
            "duration": fmt_ms(r.duration_ms),
        }
        for r in runs
    ]


def _fetch_pipeline_runs(
    engine: WorkflowEngine,
    pipeline_name: str | None,
    status: str | None,
    limit: int,
) -> list:
    storage = getattr(engine, "_storage", None)
    if storage is None:
        return []
    kwargs: dict = {"limit": limit}
    if pipeline_name:
        kwargs["pipeline_name"] = pipeline_name
    if status:
        kwargs["status"] = status
    return storage.list_pipeline_runs(**kwargs)


def _get_pipeline_run(engine: WorkflowEngine, run_id: str):
    storage = getattr(engine, "_storage", None)
    if storage is None:
        return None
    try:
        return storage.get_pipeline_run(run_id)
    except Exception:
        return None


def _info_cell(label: str, value: str) -> None:
    with ui.column().classes("gap-1"):
        ui.label(label).classes("text-caption text-grey-6")
        ui.label(value).classes("text-body2 text-bold")


def _stage_expansion(sr) -> None:
    """Rend un stage sous forme d'expansion NiceGUI avec drill-down steps."""
    from pyworkflow_engine.models.enums import RunStatus  # noqa: PLC0415

    # Icône + couleur selon statut
    if sr.status == RunStatus.SUCCESS:
        icon, color = "check_circle", "positive"
    elif sr.skipped:
        icon, color = "skip_next", "grey"
    elif sr.status == RunStatus.FAILED:
        icon, color = "cancel", "negative"
    else:
        icon, color = "pending", "warning"

    caption = fmt_ms(sr.duration_ms)
    if sr.skipped:
        caption = "skippé"
    elif sr.error:
        caption = sr.error[:60] + ("…" if len(sr.error or "") > 60 else "")

    header_text = f"#{sr.stage_index + 1}  {sr.job_name}  —  {caption}"

    with (
        ui.expansion(header_text, icon=icon)
        .classes(f"w-full q-mb-xs border rounded text-{color}")
        .props(f"icon-color={color}")
    ):
        # ── Méta du stage ──────────────────────────────────────────────
        with ui.row().classes("gap-6 q-mb-sm flex-wrap"):
            _info_cell("Statut", sr.status.value)
            _info_cell("Skippé", "Oui" if sr.skipped else "Non")
            _info_cell("Démarré", fmt_dt(sr.start_time))
            _info_cell("Durée", fmt_ms(sr.duration_ms))
            if sr.skip_reason:
                _info_cell("Raison skip", sr.skip_reason)
        if sr.error and not sr.skipped:
            with ui.row().classes("items-start gap-2 q-mb-sm"):
                ui.icon("error").classes("text-negative text-sm mt-1")
                ui.label(sr.error).classes("text-caption text-negative")

        # ── Steps du job_run (si disponible) ───────────────────────────
        step_runs = sr.job_run.step_runs if sr.job_run is not None else []
        if step_runs:
            ui.label("Steps").classes(
                "text-caption text-bold text-grey-7 q-mt-xs q-mb-xs"
            )
            ui.aggrid(
                {
                    "columnDefs": [
                        {"headerName": "Step", "field": "name", "flex": 2},
                        {
                            "headerName": "Statut",
                            "field": "status_html",
                            "width": 150,
                            "cellRenderer": "html",
                        },
                        {"headerName": "Démarré", "field": "started", "width": 150},
                        {
                            "headerName": "Durée",
                            "field": "duration",
                            "width": 100,
                            "type": "numericColumn",
                        },
                        {"headerName": "Erreur", "field": "error", "flex": 2},
                    ],
                    "rowData": [
                        {
                            "name": step.step_name,
                            "status_html": status_badge_html(step.status),
                            "started": fmt_dt(step.start_time),
                            "duration": fmt_ms(step.duration_ms),
                            "error": step.error or "",
                        }
                        for step in step_runs
                    ],
                    "defaultColDef": {"resizable": True},
                    "domLayout": "autoHeight",
                },
                html_columns=[1],
                auto_size_columns=False,
            ).classes("w-full")
        else:
            ui.label("Aucun détail de step disponible.").classes(
                "text-caption text-grey-5 q-mt-xs"
            )
