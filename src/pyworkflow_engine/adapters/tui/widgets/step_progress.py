"""StepProgress widget — table des steps d'un run avec live update."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import DataTable

if TYPE_CHECKING:
    from pyworkflow_engine.models.run import StepRun

from pyworkflow_engine.adapters.tui.widgets.run_table import STATUS_MARKUP


class StepProgressTable(DataTable):
    """Table des steps avec mise à jour en temps réel."""

    def on_mount(self) -> None:
        self.add_columns("Step", "Statut", "Durée", "Erreur")
        self.cursor_type = "row"

    def update_steps(self, step_runs: list[StepRun]) -> None:
        self.clear()
        for sr in step_runs:
            label, color = STATUS_MARKUP.get(
                sr.status, (str(sr.status.value), "white")
            )
            duration = (
                f"{sr.duration_ms}ms"
                if sr.duration_ms and sr.duration_ms < 1000
                else f"{sr.duration_ms / 1000:.2f}s"
                if sr.duration_ms
                else "—"
            )
            self.add_row(
                sr.step_name,
                Text(label, style=color),
                duration,
                sr.error or "—",
            )
