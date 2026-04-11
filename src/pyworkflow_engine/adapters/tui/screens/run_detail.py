"""RunDetailScreen — suivi d'un run en temps réel."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from pyworkflow_engine.adapters.tui.widgets.log_panel import LogPanel
from pyworkflow_engine.adapters.tui.widgets.step_progress import StepProgressTable


class RunDetailScreen(Screen):
    """Écran de détail d'un run — steps + logs, rafraîchissement live."""

    BINDINGS = [
        ("escape", "pop_screen", "Retour"),
        ("c", "cancel_run", "Annuler"),
        ("shift+r", "resume_run", "Reprendre"),
        ("r", "refresh", "Rafraîchir"),
    ]

    def __init__(self, run_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.run_id = run_id

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]🔍 Run [cyan]{self.run_id[:12]}…[/cyan][/bold]",
            classes="screen-title",
        )
        with Horizontal():
            with Vertical(classes="panel"):
                yield Static("[bold]Steps[/bold]")
                yield StepProgressTable(id="step-table")
            with Vertical(classes="panel"):
                yield Static("[bold]Logs[/bold]")
                yield LogPanel(id="log-panel")

    def on_mount(self) -> None:
        self._refresh_run()
        self.set_interval(1.0, self._refresh_run)

    def _refresh_run(self) -> None:
        job_run = self.app.engine.get_job_run(self.run_id)  # type: ignore[attr-defined]
        if job_run is None:
            self.notify("Run introuvable", severity="error")
            return

        self.query_one("#step-table", StepProgressTable).update_steps(job_run.step_runs)

        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.clear()
        for sr in job_run.step_runs:
            for log in sr.logs:
                style = {"ERROR": "red", "WARNING": "yellow", "INFO": "green"}.get(
                    log.level, "dim"
                )
                log_panel.append_log(
                    f"[{log.timestamp.strftime('%H:%M:%S')}] [{sr.step_name}] {log.message}",
                    style=style,
                )

    def action_cancel_run(self) -> None:
        cancelled = self.app.engine.cancel(self.run_id)  # type: ignore[attr-defined]
        if cancelled:
            self.notify(f"Run {self.run_id[:12]}… annulé", severity="warning")
        else:
            self.notify("Impossible d'annuler ce run", severity="error")
        self._refresh_run()

    def action_resume_run(self) -> None:
        try:
            self.app.engine.resume(self.run_id)  # type: ignore[attr-defined]
            self.notify(f"Run {self.run_id[:12]}… repris", severity="information")
        except Exception as exc:
            self.notify(f"Échec reprise : {exc}", severity="error")
        self._refresh_run()

    def action_refresh(self) -> None:
        self._refresh_run()
