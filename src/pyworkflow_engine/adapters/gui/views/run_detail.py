"""Vue Run Detail — suivi en temps réel d'un run."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.log_viewer import (
    log_viewer,
    refresh_log_viewer,
)
from pyworkflow_engine.adapters.gui.components.step_progress import (
    step_progress_table,
    refresh_step_progress,
)
from pyworkflow_engine.adapters.gui.components.status_badge import status_badge
from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.adapters.gui.styles.theme import fmt_dt, fmt_ms
from pyworkflow_engine.models.enums import RunStatus

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_run_detail(engine: WorkflowEngine, config: GUIConfig, run_id: str) -> None:
    """Construit la page de détail d'un run (/run/{run_id}).

    Args:
        engine: Instance du moteur de workflow.
        config: Configuration GUI.
        run_id: Identifiant complet du run à afficher.
    """
    page_toolbar(
        run_id[:16] + "…",
        icon="play_circle",
        icon_color="warning",
        back_url="/runs",
        subtitle="Détail du run",
    )

    job_run = engine.get_job_run(run_id)
    if job_run is None:
        ui.label(f"Run « {run_id} » introuvable.").classes("text-negative text-h6")
        return

    # ── Header : statut + méta ─────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-6 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label("Statut").classes("text-caption text-grey-6")
                status_row = ui.row().classes("items-center")
                with status_row:
                    status_badge(job_run.status)

            _info_cell("Job", job_run.job_name)
            _info_cell("Démarré", fmt_dt(job_run.start_time))
            _info_cell(
                "Durée",
                fmt_ms(
                    int((job_run.end_time - job_run.start_time).total_seconds() * 1000)
                    if job_run.start_time and job_run.end_time
                    else None
                ),
            )

        # Actions
        with ui.row().classes("q-mt-sm gap-2"):
            cancel_btn = ui.button("Annuler", icon="cancel", color="negative").props(
                "outline"
            )
            resume_btn = ui.button(
                "Reprendre", icon="play_arrow", color="positive"
            ).props("outline")
            action_msg = ui.label("").classes("text-caption self-center")

            def _cancel() -> None:
                ok = engine.cancel(run_id)
                if ok:
                    action_msg.set_text("Run annulé.")
                    action_msg.classes(replace="text-negative text-caption self-center")
                    ui.notify("Run annulé.", type="warning")
                else:
                    action_msg.set_text("Impossible d'annuler ce run.")
                    ui.notify("Impossible d'annuler ce run.", type="negative")
                _do_refresh()

            def _resume() -> None:
                try:
                    engine.resume(run_id)
                    action_msg.set_text("Run repris.")
                    action_msg.classes(replace="text-positive text-caption self-center")
                    ui.notify("Run repris.", type="positive")
                except Exception as exc:
                    action_msg.set_text(str(exc))
                    ui.notify(str(exc), type="negative")
                _do_refresh()

            cancel_btn.on("click", _cancel)
            resume_btn.on("click", _resume)

    # ── Steps progress ─────────────────────────────────────────────────────
    with ui.splitter(value=50).classes("w-full gap-4") as splitter:
        with splitter.before:
            with ui.card().classes("w-full h-full"):
                ui.label("Steps").classes("text-subtitle1 text-bold q-mb-sm")
                steps_grid = step_progress_table(job_run.step_runs)

        with splitter.after:
            with ui.card().classes("w-full h-full"):
                ui.label("Logs").classes("text-subtitle1 text-bold q-mb-sm")
                log_panel = log_viewer(job_run.step_runs)

    # ── Live refresh ───────────────────────────────────────────────────────
    def _do_refresh() -> None:
        current = engine.get_job_run(run_id)
        if current is None:
            return
        refresh_step_progress(steps_grid, current.step_runs)
        refresh_log_viewer(log_panel, current.step_runs)
        # Update status badge
        with status_row:
            status_row.clear()
            status_badge(current.status)
        # Stop timer once terminal
        if current.status not in (RunStatus.RUNNING, RunStatus.PENDING):
            t.cancel()

    t = ui.timer(config.refresh_interval, _do_refresh)


def _info_cell(label: str, value: str) -> None:
    with ui.column().classes("gap-1"):
        ui.label(label).classes("text-caption text-grey-6")
        ui.label(value).classes("text-body2 text-bold")
