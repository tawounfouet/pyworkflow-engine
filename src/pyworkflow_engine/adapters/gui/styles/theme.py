"""Helpers partagés : styles, couleurs, formatage."""

from __future__ import annotations

from datetime import datetime

from pyworkflow_engine.models.enums import RunStatus

# ---------------------------------------------------------------------------
# Mapping statut → couleur Quasar / Tailwind
# ---------------------------------------------------------------------------

STATUS_COLOR: dict[RunStatus, str] = {
    RunStatus.SUCCESS: "positive",
    RunStatus.FAILED: "negative",
    RunStatus.RUNNING: "warning",
    RunStatus.PENDING: "grey",
    RunStatus.SUSPENDED: "info",
    RunStatus.CANCELLED: "grey-7",
    RunStatus.WAITING_HUMAN: "purple",
    RunStatus.WAITING_EXTERNAL: "blue",
    RunStatus.TIMEOUT: "deep-orange",
}

STATUS_ICON: dict[RunStatus, str] = {
    RunStatus.SUCCESS: "check_circle",
    RunStatus.FAILED: "cancel",
    RunStatus.RUNNING: "sync",
    RunStatus.PENDING: "radio_button_unchecked",
    RunStatus.SUSPENDED: "pause_circle",
    RunStatus.CANCELLED: "block",
    RunStatus.WAITING_HUMAN: "person",
    RunStatus.WAITING_EXTERNAL: "hourglass_empty",
    RunStatus.TIMEOUT: "timer_off",
}

STATUS_LABEL: dict[RunStatus, str] = {
    RunStatus.SUCCESS: "SUCCESS",
    RunStatus.FAILED: "FAILED",
    RunStatus.RUNNING: "RUNNING",
    RunStatus.PENDING: "PENDING",
    RunStatus.SUSPENDED: "SUSPENDED",
    RunStatus.CANCELLED: "CANCELLED",
    RunStatus.WAITING_HUMAN: "WAITING HUMAN",
    RunStatus.WAITING_EXTERNAL: "WAITING EXT.",
    RunStatus.TIMEOUT: "TIMEOUT",
}


def fmt_dt(dt: datetime | None) -> str:
    """Formate une datetime pour l'affichage."""
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fmt_ms(ms: int | None) -> str:
    """Formate une durée en millisecondes."""
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms} ms"
    if ms < 60_000:
        return f"{ms / 1000:.2f} s"
    return f"{ms / 60_000:.1f} min"


def status_badge_html(status: RunStatus) -> str:
    """Retourne un badge HTML coloré pour l'AG Grid (html_columns)."""
    color = STATUS_COLOR.get(status, "grey")
    icon = STATUS_ICON.get(status, "help")
    label = STATUS_LABEL.get(status, status.value)
    # Quasar chip inline HTML — rendu nativement par AG Grid html_columns
    return (
        f'<span style="display:inline-flex;align-items:center;gap:3px;'
        f"padding:1px 6px;border-radius:10px;font-size:11px;font-weight:600;"
        f'background:var(--q-{color}, #888);color:#fff;">'
        f'<span class="material-icons" style="font-size:12px">{icon}</span>'
        f"{label}</span>"
    )
