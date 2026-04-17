"""Vue Conversations IA — historique des conversations + messages (ai_conversations / ai_messages)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar
from pyworkflow_engine.adapters.gui.styles.theme import fmt_dt, fmt_ms

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine

_ROLE_COLOR: dict[str, str] = {
    "user": "primary",
    "assistant": "positive",
    "system": "grey-7",
    "tool": "orange",
}
_ROLE_ICON: dict[str, str] = {
    "user": "person",
    "assistant": "smart_toy",
    "system": "settings",
    "tool": "build",
}


# ── Pages ─────────────────────────────────────────────────────────────────────


def build_conversations_page(
    engine: WorkflowEngine,
    config: GUIConfig,
    agent_filter: str | None = None,
) -> None:
    """Construit la page liste des conversations (/conversations)."""
    page_toolbar("Conversations IA", icon="chat", icon_color="teal-8")

    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-4 flex-wrap"):
            agent_input = ui.input(
                "Filtrer par agent (slug)",
                placeholder="general-assistant…",
                value=agent_filter or "",
            ).classes("min-w-[220px]")
            status_select = ui.select(
                options=["", "active", "completed", "archived"],
                value="",
                label="Statut",
            ).classes("min-w-[140px]")
            limit_input = ui.number("Limite", value=50, min=5, max=500, step=5).classes(
                "w-24"
            )
            ui.button("Appliquer", icon="search", on_click=lambda: refresh()).props(
                "color=primary"
            )

    with ui.card().classes("w-full"):
        conv_count = ui.label("").classes("text-caption text-grey-6 q-mb-xs")
        storage = _get_ai_storage(engine)
        initial_convs = _fetch_conversations(storage, agent_filter, None, 50)
        conv_count.set_text(f"{len(initial_convs)} conversation(s) trouvée(s)")
        grid = _conversations_table(
            initial_convs,
            storage,
            on_select=lambda cid: ui.navigate.to(f"/conversation/{cid}"),
        )

    def refresh() -> None:
        agent = agent_input.value.strip() or None
        status = status_select.value or None
        limit = int(limit_input.value or 50)
        convs = _fetch_conversations(storage, agent, status, limit)
        conv_count.set_text(f"{len(convs)} conversation(s) trouvée(s)")
        _refresh_conversations_table(grid, convs, storage)


def build_conversation_detail(
    engine: WorkflowEngine, config: GUIConfig, conv_id: str
) -> None:
    """Construit la page de détail d'une conversation (/conversation/{id})."""
    storage = _get_ai_storage(engine)
    conv = storage.get_conversation(conv_id) if storage else None

    if conv is None:
        page_toolbar(
            conv_id[:16] + "…",
            icon="chat",
            icon_color="teal-8",
            back_url="/conversations",
            subtitle="Conversation introuvable",
        )
        ui.label(f"Conversation « {conv_id} » introuvable.").classes(
            "text-negative text-h6"
        )
        return

    agent_slug = "—"
    agent_name = "—"
    if storage and conv.agent_id:
        try:
            ag = storage.get_agent(conv.agent_id)
            if ag:
                agent_slug = ag.slug or ag.name
                agent_name = ag.name
        except Exception:
            pass

    meta = conv.metadata or {}
    mode = meta.get("mode", "—")
    model = meta.get("model", "—")
    provider = meta.get("provider", "—")
    triggered_by = meta.get("triggered_by", "—")

    page_toolbar(
        agent_name,
        icon="chat",
        icon_color="teal-8",
        back_url="/conversations",
        subtitle=f"Conv {conv.id[:16]}… · {mode} · {conv.status.value}",
    )

    messages = storage.get_messages(conv_id) if storage else []
    visible = [m for m in messages if m.role.value in ("user", "assistant", "tool")]

    # Calculer les métriques réelles si les compteurs du modèle sont à 0
    real_msg_count = conv.message_count or len(
        [m for m in messages if m.role.value in ("user", "assistant")]
    )
    real_tokens = conv.total_tokens or sum(
        (m.metadata or {}).get("total_tokens") or 0 for m in messages
    )

    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-6 flex-wrap"):
            _info_cell("Agent", agent_name)
            _info_cell("Slug", agent_slug)
            _info_cell("Modèle", model)
            _info_cell("Provider", provider)
            _info_cell("Mode", mode)
            _info_cell("Statut", conv.status.value)
            _info_cell("Messages", str(real_msg_count))
            _info_cell("Tokens", str(real_tokens))
            _info_cell("Démarré", fmt_dt(conv.created_at))
            _info_cell("Déclenché par", triggered_by)

        error = meta.get("error")
        if error:
            with ui.row().classes("q-mt-sm"):
                ui.icon("error").classes("text-negative")
                ui.label(error).classes("text-caption text-negative q-ml-xs")

    if not visible:
        with ui.card().classes("w-full"):
            ui.label("Aucun message enregistré pour cette conversation.").classes(
                "text-grey-6 q-pa-md"
            )
        return

    with ui.card().classes("w-full"):
        ui.label(f"Messages ({len(visible)})").classes(
            "text-subtitle1 text-bold q-mb-md"
        )
        with ui.column().classes("w-full gap-3"):
            for msg in visible:
                _render_message(msg)


# ── Rendering ─────────────────────────────────────────────────────────────────


