"""Vue Dashboard — vue d'ensemble jobs + runs récents + pipelines + IA."""

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

_SECTION_HDR = "items-center gap-1 q-mb-xs"
_SECTION_LABEL = "text-caption text-grey-6 text-bold"
_KPI_ROW = "w-full gap-4 q-mb-md"
_CARD_HDR = "items-center gap-2"


def build_dashboard(engine: WorkflowEngine, config: GUIConfig) -> None:
    """Construit la page Dashboard (route / et /dashboard)."""
    page_toolbar("Dashboard", icon="dashboard", icon_color="primary")

    # ── Section Workflow — KPI cards ───────────────────────────────────────
    with ui.row().classes(_SECTION_HDR):
        ui.icon("work").classes("text-primary")
        ui.label("Workflow").classes(_SECTION_LABEL)
    with ui.row().classes(_KPI_ROW):
        kpi_jobs = _kpi_card("Jobs", "work", "primary")
        kpi_runs = _kpi_card("Runs total", "bar_chart", "secondary")
        kpi_running = _kpi_card("En cours", "sync", "warning")
        kpi_failed = _kpi_card("Échoués (24h)", "cancel", "negative")
        kpi_suspended = _kpi_card("Suspendus", "pause_circle", "info")
        kpi_success_rate = _kpi_card("Taux succès", "percent", "positive")

    # ── Section Pipelines — KPI cards ──────────────────────────────────────
    with ui.row().classes(_SECTION_HDR):
        ui.icon("account_tree").classes("text-teal")
        ui.label("Pipelines").classes(_SECTION_LABEL)
    with ui.row().classes(_KPI_ROW):
        kpi_pipeline_runs = _kpi_card("Pipeline runs", "timeline", "teal")
        kpi_pipeline_running = _kpi_card("En cours", "sync", "warning")
        kpi_pipeline_failed = _kpi_card("Échoués", "cancel", "negative")
        kpi_pipeline_ok = _kpi_card("Succès", "check_circle", "positive")

    # ── Section IA — KPI cards ─────────────────────────────────────────────
    with ui.row().classes(_SECTION_HDR):
        ui.icon("smart_toy").classes("text-deep-purple")
        ui.label("Intelligence Artificielle").classes(_SECTION_LABEL)
    with ui.row().classes(_KPI_ROW):
        kpi_agents = _kpi_card("Agents", "smart_toy", "deep-purple")
        kpi_executions = _kpi_card("Exécutions", "bolt", "orange")
        kpi_conversations = _kpi_card("Conversations", "chat", "teal-8")
        kpi_tokens = _kpi_card("Tokens (total)", "token", "grey-7")

    # ── Section Scheduler — KPI cards ─────────────────────────────────────
    with ui.row().classes(_SECTION_HDR):
        ui.icon("schedule").classes("text-teal")
        ui.label("Scheduler").classes(_SECTION_LABEL)
    with ui.row().classes(_KPI_ROW):
        kpi_sched_runner = _kpi_card("Runner", "circle", "teal")
        kpi_sched_active = _kpi_card("Actifs / Total", "play_circle", "positive")
        kpi_sched_next = _kpi_card("Prochain fire", "alarm", "teal")
        with ui.card().classes("flex-none self-center"):
            ui.button(
                "→ Scheduler",
                icon="open_in_new",
                on_click=lambda: ui.navigate.to("/scheduler"),
            ).props("flat dense color=teal")

    # ── Jobs table ─────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center q-mb-sm"):
            ui.icon("work").classes("text-primary text-h6")
            ui.label("Jobs enregistrés").classes("text-h6 q-ml-sm")
        jobs_grid = job_table(
            engine,
            on_select=lambda name: ui.navigate.to(f"/job/{name}"),
            height="380px",
        )

    # ── Recent runs table ──────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center justify-between q-mb-sm"):
            with ui.row().classes(_CARD_HDR):
                ui.icon("history").classes("text-secondary text-h6")
                ui.label("Runs récents (job)").classes("text-h6")
            ui.button(
                "Tout voir",
                icon="open_in_new",
                on_click=lambda: ui.navigate.to("/runs"),
            ).props("flat dense")
        try:
            initial_runs = engine.list_job_runs(limit=20)
        except Exception:
            initial_runs = []
        runs_grid = run_table(
            initial_runs,
            on_select=lambda run_id: ui.navigate.to(f"/run/{run_id}"),
        )

    # ── Recent pipeline runs ───────────────────────────────────────────────
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center justify-between q-mb-sm"):
            with ui.row().classes(_CARD_HDR):
                ui.icon("timeline").classes("text-teal text-h6")
                ui.label("Pipeline runs récents").classes("text-h6")
            ui.button(
                "Tout voir",
                icon="open_in_new",
                on_click=lambda: ui.navigate.to("/pipeline-runs"),
            ).props("flat dense")
        try:
            pl_runs = _list_pipeline_runs(engine, limit=10)
        except Exception:
            pl_runs = []
        if pl_runs:
            from pyworkflow_engine.adapters.gui.styles.theme import (
                fmt_dt,
                fmt_ms,
                status_badge_html,
            )

            _pl_grid = ui.aggrid(
                {
                    "columnDefs": [
                        {"headerName": "Pipeline", "field": "pipeline_name", "flex": 2},
                        {
                            "headerName": "Statut",
                            "field": "status_html",
                            "flex": 1,
                            "cellRenderer": "html",
                        },
                        {"headerName": "Stages", "field": "stages", "width": 90},
                        {"headerName": "Créé le", "field": "created_at", "width": 160},
                        {"headerName": "Durée", "field": "duration", "width": 100},
                    ],
                    "rowData": [
                        {
                            "pipeline_run_id": r.pipeline_run_id,
                            "pipeline_name": r.pipeline_name,
                            "status_html": status_badge_html(r.status),
                            "stages": len(r.stage_runs),
                            "created_at": fmt_dt(r.created_at),
                            "duration": fmt_ms(r.duration_ms),
                        }
                        for r in pl_runs
                    ],
                    "defaultColDef": {"resizable": True},
                    "domLayout": "autoHeight",
                    "rowSelection": "single",
                },
                html_columns=[1],
                auto_size_columns=False,
            ).classes("w-full")
            _pl_grid.on(
                "rowSelected",
                lambda e: (
                    ui.navigate.to(f"/pipeline-run/{e.args['data']['pipeline_run_id']}")
                    if e.args.get("selected")
                    else None
                ),
            )
        else:
            ui.label("Aucun pipeline run trouvé.").classes("text-grey-6 text-caption")

    # ── Refresh logic ──────────────────────────────────────────────────────
    def _update_workflow_kpis(jobs: list, runs: list, all_runs: list) -> None:
        from datetime import UTC, datetime, timedelta

        running = sum(1 for r in runs if r.status == RunStatus.RUNNING)
        suspended = sum(1 for r in runs if r.status in SUSPENDED_STATUSES)
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        failed_24h = sum(
            1
            for r in all_runs
            if r.status == RunStatus.FAILED
            and r.start_time
            and r.start_time.replace(
                tzinfo=UTC if r.start_time.tzinfo is None else r.start_time.tzinfo
            )
            >= cutoff
        )
        terminal = [
            r for r in all_runs if r.status in (RunStatus.SUCCESS, RunStatus.FAILED)
        ]
        success_rate = (
            f"{sum(1 for r in terminal if r.status == RunStatus.SUCCESS) / len(terminal) * 100:.0f}%"
            if terminal
            else "—"
        )
        try:
            total_runs = engine.count_job_runs()
        except Exception:
            total_runs = len(all_runs)

        kpi_jobs.set_text(str(len(jobs)))
        kpi_runs.set_text(str(total_runs))
        kpi_running.set_text(str(running))
        kpi_failed.set_text(str(failed_24h))
        kpi_suspended.set_text(str(suspended))
        kpi_success_rate.set_text(success_rate)

    def _update_pipeline_kpis(pl_runs_list: list) -> None:
        pl_running = sum(1 for r in pl_runs_list if r.status == RunStatus.RUNNING)
        pl_failed = sum(1 for r in pl_runs_list if r.status == RunStatus.FAILED)
        pl_ok = sum(1 for r in pl_runs_list if r.status == RunStatus.SUCCESS)
        kpi_pipeline_runs.set_text(str(len(pl_runs_list)))
        kpi_pipeline_running.set_text(str(pl_running))
        kpi_pipeline_failed.set_text(str(pl_failed))
        kpi_pipeline_ok.set_text(str(pl_ok))

    def _update_ai_kpis() -> None:
        agents = _list_agents(engine)
        runs = _list_agent_runs(engine)
        total_tokens = sum((r.get("total_tokens") or 0) for r in runs)
        kpi_agents.set_text(str(len(agents)))
        kpi_executions.set_text(str(len(runs)))
        kpi_conversations.set_text(str(len(runs)))
        kpi_tokens.set_text(_fmt_tokens(total_tokens))

    def _update_scheduler_kpis() -> None:
        from pyworkflow_engine.adapters.gui.views.scheduler import (  # noqa: PLC0415
            _excluded_jobs,
            _human_delta,
            _load_manifest,
            _next_fire,
            _runner_pid,
        )

        pid = _runner_pid()
        jobs = _load_manifest()
        excluded = _excluded_jobs()
        total = len(jobs)
        active = total - len(excluded)

        # Runner badge
        if pid:
            kpi_sched_runner.set_text("ACTIF")
            kpi_sched_runner.classes(
                "text-positive", remove="text-negative text-grey-6"
            )
        else:
            kpi_sched_runner.set_text("ARRÊTÉ")
            kpi_sched_runner.classes(
                "text-negative", remove="text-positive text-grey-6"
            )

        kpi_sched_active.set_text(f"{active} / {total}")

        # Prochain fire parmi les actifs
        nxt_global = None
        for job in jobs:
            if job["name"] in excluded:
                continue
            nxt = _next_fire(job["schedule"])
            if nxt and (nxt_global is None or nxt < nxt_global):
                nxt_global = nxt
        if nxt_global and pid:
            kpi_sched_next.set_text(
                nxt_global.strftime("%H:%M") + f"  ({_human_delta(nxt_global)})"
            )
        else:
            kpi_sched_next.set_text("—")

    def refresh() -> None:
        jobs = engine.list_jobs()
        try:
            runs = engine.list_job_runs(limit=20)
        except Exception:
            runs = []
        try:
            all_runs = engine.list_job_runs(limit=500)
        except Exception:
            all_runs = runs
        _update_workflow_kpis(jobs, runs, all_runs)
        refresh_job_table(jobs_grid, engine)
        refresh_run_table(runs_grid, runs)
        # Pipelines
        pl_runs_list = _list_pipeline_runs(engine)
        _update_pipeline_kpis(pl_runs_list)
        # AI (less frequent — only update labels, don't refresh grid)
        _update_ai_kpis()
        # Scheduler
        _update_scheduler_kpis()

    # Populate KPI labels immediately (labels are server-side, safe to set now).
    try:
        _initial_jobs = engine.list_jobs()
        _initial_runs = engine.list_job_runs(limit=20)
        _all_runs = engine.list_job_runs(limit=500)
    except Exception:
        _initial_jobs, _initial_runs, _all_runs = [], [], []
    _update_workflow_kpis(_initial_jobs, _initial_runs, _all_runs)

    _initial_pl = _list_pipeline_runs(engine)
    _update_pipeline_kpis(_initial_pl)

    _update_ai_kpis()

    _update_scheduler_kpis()

    def _safe_refresh() -> None:
        try:
            refresh()
        except Exception:  # noqa: BLE001
            pass

    t = ui.timer(config.refresh_interval, _safe_refresh)

    # The RuntimeError("The parent slot of the element has been deleted.")
    # is raised inside NiceGUI's timer._get_context() — *before* the callback
    # runs — so a try/except in the callback is insufficient.
    # We monkey-patch _get_context on this instance so that once the parent
    # slot is gone the timer silently cancels itself instead of logging a
    # traceback on every tick.
    from contextlib import nullcontext  # noqa: PLC0415

    _original_get_context = t._get_context  # type: ignore[attr-defined]

    def _safe_get_context():  # type: ignore[return]
        try:
            return _original_get_context()
        except RuntimeError:
            t.cancel()
            return nullcontext()

    t._get_context = _safe_get_context  # type: ignore[method-assign]


