"""RunTable widget — DataTable des runs avec statuts colorés."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import DataTable

if TYPE_CHECKING:
    from pyworkflow_engine.models import JobRun

from pyworkflow_engine.models.enums import RunStatus

# Mapping statut → (label, style) partageable avec d'autres widgets TUI
STATUS_MARKUP: dict[RunStatus, tuple[str, str]] = {
    RunStatus.SUCCESS:          ("✓ SUCCESS",        "green"),
    RunStatus.FAILED:           ("✗ FAILED",         "red"),
    RunStatus.RUNNING:          ("⟳ RUNNING",         "yellow"),
    RunStatus.PENDING:          ("◯ PENDING",         "dim"),
    RunStatus.SUSPENDED:        ("⏸ SUSPENDED",       "cyan"),
    RunStatus.CANCELLED:        ("✗ CANCELLED",       "red"),
    RunStatus.WAITING_HUMAN:    ("👤 WAITING_HUMAN",  "magenta"),
    RunStatus.WAITING_EXTERNAL: ("⏳ WAITING_EXT",    "blue"),
    RunStatus.TIMEOUT:          ("⏱ TIMEOUT",         "dark_orange"),
}


class RunTable(DataTable):
    """Table interactive des workflow runs.

    L'appui sur ``Enter`` émet un événement ``RowSelected`` capté
    par le screen parent pour naviguer vers le RunDetailScreen.
    """

    def on_mount(self) -> None:
        self.add_columns("Run ID", "Job", "Statut", "Début", "Durée")
        self.cursor_type = "row"

    def load_runs(self, runs: list[JobRun]) -> None:
        self.clear()
        for run in runs:
            label, color = STATUS_MARKUP.get(
                run.status, (str(run.status.value), "white")
            )
            started = (
                run.start_time.strftime("%Y-%m-%d %H:%M:%S")
                if run.start_time
                else "—"
            )
            dur_ms = (
                int((run.end_time - run.start_time).total_seconds() * 1000)
                if run.start_time and run.end_time
                else None
            )
            duration = (
                f"{dur_ms}ms"
                if dur_ms and dur_ms < 1000
                else (f"{dur_ms / 1000:.2f}s" if dur_ms else "—")
            )
            self.add_row(
                run.job_run_id[:12] + "…",
                run.job_name,
                Text(label, style=color),
                started,
                duration,
                key=run.job_run_id,
            )
