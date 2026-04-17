"""Vue Exécutions IA — historique des exécutions d'agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.status_badge import status_badge
from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.adapters.gui.styles.theme import fmt_dt, fmt_ms, status_badge_html
from pyworkflow_engine.models.enums import RunStatus

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_executions_page(
    engine: WorkflowEngine,
    config: GUIConfig,
    agent_filter: str | None = None,
) -> None:
    """Construit la page historique des exécutions IA (/executions)."""
    page_toolbar("Exécutions IA", icon="bolt", icon_color="orange")

    # ── Filtres ────────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-4 flex-wrap"):
            agent_input = ui.input(
                "Filtrer par agent (ID/slug)",
                placeholder="ID ou slug de l'agent…",
                value=agent_filter or "",
            ).classes("min-w-[240px]")
            status_select = ui.select(
                options=[""] + [s.value for s in RunStatus],
                value="",
                label="Statut",
            ).classes("min-w-[160px]")
            limit_input = ui.number(
                "Limite", value=100, min=10, max=1000, step=10
            ).classes("w-24")
            ui.button(
                "Appliquer", icon="search", on_click=lambda: refresh()
            ).props("color=primary")

    # ── Table exécutions ───────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        exec_count = ui.label("").classes("text-caption text-grey-6 q-mb-xs")
        try:
            initial_execs = _fetch_executions(engine, agent_filter, None, 100)
        except Exception:
            initial_execs = []
        exec_count.set_text(f"{len(initial_execs)} exécution(s) trouvée(s)")
        grid = _execution_table(
            initial_execs,
            on_select=lambda eid: ui.navigate.to(f"/execution/{eid}"),
        )

    def refresh() -> None:
        agent_id = agent_input.value.strip() or None
        status_val = status_select.value or None
        limit = int(limit_input.value or 100)
        try:
            execs = _fetch_executions(engine, agent_id, status_val, limit)
        except Exception:
            execs = []
        exec_count.set_text(f"{len(execs)} exécution(s) trouvée(s)")
        _refresh_execution_table(grid, execs)


def build_execution_detail(
    engine: WorkflowEngine, config: GUIConfig, exec_id: str
) -> None:
    """Construit la page de détail d'une exécution IA (/execution/{id})."""
    page_toolbar(
        exec_id[:16] + "…",
        icon="bolt",
        icon_color="orange",
        back_url="/executions",
        subtitle="Détail de l'exécution IA",
    )

    execution = _get_execution(engine, exec_id)
    if execution is None:
        ui.label(f"Exécution « {exec_id} » introuvable.").classes(
            "text-negative text-h6"
        )
        return

    # ── Header ─────────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-6 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label("Statut").classes("text-caption text-grey-6")
                status_badge(execution.status)

            _info_cell("Agent ID", execution.agent_id[:14] + "…" if len(execution.agent_id) > 14 else execution.agent_id)
            _info_cell("Steps", str(execution.total_steps))
            _info_cell("Démarré", fmt_dt(execution.started_at))
            _info_cell("Terminé", fmt_dt(execution.completed_at))
            _info_cell(
                "Durée",
                fmt_ms(
                    int(
                        (execution.completed_at - execution.started_at).total_seconds() * 1000
                    )
                    if execution.started_at and execution.completed_at
                    else None
                ),
            )

        # Token usage
        usage = getattr(execution, "token_usage", None)
        if usage:
            with ui.row().classes("items-center gap-4 q-mt-sm flex-wrap"):
                ui.icon("token").classes("text-orange")
                ui.label("Tokens :").classes("text-caption text-grey-6")
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
                ui.label(f"prompt={prompt_tokens}").classes("text-caption")
                ui.label(f"completion={completion_tokens}").classes("text-caption")
                ui.label(f"total={total_tokens}").classes("text-caption text-bold")

        if execution.error:
            with ui.row().classes("q-mt-sm"):
                ui.icon("error").classes("text-negative")
                ui.label(execution.error).classes("text-caption text-negative q-ml-xs")

    # ── Input / Output ─────────────────────────────────────────────────────
    with ui.row().classes("w-full gap-4 q-mb-md"):
        if execution.input_data:
            with ui.card().classes("flex-1"):
                ui.label("Données d'entrée").classes("text-subtitle1 text-bold q-mb-sm")
                ui.code(str(execution.input_data), language="python").classes("w-full")

        if execution.output_data:
            with ui.card().classes("flex-1"):
                ui.label("Données de sortie").classes("text-subtitle1 text-bold q-mb-sm")
                ui.code(str(execution.output_data), language="python").classes("w-full")

    # ── Steps IA ───────────────────────────────────────────────────────────
    exec_steps = _get_execution_steps(engine, exec_id)
    if exec_steps:
        with ui.card().classes("w-full q-mb-md"):
            ui.label(f"Steps IA ({len(exec_steps)})").classes(
                "text-subtitle1 text-bold q-mb-sm"
            )
            ui.aggrid(
                {
                    "columnDefs": [
                        {
                            "headerName": "#",
                            "field": "order",
                            "width": 60,
                            "type": "numericColumn",
                        },
                        {"headerName": "Type", "field": "step_type", "width": 130},
                        {"headerName": "Agent", "field": "agent_id", "width": 120},
                        {"headerName": "Tool", "field": "tool_id", "width": 120},
                        {"headerName": "Tokens", "field": "tokens", "width": 100},
                        {"headerName": "Coût ($)", "field": "cost", "width": 100},
                        {"headerName": "Durée", "field": "duration", "width": 100},
                        {"headerName": "Erreur", "field": "error", "flex": 2},
                    ],
                    "rowData": [
                        {
                            "order": s.order,
                            "step_type": s.step_type.value
                            if hasattr(s.step_type, "value")
                            else str(s.step_type),
                            "agent_id": s.agent_id[:10] + "…"
                            if s.agent_id and len(s.agent_id) > 10
                            else (s.agent_id or "—"),
                            "tool_id": s.tool_id[:10] + "…"
                            if s.tool_id and len(s.tool_id) > 10
                            else (s.tool_id or "—"),
                            "tokens": s.tokens_used or 0,
                            "cost": f"{s.cost:.6f}" if s.cost else "0.000000",
                            "duration": fmt_ms(s.duration_ms),
                            "error": s.error or "—",
                        }
                        for s in sorted(exec_steps, key=lambda x: x.order)
                    ],
                    "defaultColDef": {"resizable": True},
                    "domLayout": "autoHeight",
                },
                auto_size_columns=False,
            ).classes("w-full")

    # ── Métadonnées ────────────────────────────────────────────────────────
    if execution.metadata:
        with ui.card().classes("w-full"):
            ui.label("Métadonnées").classes("text-subtitle1 text-bold q-mb-sm")
            ui.code(str(execution.metadata), language="python").classes("w-full")


