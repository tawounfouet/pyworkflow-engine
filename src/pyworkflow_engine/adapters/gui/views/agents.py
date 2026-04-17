"""Vue Agents IA — liste des agents + détail d'un agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.adapters.gui.styles.theme import fmt_dt

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_agents_page(engine: WorkflowEngine, config: GUIConfig) -> None:
    """Construit la page liste des agents IA (/agents)."""
    page_toolbar("Agents IA", icon="smart_toy", icon_color="deep-purple")

    agents = _list_agents(engine)

    # ── KPI cards ──────────────────────────────────────────────────────────
    with ui.row().classes("w-full gap-4 q-mb-md"):
        with ui.card().classes("flex-1 min-w-[140px]"):
            with ui.column().classes("gap-1"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("smart_toy").classes("text-deep-purple text-h5")
                    ui.label("Total agents").classes("text-caption text-grey-6")
                ui.label(str(len(agents))).classes("text-h4 text-bold")
        active = sum(1 for a in agents if getattr(a, "is_active", True))
        with ui.card().classes("flex-1 min-w-[140px]"):
            with ui.column().classes("gap-1"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check_circle").classes("text-positive text-h5")
                    ui.label("Actifs").classes("text-caption text-grey-6")
                ui.label(str(active)).classes("text-h4 text-bold")
        roles = len({getattr(a, "role", "") for a in agents})
        with ui.card().classes("flex-1 min-w-[140px]"):
            with ui.column().classes("gap-1"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("groups").classes("text-secondary text-h5")
                    ui.label("Rôles distincts").classes("text-caption text-grey-6")
                ui.label(str(roles)).classes("text-h4 text-bold")

    # ── Table agents ───────────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center justify-between q-mb-sm"):
            ui.label(f"{len(agents)} agent(s)").classes("text-caption text-grey-6")
            ui.button(
                "Rafraîchir",
                icon="refresh",
                on_click=lambda: ui.navigate.reload(),
            ).props("flat dense")

        if not agents:
            ui.label("Aucun agent IA enregistré.").classes("text-grey-6 q-pa-md")
            return

        grid = (
            ui.aggrid(
                {
                    "columnDefs": [
                        {"headerName": "_agent_id", "field": "_agent_id", "hide": True},
                        {
                            "headerName": "Nom",
                            "field": "name",
                            "flex": 2,
                            "cellStyle": {
                                "cursor": "pointer",
                                "color": "var(--q-primary)",
                            },
                        },
                        {"headerName": "Slug", "field": "slug", "width": 160},
                        {"headerName": "Rôle", "field": "role", "width": 130},
                        {"headerName": "Modèle", "field": "model", "width": 160},
                        {"headerName": "Provider", "field": "provider_id", "flex": 1},
                        {
                            "headerName": "Actif",
                            "field": "is_active",
                            "width": 80,
                            "cellRenderer": "agCheckboxCellRenderer",
                        },
                        {
                            "headerName": "Mémoire",
                            "field": "enable_memory",
                            "width": 100,
                        },
                        {"headerName": "Outils", "field": "tools", "width": 80},
                        {"headerName": "Skills", "field": "skills", "width": 80},
                        {"headerName": "Créé le", "field": "created_at", "width": 160},
                        {
                            "headerName": "Description",
                            "field": "description",
                            "flex": 2,
                        },
                    ],
                    "rowData": [
                        {
                            "_agent_id": a.id,
                            "name": a.name,
                            "slug": a.slug or "—",
                            "role": (
                                a.role.value
                                if hasattr(a.role, "value")
                                else str(a.role)
                            ),
                            "model": a.model or "(provider default)",
                            "provider_id": (
                                a.provider_id[:14] + "…"
                                if len(a.provider_id) > 14
                                else a.provider_id
                            ),
                            "is_active": a.is_active,
                            "enable_memory": (
                                "Oui"
                                if getattr(a.config, "enable_memory", False)
                                else "Non"
                            ),
                            "tools": len(a.tool_ids),
                            "skills": len(a.skill_ids),
                            "created_at": fmt_dt(a.created_at),
                            "description": a.description or "—",
                        }
                        for a in agents
                    ],
                    "defaultColDef": {
                        "resizable": True,
                        "filter": True,
                        "sortable": True,
                    },
                    "domLayout": "normal",
                    "rowSelection": {"mode": "singleRow"},
                },
                auto_size_columns=False,
            )
            .classes("w-full")
            .style("height: 480px")
        )

        def _on_cell_click(e: dict) -> None:
            agent_id = (e.args or {}).get("data", {}).get("_agent_id", "")
            if agent_id:
                ui.navigate.to(f"/agent/{agent_id}")

        grid.on("cellClicked", _on_cell_click)


def build_agent_detail_page(
    engine: WorkflowEngine, config: GUIConfig, agent_id: str
) -> None:
    """Construit la page détail d'un agent (/agent/{id})."""
    agent = _get_agent(engine, agent_id)

    if agent is None:
        page_toolbar(
            agent_id,
            icon="smart_toy",
            icon_color="deep-purple",
            back_url="/agents",
            subtitle="Détail de l'agent IA",
        )
        ui.label(f"Agent « {agent_id} » introuvable.").classes("text-negative text-h6")
        return

    page_toolbar(
        agent.name,
        icon="smart_toy",
        icon_color="deep-purple",
        back_url="/agents",
        subtitle=f"ID : {agent.id}",
    )

    # ── Identité ───────────────────────────────────────────────────────────
    with ui.row().classes("w-full gap-4 q-mb-md"):
        with ui.card().classes("flex-1"):
            ui.label("Identité").classes("text-subtitle1 text-bold q-mb-sm")
            _meta_row("ID", agent.id)
            _meta_row("Nom", agent.name)
            _meta_row("Slug", agent.slug or "—")
            _meta_row(
                "Rôle",
                agent.role.value if hasattr(agent.role, "value") else str(agent.role),
            )
            _meta_row("Actif", "Oui" if agent.is_active else "Non")
            _meta_row("Owner", agent.owner_id or "—")
            _meta_row("Créé le", fmt_dt(agent.created_at))
            _meta_row("Modifié le", fmt_dt(agent.updated_at))

        with ui.card().classes("flex-1"):
            ui.label("LLM").classes("text-subtitle1 text-bold q-mb-sm")
            _meta_row("Provider ID", agent.provider_id)
            _meta_row("Modèle override", agent.model or "(provider default)")
            cfg = agent.config
            _meta_row("Max itérations", str(cfg.max_iterations))
            _meta_row("Max tokens / run", str(cfg.max_tokens_per_run))
            _meta_row(
                "Température",
                (
                    str(cfg.temperature)
                    if cfg.temperature is not None
                    else "(provider default)"
                ),
            )
            _meta_row("Mémoire", "Oui" if cfg.enable_memory else "Non")
            _meta_row("Outils", "Oui" if cfg.enable_tools else "Non")
            _meta_row("RAG", "Oui" if cfg.enable_rag else "Non")
            _meta_row("Retry", "Oui" if cfg.retry_on_failure else "Non")
            _meta_row("Max retries", str(cfg.max_retries))

    # ── Description ────────────────────────────────────────────────────────
    if agent.description:
        with ui.card().classes("w-full q-mb-md"):
            ui.label("Description").classes("text-subtitle1 text-bold q-mb-sm")
            ui.label(agent.description).classes("text-body2")

    # ── System prompt ──────────────────────────────────────────────────────
    if agent.system_prompt:
        with ui.card().classes("w-full q-mb-md"):
            ui.label("System Prompt").classes("text-subtitle1 text-bold q-mb-sm")
            ui.textarea(value=agent.system_prompt).props(
                "readonly outlined autogrow"
            ).classes("w-full font-mono text-caption")

    # ── Welcome message ────────────────────────────────────────────────────
    if agent.welcome_message:
        with ui.card().classes("w-full q-mb-md"):
            ui.label("Message d'accueil").classes("text-subtitle1 text-bold q-mb-sm")
            ui.label(agent.welcome_message).classes("text-body2")

    # ── Tools / Skills / Knowledge ─────────────────────────────────────────
    with ui.row().classes("w-full gap-4 q-mb-md"):
        if agent.tool_ids:
            with ui.card().classes("flex-1"):
                ui.label(f"Outils ({len(agent.tool_ids)})").classes(
                    "text-subtitle1 text-bold q-mb-sm"
                )
                for tid in agent.tool_ids:
                    with ui.row().classes("items-center gap-1 q-mb-xs"):
                        ui.icon("build").classes("text-secondary")
                        ui.label(tid).classes("text-caption text-mono")

        if agent.skill_ids:
            with ui.card().classes("flex-1"):
                ui.label(f"Skills ({len(agent.skill_ids)})").classes(
                    "text-subtitle1 text-bold q-mb-sm"
                )
                for sid in agent.skill_ids:
                    with ui.row().classes("items-center gap-1 q-mb-xs"):
                        ui.icon("psychology").classes("text-deep-purple")
                        ui.label(sid).classes("text-caption text-mono")

        if agent.knowledge_base_ids:
            with ui.card().classes("flex-1"):
                ui.label(f"Knowledge bases ({len(agent.knowledge_base_ids)})").classes(
                    "text-subtitle1 text-bold q-mb-sm"
                )
                for kid in agent.knowledge_base_ids:
                    with ui.row().classes("items-center gap-1 q-mb-xs"):
                        ui.icon("library_books").classes("text-teal")
                        ui.label(kid).classes("text-caption text-mono")

    # ── Actions ────────────────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("Actions").classes("text-subtitle1 text-bold q-mb-sm")
        with ui.row().classes("gap-2 flex-wrap"):
            ui.button(
                "💬  Conversations",
                color="primary",
                on_click=lambda: ui.navigate.to(f"/conversations?agent={agent.id}"),
            ).props("outline")
            ui.button(
                "📊  Exécutions",
                color="secondary",
                on_click=lambda: ui.navigate.to(f"/executions?agent={agent.id}"),
            ).props("outline")


