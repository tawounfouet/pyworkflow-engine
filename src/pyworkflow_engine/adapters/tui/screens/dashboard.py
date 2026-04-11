"""DashboardScreen — vue d'ensemble jobs + runs récents."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from pyworkflow_engine.adapters.tui.widgets.job_table import JobTable
from pyworkflow_engine.adapters.tui.widgets.run_table import RunTable
from pyworkflow_engine.adapters.tui.widgets.status_bar import StatusBar
from pyworkflow_engine.models.enums import SUSPENDED_STATUSES


class DashboardScreen(Screen):
    """Écran principal — jobs enregistrés et runs récents côte à côte."""

    BINDINGS = [
        ("r", "refresh", "Rafraîchir"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("[bold]📊 Dashboard[/bold]", classes="screen-title")
        with Horizontal():
            with Vertical(classes="panel"):
                yield Static("[bold cyan]📋 Jobs enregistrés[/bold cyan]")
                yield JobTable(id="job-table")
            with Vertical(classes="panel"):
                yield Static("[bold cyan]📜 Runs récents[/bold cyan]")
                yield RunTable(id="run-table")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        self._refresh_data()
        self.set_interval(5.0, self._refresh_data)

    def _refresh_data(self) -> None:
        engine = self.app.engine  # type: ignore[attr-defined]
        jobs = engine.list_jobs()
        self.query_one("#job-table", JobTable).load_jobs(jobs)

        try:
            runs = engine.list_job_runs(limit=20)
        except Exception:
            runs = []

        self.query_one("#run-table", RunTable).load_runs(runs)

        suspended = sum(1 for r in runs if r.status in SUSPENDED_STATUSES)
        self.query_one("#status-bar", StatusBar).update_stats(
            total_jobs=len(jobs),
            total_runs=len(runs),
            suspended=suspended,
        )

    def on_data_table_row_selected(self, event: JobTable.RowSelected) -> None:
        from pyworkflow_engine.adapters.tui.screens.job_detail import JobDetailScreen

        if event.data_table.id == "job-table" and event.row_key.value:
            job_name = str(event.row_key.value)
            self.app.push_screen(JobDetailScreen(job_name))  # type: ignore[attr-defined]
        elif event.data_table.id == "run-table" and event.row_key.value:
            from pyworkflow_engine.adapters.tui.screens.run_detail import RunDetailScreen

            run_id = str(event.row_key.value)
            self.app.push_screen(RunDetailScreen(run_id))  # type: ignore[attr-defined]

    def action_refresh(self) -> None:
        self._refresh_data()
