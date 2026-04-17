# filepath: src/pyworkflow_engine/adapters/gui/views/scheduler.py
"""Vue Scheduler — monitoring et contrôle des triggers schedulés.

Affiche :
  - Bannière état runner (PID, actif/arrêté) + actions globales
  - KPI cards : triggers actifs / désactivés / total
  - Tableau des triggers : cron, prochain fire, état, bouton disable/enable
  - Log live (50 dernières lignes de scheduler_runner.log)

Auto-refresh toutes les 30 secondes via ui.timer.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


# ── Chemins (miroir de scheduler_runner.py) ───────────────────────────────────

_ROOT = Path(__file__).resolve().parents[5]
_LOGS_DIR = _ROOT / "logs"
_PID_FILE = _LOGS_DIR / "scheduler_runner.pid"
_EXCLUDED_FILE = _LOGS_DIR / "scheduler_runner.excluded"
_CMD_FILE = _LOGS_DIR / "scheduler_runner.cmd"
_LOG_FILE = _LOGS_DIR / "scheduler_runner.log"
_MANIFEST = _ROOT / "jobs" / "manifest.yaml"


# ── Helpers données ───────────────────────────────────────────────────────────


def _runner_pid() -> int | None:
    """Retourne le PID du runner daemon si actif, sinon None."""
    try:
        pid = int(_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def _excluded_jobs() -> set[str]:
    try:
        return {l.strip() for l in _EXCLUDED_FILE.read_text().splitlines() if l.strip()}
    except FileNotFoundError:
        return set()


def _load_manifest() -> list[dict]:
    try:
        import yaml  # noqa: PLC0415

        data = yaml.safe_load(_MANIFEST.read_text()) or {}
        return [j for j in data.get("jobs", []) if j.get("schedule")]
    except Exception:
        return []


def _next_fire(cron: str) -> datetime | None:
    try:
        from pyworkflow_engine.adapters.triggers.schedule import (
            CronExpression,
        )  # noqa: PLC0415

        expr = CronExpression(cron)
        dt = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(60 * 24 * 8):  # max 8 jours
            if expr.matches(dt):
                return dt
            dt += timedelta(minutes=1)
    except Exception:
        return None
    return None


def _human_delta(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    total = int((dt - datetime.now(UTC)).total_seconds())
    if total < 0:
        return "passé"
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}min"
    h, m = divmod(total // 60, 60)
    return f"{h}h {m}min" if m else f"{h}h"


def _tail_log(n: int = 50) -> list[str]:
    try:
        lines = _LOG_FILE.read_text(errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []


def _send_command(verb: str, job_name: str = "") -> bool:
    pid = _runner_pid()
    if not pid:
        return False
    try:
        _CMD_FILE.write_text(f"{verb} {job_name}".strip())
        os.kill(pid, signal.SIGUSR1)
        return True
    except Exception:
        return False


# ── Vue principale ────────────────────────────────────────────────────────────


def build_scheduler_page(engine: WorkflowEngine, config: GUIConfig) -> None:
    """Page /scheduler — monitoring et contrôle des triggers."""
    page_toolbar("Scheduler", icon="schedule", icon_color="teal")

    scheduled_jobs = _load_manifest()

    # ── Bannière runner ───────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-3 flex-wrap"):
            runner_icon = ui.icon("circle").classes("text-h6")
            runner_label = ui.label().classes("text-subtitle1 text-bold")
            runner_sub = ui.label().classes("text-caption text-grey-6")
            ui.space()
            btn_start = ui.button(
                "Démarrer",
                icon="play_arrow",
                on_click=lambda: _action_start(),
            ).props("flat color=positive size=sm")
            btn_stop = ui.button(
                "Arrêter",
                icon="stop",
                on_click=lambda: _action_stop(),
            ).props("flat color=negative size=sm")
            btn_reload = ui.button(
                "Reload manifest",
                icon="refresh",
                on_click=lambda: _action_reload(),
            ).props("flat color=primary size=sm")

    # ── KPI cards ─────────────────────────────────────────────────────────
    with ui.row().classes("w-full gap-4 q-mb-md"):
        kpi_total = _kpi_card("Total schedulé", "event", "primary")
        kpi_active = _kpi_card("Actifs", "play_circle", "positive")
        kpi_disabled = _kpi_card("Désactivés", "pause_circle", "orange")
        kpi_next_label = _kpi_card("Prochain fire", "alarm", "teal")

    # ── Tableau triggers ──────────────────────────────────────────────────
    with ui.card().classes("w-full q-mb-md"):
        with ui.row().classes("items-center gap-2 q-mb-sm"):
            ui.icon("table_rows").classes("text-teal")
            ui.label("Triggers").classes("text-subtitle1 text-bold")
            ui.space()
            ui.label("auto-refresh 30s").classes("text-caption text-grey-6")

        # En-tête fixe
        with (
            ui.row()
            .classes(
                "w-full px-3 py-1 rounded text-caption text-grey-5 text-bold gap-2"
            )
            .style("background: rgba(255,255,255,0.04)")
        ):
            ui.label("JOB").classes("flex-1")
            ui.label("CRON").style("width:130px")
            ui.label("PROCHAIN FIRE").style("width:160px")
            ui.label("ÉTAT").style("width:110px")
            ui.label("ACTIONS").style("width:130px; text-align:right")

        triggers_container = ui.column().classes("w-full gap-0")

    # ── Log live ──────────────────────────────────────────────────────────
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-2 q-mb-sm"):
            ui.icon("terminal").classes("text-grey-5")
            ui.label("scheduler_runner.log").classes("text-subtitle1 text-bold")
            ui.space()
            ui.button(
                "Rafraîchir",
                icon="refresh",
                on_click=lambda: _refresh_log(),
            ).props("flat dense size=xs color=grey")
        log_container = ui.column().classes("w-full")

    # ── Logique de refresh ────────────────────────────────────────────────

    def _refresh_banner():
        pid = _runner_pid()
        if pid:
            runner_icon.classes("text-positive", remove="text-negative text-grey")
            runner_label.set_text(f"Runner actif — PID {pid}")
            runner_label.classes("text-positive", remove="text-negative text-grey-6")
            runner_sub.set_text(str(_LOG_FILE))
            btn_start.set_visibility(False)
            btn_stop.set_visibility(True)
            btn_reload.set_visibility(True)
        else:
            runner_icon.classes("text-negative", remove="text-positive text-grey")
            runner_label.set_text("Runner arrêté")
            runner_label.classes("text-negative", remove="text-positive text-grey-6")
            runner_sub.set_text("Aucun processus actif")
            btn_start.set_visibility(True)
            btn_stop.set_visibility(False)
            btn_reload.set_visibility(False)

    def _refresh_kpis(excluded: set[str], pid: int | None):
        total = len(scheduled_jobs)
        disabled = len(excluded)
        active = total - disabled if pid else 0

        kpi_total.set_text(str(total))
        kpi_active.set_text(str(active))
        kpi_disabled.set_text(str(disabled))

        # Prochain fire global (premier parmi tous les actifs)
        nxt_global: datetime | None = None
        nxt_name = ""
        for job in scheduled_jobs:
            if job["name"] in excluded:
                continue
            nxt = _next_fire(job["schedule"])
            if nxt and (nxt_global is None or nxt < nxt_global):
                nxt_global = nxt
                nxt_name = job["name"]
        if nxt_global and pid:
            kpi_next_label.set_text(
                nxt_global.strftime("%d/%m %H:%M") + f"\n{nxt_name[:22]}"
            )
        else:
            kpi_next_label.set_text("—")

    def _refresh_triggers(excluded: set[str], pid: int | None):
        triggers_container.clear()
        with triggers_container:
            for job in scheduled_jobs:
                name: str = job["name"]
                cron: str = job["schedule"]
                is_disabled = name in excluded
                nxt = _next_fire(cron)
                nxt_str = nxt.strftime("%d/%m %H:%M UTC") if nxt else "—"
                delta = _human_delta(nxt)

                # Couleur de ligne alternée + highlight si désactivé
                row_style = "opacity:0.5" if is_disabled else ""

                with (
                    ui.row()
                    .classes(
                        "w-full px-3 py-2 items-center gap-2 rounded "
                        "hover:bg-grey-9 border-b border-grey-9"
                    )
                    .style(row_style)
                ):
                    # Nom
                    with ui.row().classes("flex-1 items-center gap-2"):
                        ui.icon(
                            "pause_circle" if is_disabled else "play_circle"
                        ).classes(
                            "text-orange text-sm"
                            if is_disabled
                            else "text-positive text-sm"
                        )
                        ui.label(name).classes("font-mono text-sm")

                    # Cron
                    ui.label(cron).classes("text-grey-5 font-mono text-xs").style(
                        "width:130px"
                    )

                    # Prochain fire
                    with ui.column().classes("gap-0").style("width:160px"):
                        ui.label(nxt_str if pid and not is_disabled else "—").classes(
                            "text-xs"
                        )
                        if pid and not is_disabled and delta != "—":
                            ui.label(f"dans {delta}").classes(
                                "text-caption text-grey-5"
                            )

                    # Badge état
                    with ui.element("div").style("width:110px"):
                        if not pid:
                            ui.badge("runner off", color="grey").props("outline")
                        elif is_disabled:
                            ui.badge("désactivé", color="orange").props("outline")
                        else:
                            ui.badge("actif", color="positive").props("outline")

                    # Actions
                    with ui.row().classes("justify-end gap-1").style("width:130px"):
                        if pid and not is_disabled:
                            ui.button(
                                "Désactiver",
                                on_click=lambda n=name: _action_disable(n),
                            ).props("flat dense size=xs color=orange unelevated")
                        elif pid and is_disabled:
                            ui.button(
                                "Activer",
                                on_click=lambda n=name: _action_enable(n),
                            ).props("flat dense size=xs color=positive unelevated")

    def _refresh_log():
        log_container.clear()
        lines = _tail_log(50)
        with log_container:
            if not lines:
                ui.label("Aucun log disponible.").classes("text-caption text-grey-6")
                return
            with (
                ui.element("div")
                .classes("w-full rounded font-mono text-xs q-pa-sm overflow-auto")
                .style(
                    "background:#1a1a2e; color:#c9d1d9; max-height:340px; "
                    "white-space:pre; overflow-x:auto"
                )
            ):
                for line in lines:
                    if "ERROR" in line or "❌" in line:
                        color = "#ef5350"
                    elif "SUCCESS" in line or "✅" in line:
                        color = "#66bb6a"
                    elif "firing" in line or "🚀" in line:
                        color = "#42a5f5"
                    elif "WARNING" in line or "⚠️" in line:
                        color = "#ffa726"
                    elif "⏸" in line or "désactivé" in line:
                        color = "#ffb74d"
                    elif "▶️" in line or "réactivé" in line:
                        color = "#81c784"
                    else:
                        color = "#c9d1d9"
                    ui.html(f'<div style="color:{color}; line-height:1.5">{line}</div>')

    def _refresh_all():
        pid = _runner_pid()
        excluded = _excluded_jobs()
        _refresh_banner()
        _refresh_kpis(excluded, pid)
        _refresh_triggers(excluded, pid)
        _refresh_log()

    # ── Actions ───────────────────────────────────────────────────────────

    def _action_start():
        try:
            subprocess.Popen(
                [sys.executable, "-m", "jobs.ops.scheduler_runner", "--detach"],
                cwd=str(_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            import time  # noqa: PLC0415

            time.sleep(1.5)
            ui.notify("🚀 Runner démarré", color="positive", position="top")
        except Exception as exc:
            ui.notify(f"Erreur démarrage : {exc}", color="negative", position="top")
        _refresh_all()

    def _action_stop():
        pid = _runner_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                _PID_FILE.unlink(missing_ok=True)
                ui.notify(
                    f"⏹ Runner arrêté (PID {pid})", color="warning", position="top"
                )
            except Exception as exc:
                ui.notify(f"Erreur : {exc}", color="negative", position="top")
        _refresh_all()

    def _action_reload():
        ok = _send_command("reload")
        ui.notify(
            "🔄 Manifest rechargé" if ok else "❌ Runner non joignable",
            color="primary" if ok else "negative",
            position="top",
        )
        _refresh_all()

    def _action_disable(name: str):
        ok = _send_command("disable", name)
        ui.notify(
            f"⏸ {name} désactivé" if ok else "❌ Runner non joignable",
            color="orange" if ok else "negative",
            position="top",
        )
        _refresh_all()

    def _action_enable(name: str):
        ok = _send_command("enable", name)
        ui.notify(
            f"▶ {name} réactivé" if ok else "❌ Runner non joignable",
            color="positive" if ok else "negative",
            position="top",
        )
        _refresh_all()

    # Premier affichage + timer auto
    _refresh_all()
    ui.timer(30.0, _refresh_all)


# ── Helper KPI card ───────────────────────────────────────────────────────────


def _kpi_card(title: str, icon: str, color: str) -> ui.label:
    """Crée une carte KPI et retourne le label de valeur (pour mise à jour)."""
    with ui.card().classes("flex-1 min-w-[140px]"):
        with ui.row().classes("items-center gap-2 q-mb-xs"):
            ui.icon(icon).classes(f"text-{color}")
            ui.label(title).classes("text-caption text-grey-5")
        value_label = ui.label("—").classes("text-h5 text-bold")
    return value_label