def _list_agents(engine: WorkflowEngine) -> list:
    # Prefer AI storage (UnifiedStorage backed by workflow.db)
    ai_storage = _get_ai_storage(engine)
    if ai_storage and hasattr(ai_storage, "list_agents"):
        try:
            return ai_storage.list_agents()
        except Exception:
            pass
    # Fallback: in-memory service
    try:
        return engine.list_agents()
    except Exception:
        return []


def _get_agent(engine: WorkflowEngine, agent_id: str):
    ai_storage = _get_ai_storage(engine)
    if ai_storage:
        result = _agent_from_storage(ai_storage, agent_id)
        if result:
            return result
    try:
        return engine.get_agent(agent_id) or None
    except Exception:
        return None


def _agent_from_storage(ai_storage, agent_id: str):
    """Cherche un agent par ID, slug ou nom dans le storage IA."""
    result = _try_fetch(ai_storage, "get_agent", agent_id)
    if result:
        return result
    result = _try_fetch(ai_storage, "get_agent_by_slug", agent_id)
    if result:
        return result
    return _scan_agents_by_name(ai_storage, agent_id)


def _try_fetch(storage, method: str, key: str):
    """Appelle storage.<method>(key) et retourne le résultat ou None."""
    if not hasattr(storage, method):
        return None
    try:
        return getattr(storage, method)(key) or None
    except Exception:
        return None


def _scan_agents_by_name(ai_storage, name: str):
    """Scan linéaire de la liste des agents par nom."""
    if not hasattr(ai_storage, "list_agents"):
        return None
    try:
        return next((a for a in ai_storage.list_agents() if a.name == name), None)
    except Exception:
        return None


def _get_ai_storage(engine: WorkflowEngine):
    """Retourne le backend AI storage branché sur le moteur."""
    return getattr(engine, "ai_storage", None)


def _meta_row(label: str, value: str) -> None:
    with ui.row().classes("items-start gap-2 q-mb-xs"):
        ui.label(label + " :").classes("text-caption text-grey-6 w-32")
        ui.label(value).classes("text-body2")
