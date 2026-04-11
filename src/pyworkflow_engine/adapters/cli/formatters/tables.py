"""
Rich Table formatters pour la sortie CLI.

Chaque fonction prend une ``Console`` et des modèles domaine, et produit
un affichage Rich. Aucune logique métier ici — uniquement du rendu.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from pyworkflow_engine.models.job import Job
    from pyworkflow_engine.models.run import JobRun

from pyworkflow_engine.models.enums import RunStatus

# ---------------------------------------------------------------------------
# Mapping statut → style Rich
# ---------------------------------------------------------------------------

_STATUS_STYLE: dict[RunStatus, str] = {
    RunStatus.SUCCESS: "[bold green]✓ SUCCESS[/]",
    RunStatus.FAILED: "[bold red]✗ FAILED[/]",
    RunStatus.RUNNING: "[bold yellow]⟳ RUNNING[/]",
    RunStatus.PENDING: "[dim]◯ PENDING[/]",
    RunStatus.SUSPENDED: "[bold cyan]⏸ SUSPENDED[/]",
    RunStatus.CANCELLED: "[dim red]✗ CANCELLED[/]",
    RunStatus.WAITING_HUMAN: "[bold magenta]👤 WAITING_HUMAN[/]",
    RunStatus.WAITING_EXTERNAL: "[bold blue]⏳ WAITING_EXTERNAL[/]",
    RunStatus.TIMEOUT: "[bold red]⏱ TIMEOUT[/]",
}


def _status(s: RunStatus) -> str:
    return _STATUS_STYLE.get(s, f"[dim]{s.value}[/]")


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.2f}s"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def render_job_table(console: Console, jobs: list[Job]) -> None:
    """Affiche la liste des jobs sous forme de Rich Table."""
    if not jobs:
        console.print("[dim]Aucun job enregistré.[/dim]")
        return

    table = Table(title="📋  Jobs enregistrés", show_lines=True, expand=False)
    table.add_column("Nom", style="bold cyan", no_wrap=True)
    table.add_column("Steps", justify="right", style="magenta")
    table.add_column("Version", style="dim")
    table.add_column("Executor", style="dim")
    table.add_column("Description")

    for job in jobs:
        table.add_row(
            job.name,
            str(len(job.steps)),
            job.version or "—",
            job.default_executor.value if job.default_executor else "local",
            job.description or "—",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def render_run_result(console: Console, job_run: JobRun) -> None:
    """Affiche le résultat complet d'un run avec le détail des steps."""
    style = _status(job_run.status)

    console.print()
    console.print(
        Panel(
            f"[bold]Run ID[/bold]  {job_run.job_run_id}\n"
            f"[bold]Job    [/bold]  {job_run.job_name}\n"
            f"[bold]Statut [/bold]  {style}",
            title="📊  Résultat",
            expand=False,
        )
    )

    if job_run.step_runs:
        table = Table(show_lines=True, expand=False)
        table.add_column("Step", style="cyan")
        table.add_column("Statut")
        table.add_column("Durée", justify="right", style="dim")
        table.add_column("Erreur")

        for sr in job_run.step_runs:
            table.add_row(
                sr.step_name,
                _status(sr.status),
                _fmt_ms(sr.duration_ms),
                sr.error or "—",
            )
        console.print(table)
    console.print()


def render_run_status(console: Console, job_run: JobRun) -> None:
    """Affiche le statut résumé d'un run."""
    console.print(
        Panel(
            f"[bold]Run ID[/bold]  {job_run.job_run_id}\n"
            f"[bold]Job   [/bold]  {job_run.job_name}\n"
            f"[bold]Statut[/bold]  {_status(job_run.status)}\n"
            f"[bold]Début [/bold]  {_fmt_dt(job_run.start_time)}\n"
            f"[bold]Fin   [/bold]  {_fmt_dt(job_run.end_time)}",
            title="🔍  Statut du run",
            expand=False,
        )
    )


def render_run_history(console: Console, runs: list[JobRun]) -> None:
    """Affiche l'historique des runs sous forme de Rich Table."""
    if not runs:
        console.print("[dim]Aucun run dans l'historique.[/dim]")
        return

    table = Table(title="📜  Historique des runs", show_lines=True, expand=False)
    table.add_column("Run ID", style="bold", no_wrap=True)
    table.add_column("Job", style="cyan")
    table.add_column("Statut")
    table.add_column("Début", style="dim")
    table.add_column("Durée", justify="right", style="dim")

    for run in runs:
        dur_ms = (
            int((run.end_time - run.start_time).total_seconds() * 1000)
            if run.start_time and run.end_time
            else None
        )
        table.add_row(
            run.job_run_id[:12] + "…",
            run.job_name,
            _status(run.status),
            _fmt_dt(run.start_time),
            _fmt_ms(dur_ms),
        )
    console.print(table)
