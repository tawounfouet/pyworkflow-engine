"""RunHistoryScreen — historique filtrable des runs."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Select, Static

from pyworkflow_engine.adapters.tui.widgets.run_table import RunTable
from pyworkflow_engine.models.enums import RunStatus


class RunHistoryScreen(Screen):
    """Écran d'historique des runs — filtrable par job et par statut."""

    BINDINGS = [
        ("escape", "pop_screen", "Retour"),
        ("r", "refresh", "Rafraîchir"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("[bold]📜 Historique des runs[/bold]", classes="screen-title")
        with Horizontal(classes="panel"):
            with Vertical():
                yield Static("[bold]Filtres[/bold]")
                yield Input(placeholder="Nom du job…", id="filter-job")
                yield Select(
                    options=[("Tous les statuts", "")] + [
                        (s.value, s.value) for s in RunStatus
                    ],
                    id="filter-status",
                    value="",
                )
        yield RunTable(id="run-table")

    def on_mount(self) -> None:
        self._load_runs()

    def _load_runs(self) -> None:
        job_filter = self.query_one("#filter-job", Input).value.strip() or None
        status_select = self.query_one("#filter-status", Select)
        status_filter = status_select.value if status_select.value else None

        try:
            runs = self.app.engine.list_job_runs(  # type: ignore[attr-defined]
                job_name=job_filter,
                status=status_filter,
                limit=100,
            )
        except Exception:
            runs = []

        self.query_one("#run-table", RunTable).load_runs(runs)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._load_runs()

    def on_select_changed(self, event: Select.Changed) -> None:
        self._load_runs()

    def on_data_table_row_selected(self, event: RunTable.RowSelected) -> None:
        if event.row_key.value:
            from pyworkflow_engine.adapters.tui.screens.run_detail import RunDetailScreen

            run_id = str(event.row_key.value)
            self.app.push_screen(RunDetailScreen(run_id))  # type: ignore[attr-defined]

    def action_refresh(self) -> None:
        self._load_runs()