def _kpi_card(title: str, icon: str, color: str) -> ui.label:
    """Crée une petite carte KPI et retourne le label de valeur."""
    with ui.card().classes("flex-1 min-w-[140px]"):
        with ui.column().classes("gap-1"):
            with ui.row().classes(_CARD_HDR):
                ui.icon(icon).classes(f"text-{color} text-h5")
                ui.label(title).classes("text-caption text-grey-6")
            value_label = ui.label("…").classes("text-h4 text-bold")
    return value_label


# ── Helpers data fetching ─────────────────────────────────────────────────────


def _list_pipeline_runs(engine: WorkflowEngine, limit: int = 100) -> list:
    storage = getattr(engine, "_storage", None)
    if storage is None:
        return []
    try:
        return storage.list_pipeline_runs(limit=limit)
    except Exception:
        return []


def _get_ai_storage(engine: WorkflowEngine):
    return getattr(engine, "ai_storage", None)


def _list_agents(engine: WorkflowEngine) -> list:
    ai_storage = _get_ai_storage(engine)
    if ai_storage and hasattr(ai_storage, "list_agents"):
        try:
            return ai_storage.list_agents()
        except Exception:
            pass
    try:
        return engine.list_agents()
    except Exception:
        return []


def _list_agent_runs(engine: WorkflowEngine) -> list[dict]:
    """Lit les conversations depuis ai_conversations via SQLiteAIStorage."""
    ai_storage = _get_ai_storage(engine)
    if ai_storage is None:
        return []
    try:
        convs = ai_storage.list_conversations()
        return [
            {
                "total_tokens": c.total_tokens or 0,
                "status": c.status.value,
                "agent_id": c.agent_id,
            }
            for c in convs
        ]
    except Exception:
        return []


def _fmt_tokens(n: int) -> str:
    """Formate un nombre de tokens de façon compacte."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n) if n else "—"
