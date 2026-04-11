"""status_badge — badge coloré NiceGUI pour afficher un RunStatus."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.styles.theme import (
    STATUS_COLOR,
    STATUS_ICON,
    STATUS_LABEL,
)

if TYPE_CHECKING:
    from pyworkflow_engine.models.enums import RunStatus


def status_badge(status: RunStatus) -> ui.badge:
    """Crée un badge NiceGUI coloré pour un RunStatus.

    Usage::

        with ui.row():
            status_badge(run.status)

    Returns:
        L'élément ``ui.badge`` créé.
    """
    color = STATUS_COLOR.get(status, "grey")
    icon = STATUS_ICON.get(status, "help")
    label = STATUS_LABEL.get(status, str(status.value))

    with ui.row().classes("items-center gap-1"):
        ui.icon(icon).classes(f"text-{color} text-sm")
        badge = ui.badge(label, color=color).props("rounded")
    return badge