def _render_message(msg) -> None:
    role = msg.role.value
    color = _ROLE_COLOR.get(role, "grey")
    icon = _ROLE_ICON.get(role, "chat_bubble")
    is_user = role == "user"
    align = "items-end" if is_user else "items-start"
    bubble_cls = "q-pa-sm rounded-borders " + (
        "bg-primary text-white max-w-[70%]"
        if is_user
        else "bg-grey-2 text-dark max-w-[70%]"
    )
    with ui.row().classes(f"w-full {align}"):
        if not is_user:
            ui.icon(icon).classes(f"text-{color} text-h6 self-start q-mt-xs")
        with ui.column().classes("gap-1"):
            with ui.row().classes("items-center gap-2"):
                ui.label(role.upper()).classes(f"text-caption text-bold text-{color}")
                if msg.created_at:
                    ui.label(fmt_dt(msg.created_at)).classes("text-caption text-grey-5")
            if msg.content:
                with ui.element("div").classes(bubble_cls):
                    ui.label(msg.content).style(
                        "white-space: pre-wrap; word-break: break-word;"
                    )
            # Token / latency info from message metadata
            meta = msg.metadata or {}
            total = meta.get("total_tokens")
            if total:
                parts = [f"tokens: {total}"]
                mdl = meta.get("model", "")
                rt = meta.get("response_time_ms")
                if mdl:
                    parts.append(mdl)
                if rt:
                    parts.append(f"{float(rt):.0f}ms")
                ui.label(" · ".join(parts)).classes("text-caption text-grey-5")


# ── AG Grid helpers ───────────────────────────────────────────────────────────


def _conversations_table(convs, storage, on_select=None) -> ui.aggrid:
    grid = (
        ui.aggrid(
            {
                "columnDefs": [
                    {"headerName": "_conv_id", "field": "_conv_id", "hide": True},
                    {
                        "headerName": "Agent",
                        "field": "agent_name",
                        "flex": 2,
                        "cellStyle": {"cursor": "pointer", "color": "var(--q-primary)"},
                    },
                    {"headerName": "Slug", "field": "agent_slug", "width": 160},
                    {"headerName": "Mode", "field": "mode", "width": 100},
                    {"headerName": "Statut", "field": "status", "width": 110},
                    {"headerName": "Messages", "field": "message_count", "width": 100},
                    {"headerName": "Tokens", "field": "total_tokens", "width": 90},
                    {"headerName": "Modèle", "field": "model", "width": 140},
                    {
                        "headerName": "Déclenché par",
                        "field": "triggered_by",
                        "width": 130,
                    },
                    {"headerName": "Créé le", "field": "created_at", "width": 160},
                ],
                "rowData": _convs_to_rows(convs, storage),
                "defaultColDef": {"resizable": True, "filter": True, "sortable": True},
                "domLayout": "normal",
                "rowSelection": {"mode": "singleRow"},
            },
            auto_size_columns=False,
        )
        .classes("w-full")
        .style("height: 480px")
    )

    if on_select:

        def _on_cell_click(e: dict) -> None:
            cid = (e.args or {}).get("data", {}).get("_conv_id", "")
            if cid:
                on_select(cid)

        grid.on("cellClicked", _on_cell_click)

    return grid


def _refresh_conversations_table(grid: ui.aggrid, convs, storage) -> None:
    grid.options["rowData"] = _convs_to_rows(convs, storage)
    grid.update()


def _convs_to_rows(convs, storage) -> list[dict]:
    rows = []
    for c in convs:
        agent_slug = "—"
        agent_name = "—"
        if storage and c.agent_id:
            try:
                ag = storage.get_agent(c.agent_id)
                if ag:
                    agent_slug = ag.slug or ag.name
                    agent_name = ag.name
            except Exception:
                pass
        meta = c.metadata or {}
        # Compter les messages réels si les compteurs du modèle sont à 0
        msg_count = c.message_count or 0
        total_tokens = c.total_tokens or 0
        if (msg_count == 0 or total_tokens == 0) and storage:
            try:
                msgs = storage.get_messages(c.id)
                if msg_count == 0:
                    msg_count = len(
                        [m for m in msgs if m.role.value in ("user", "assistant")]
                    )
                if total_tokens == 0:
                    total_tokens = sum(
                        (m.metadata or {}).get("total_tokens") or 0 for m in msgs
                    )
            except Exception:
                pass
        rows.append(
            {
                "_conv_id": c.id,
                "agent_name": agent_name,
                "agent_slug": agent_slug,
                "mode": meta.get("mode", "—"),
                "status": c.status.value,
                "message_count": msg_count,
                "total_tokens": total_tokens,
                "model": meta.get("model", "—"),
                "triggered_by": meta.get("triggered_by", "—"),
                "created_at": fmt_dt(c.created_at),
            }
        )
    return rows


# ── Data access (SQLiteAIStorage) ─────────────────────────────────────────────


def _get_ai_storage(engine: WorkflowEngine):
    """Retourne le SQLiteAIStorage — préfère l'instance partagée avec AgentRunner."""
    return getattr(engine, "ai_storage", None)


def _fetch_conversations(storage, agent_filter, status, limit) -> list:
    if storage is None:
        return []
    try:
        convs = storage.list_conversations()
        if agent_filter:
            af = agent_filter.lower()
            filtered = []
            for c in convs:
                if c.agent_id:
                    try:
                        ag = storage.get_agent(c.agent_id)
                        if ag and (
                            af in (ag.slug or "").lower() or af in ag.name.lower()
                        ):
                            filtered.append(c)
                    except Exception:
                        pass
                else:
                    filtered.append(c)
            convs = filtered
        if status:
            convs = [c for c in convs if c.status.value == status]
        convs.sort(key=lambda c: c.created_at, reverse=True)
        return convs[:limit]
    except Exception:
        return []


def _info_cell(label: str, value: str) -> None:
    with ui.column().classes("gap-1"):
        ui.label(label).classes("text-caption text-grey-6")
        ui.label(value).classes("text-body2 text-bold")
