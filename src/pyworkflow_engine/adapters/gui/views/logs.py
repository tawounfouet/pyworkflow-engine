"""Vue Logs — consultation de la table workflow_logs (SQLiteLogHandler)."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


# ── Badge HTML par niveau ─────────────────────────────────────────────────────

_LEVEL_STYLE: dict[str, tuple[str, str]] = {
    "DEBUG":    ("grey-6",        "bug_report"),
    "INFO":     ("blue-6",        "info"),
    "WARNING":  ("warning",       "warning"),
    "ERROR":    ("negative",      "error"),
    "CRITICAL": ("deep-orange-9", "dangerous"),
}


def _level_badge_html(level: str) -> str:
    color, icon = _LEVEL_STYLE.get(level.upper(), ("grey-6", "help"))
    return (
        f'<span style="display:inline-flex;align-items:center;gap:3px;'
        f"padding:1px 6px;border-radius:10px;font-size:11px;font-weight:600;"
        f'background:var(--q-{color},#888);color:#fff;">'
        f'<span class="material-icons" style="font-size:12px">{icon}</span>'
        f"{level}</span>"
    )


# ── Requête SQLite ─────────────────────────────────────────────────────────────


def _query_logs(
    db_path: str,
    level: str | None,
    logger_filter: str | None,
    limit: int,
) -> list[dict]:
    """Requête la table workflow_logs. Retourne [] si absente ou DB inexistante."""
    try:
        conn = sqlite3.connect(db_path)
        conditions: list[str] = []
        params: list[object] = []

        if level:
            conditions.append("level = ?")
            params.append(level.upper())
        if logger_filter:
            conditions.append("logger LIKE ?")
            params.append(f"%{logger_filter}%")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        cursor = conn.execute(
            f"SELECT id, timestamp, level, logger, message, extra "
            f"FROM workflow_logs {where} ORDER BY id DESC LIMIT ?",
            params,
        )
        rows = []
        for id_, ts, lvl, logger, msg, extra_raw in cursor.fetchall():
            extra_str = ""
            if extra_raw:
                try:
                    extra_str = json.dumps(
                        json.loads(extra_raw), ensure_ascii=False, separators=(", ", ": ")
                    )
                except Exception:
                    extra_str = str(extra_raw)
            rows.append(
                {
                    "id": id_,
                    "timestamp": (ts[:19].replace("T", " ") if ts else ""),
                    "level_html": _level_badge_html(lvl),
                    "logger": logger,
                    "message": msg,
                    "extra": extra_str,
                }
            )
        conn.close()
        return rows

    except sqlite3.OperationalError:
        return []  # table workflow_logs absente — pas encore de logging configuré
    except Exception:
        return []


# ── Page ──────────────────────────────────────────────────────────────────────


def build_logs_page(engine: WorkflowEngine, config: GUIConfig) -> None:
    """Construit la page Logs (/logs).

    Affiche le contenu de ``workflow_logs`` (créée par ``SQLiteLogHandler``).
    La page est purement en lecture — rafraîchissement manuel via le bouton.
    """
    page_toolbar("Logs applicatifs", icon="receipt_long", icon_color="info")

    # ── Filtres ────────────────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-4 flex-wrap"):
            level_select = ui.select(
                options=["", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                value="",
                label="Niveau",
            ).classes("min-w-[160px]")
            logger_input = ui.input(
                "Logger",
                placeholder="pyworkflow_engine…",
            ).classes("min-w-[220px]")
            limit_input = ui.number(
                "Limite", value=200, min=10, max=5000, step=50
            ).classes("w-28")
            ui.button(
                "Actualiser", icon="refresh", on_click=lambda: _refresh()
            ).props("color=primary")

    # ── Tableau ────────────────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        count_label = ui.label("").classes("text-caption text-grey-6 q-mb-xs")

        initial_rows = _query_logs(config.db_path, None, None, 200)
        count_label.set_text(f"{len(initial_rows)} entrée(s)")

        grid = (
            ui.aggrid(
                {
                    "columnDefs": [
                        {
                            "headerName": "ID",
                            "field": "id",
                            "width": 75,
                            "type": "numericColumn",
                        },
                        {
                            "headerName": "Timestamp",
                            "field": "timestamp",
                            "width": 165,
                        },
                        {
                            "headerName": "Niveau",
                            "field": "level_html",
                            "width": 120,
                        },
                        {
                            "headerName": "Logger",
                            "field": "logger",
                            "flex": 1,
                        },
                        {
                            "headerName": "Message",
                            "field": "message",
                            "flex": 2,
                        },
                        {
                            "headerName": "Extra",
                            "field": "extra",
                            "flex": 1,
                        },
                    ],
                    "rowData": initial_rows,
                    "defaultColDef": {"resizable": True, "filter": True},
                },
                html_columns=[2],
                auto_size_columns=False,
            )
            .classes("w-full")
            .style("height: 600px")
        )

        if not initial_rows:
            ui.label(
                "Aucun log trouvé — la table workflow_logs n'existe pas encore. "
                "Lancez un job avec SQLiteLogHandler configuré pour peupler cette vue."
            ).classes("text-caption text-grey-5 q-mt-xs")

    # ── Refresh ────────────────────────────────────────────────────────────
    def _refresh() -> None:
        rows = _query_logs(
            config.db_path,
            level_select.value or None,
            logger_input.value.strip() or None,
            int(limit_input.value or 200),
        )
        count_label.set_text(f"{len(rows)} entrée(s)")
        grid.run_grid_method("setGridOption", "rowData", rows)