def _execution_table(executions: list, on_select=None) -> ui.aggrid:
    grid = ui.aggrid(
        {
            "columnDefs": [
                {"headerName": "_exec_id", "field": "_exec_id", "hide": True},
                {"headerName": "Agent ID", "field": "agent_id", "flex": 1},
                {
                    "headerName": "Statut",
                    "field": "status_html",
                    "flex": 1,
                    "cellRenderer": "html",
                },
                {"headerName": "Steps", "field": "steps", "width": 80},
                {"headerName": "Tokens", "field": "tokens", "width": 100},
                {"headerName": "Coût ($)", "field": "cost", "width": 100},
                {"headerName": "Démarré", "field": "started_at", "width": 160},
                {"headerName": "Durée", "field": "duration", "width": 100},
            ],
            "rowData": _execs_to_rows(executions),
            "defaultColDef": {
                "resizable": True,
                "filter": True,
                "sortable": True,
            },
            "domLayout": "normal",
            "rowSelection": {"mode": "singleRow"},
        },
        html_columns=[1],
        auto_size_columns=False,
    ).classes("w-full").style("height: 480px")
    if on_select:
        grid.on("rowClicked", lambda e: on_select((e.args or {}).get("data", {}).get("_exec_id", "")) if (e.args or {}).get("data", {}).get("_exec_id") else None)
    return grid


def _refresh_execution_table(grid: ui.aggrid, executions: list) -> None:
    grid.options["rowData"] = _execs_to_rows(executions)
    grid.update()


def _execs_to_rows(executions: list) -> list[dict]:
    rows = []
    for e in executions:
        usage = getattr(e, "token_usage", None)
        total_tokens = 0
        total_cost = 0.0
        if usage:
            total_tokens = getattr(usage, "total_tokens", 0) or 0
            total_cost = getattr(usage, "cost", 0.0) or 0.0
        duration_ms = None
        if e.started_at and e.completed_at:
            duration_ms = int(
                (e.completed_at - e.started_at).total_seconds() * 1000
            )
        rows.append(
            {
                "_exec_id": e.id,
                "agent_id": e.agent_id[:14] + "…"
                if len(e.agent_id) > 14
                else e.agent_id,
                "status_html": status_badge_html(e.status),
                "steps": e.total_steps,
                "tokens": total_tokens,
                "cost": f"{total_cost:.6f}",
                "started_at": fmt_dt(e.started_at),
                "duration": fmt_ms(duration_ms),
            }
        )
    return rows


def _fetch_executions(
    engine: WorkflowEngine,
    agent_id: str | None,
    status: str | None,
    limit: int,
) -> list:
    ai_storage = _get_ai_storage(engine)
    if ai_storage is None:
        return []
    try:
        kwargs: dict = {}
        if agent_id:
            kwargs["agent_id"] = agent_id
        if status:
            kwargs["status"] = status
        if hasattr(ai_storage, "list_executions"):
            return ai_storage.list_executions(**kwargs)
    except Exception:
        pass
    return []


def _get_execution(engine: WorkflowEngine, exec_id: str):
    ai_storage = _get_ai_storage(engine)
    if ai_storage is None:
        return None
    try:
        if hasattr(ai_storage, "get_execution"):
            return ai_storage.get_execution(exec_id)
    except Exception:
        pass
    return None


def _get_execution_steps(engine: WorkflowEngine, exec_id: str) -> list:
    ai_storage = _get_ai_storage(engine)
    if ai_storage is None:
        return []
    try:
        if hasattr(ai_storage, "get_execution_steps"):
            return ai_storage.get_execution_steps(exec_id)
    except Exception:
        pass
    return []


def _get_ai_storage(engine: WorkflowEngine):
    """Retourne le backend AI storage si disponible."""
    # Tente d'accéder via _cached_ai_service ou _ai_storage
    ai_service = getattr(engine, "_cached_ai_service", None)
    if ai_service:
        return getattr(ai_service, "storage", None)
    ai_storage = getattr(engine, "_ai_storage", None)
    return ai_storage


def _info_cell(label: str, value: str) -> None:
    with ui.column().classes("gap-1"):
        ui.label(label).classes("text-caption text-grey-6")
        ui.label(value).classes("text-body2 text-bold")
