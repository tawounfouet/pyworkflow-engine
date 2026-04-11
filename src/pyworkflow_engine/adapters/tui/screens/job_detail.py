"""JobListScreen et JobDetailScreen — liste et inspection des jobs."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from pyworkflow_engine.adapters.tui.widgets.job_table import JobTable
from pyworkflow_engine.adapters.tui.widgets.job_tree import JobTree


class JobListScreen(Screen):
    """Écran de liste des jobs — navigation vers le détail DAG."""

    BINDINGS = [
        ("escape", "pop_screen", "Retour"),
        ("r", "refresh", "Rafraîchir"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("[bold]📋 Jobs enregistrés[/bold]", classes="screen-title")
        yield JobTable(id="job-table")

    def on_mount(self) -> None:
        self._load_jobs()

    def _load_jobs(self) -> None:
        engine = self.app.engine  # type: ignore[attr-defined]
        self.query_one("#job-table", JobTable).load_jobs(engine.list_jobs())

    def on_data_table_row_selected(self, event: JobTable.RowSelected) -> None:
        if event.row_key.value:
            job_name = str(event.row_key.value)
            self.app.push_screen(JobDetailScreen(job_name))  # type: ignore[attr-defined]

    def action_refresh(self) -> None:
        self._load_jobs()


class JobDetailScreen(Screen):
    """Écran de détail d'un job — visualisation DAG interactif + métadonnées."""

    BINDINGS = [
        ("escape", "pop_screen", "Retour"),
        ("r", "run_job", "Lancer"),
    ]

    def __init__(self, job_name: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.job_name = job_name

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]📋 Job [cyan]{self.job_name}[/cyan][/bold]",
            classes="screen-title",
        )
        with Horizontal():
            with Vertical(classes="panel"):
                yield Static("[bold]DAG — Steps[/bold]")
                yield JobTree(label=self.job_name, id="job-tree")
            with Vertical(classes="panel"):
                yield Static("[bold]Métadonnées[/bold]")
                yield Static(id="job-meta")

    def on_mount(self) -> None:
        engine = self.app.engine  # type: ignore[attr-defined]
        job = engine.get_job(self.job_name)
        if job is None:
            self.notify(f"Job {self.job_name!r} introuvable", severity="error")
            self.pop_screen()
            return

        self.query_one("#job-tree", JobTree).load_job(job)

        meta_lines = [
            f"[bold]Nom[/bold] : {job.name}",
            f"[bold]Version[/bold] : {getattr(job, 'version', '—') or '—'}",
            f"[bold]Description[/bold] : {job.description or '—'}",
            f"[bold]Steps[/bold] : {len(job.steps)}",
            f"[bold]Executor[/bold] : {job.default_executor.value}",
            f"[bold]Priorité[/bold] : {job.priority.name}",
            f"[bold]Activé[/bold] : {'✓' if getattr(job, 'enabled', True) else '✗'}",
        ]
        self.query_one("#job-meta", Static).update("\n".join(meta_lines))

    def action_run_job(self) -> None:
        engine = self.app.engine  # type: ignore[attr-defined]
        try:
            job_run = engine.run(self.job_name)
            self.notify(
                f"Run démarré : {job_run.job_run_id[:12]}…",
                severity="information",
            )
        except Exception as exc:
            self.notify(f"Échec du lancement : {exc}", severity="error")
