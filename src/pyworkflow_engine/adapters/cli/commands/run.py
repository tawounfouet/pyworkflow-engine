"""
Commandes de gestion des runs : start, status, history, resume, cancel.
"""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="run",
    help="Lancer et surveiller des workflow runs (start, status, history, resume, cancel).",
    no_args_is_help=True,
)
console = Console()


@app.command("start")
@error_handler
def run_start(
    ctx: typer.Context,
    job_name: str = typer.Argument(help="Nom du job à exécuter"),
    run_id: Optional[str] = typer.Option(
        None,
        "--run-id",
        "-r",
        help="ID d'exécution personnalisé (UUID généré si absent).",
    ),
    context_json: Optional[str] = typer.Option(
        None,
        "--context",
        "-c",
        help='Contexte initial JSON en ligne, ex: \'{"key": "value"}\'.',
    ),
    persist: bool = typer.Option(
        False,
        "--persist",
        "-p",
        help="Utiliser run_with_storage() pour checkpoint automatique.",
    ),
) -> None:
    """Lance un run pour le job donné et affiche le résultat."""
    engine = load_engine(ctx.obj["app_path"])

    # Désérialisation du contexte initial
    initial_context: dict | None = None
    if context_json:
        try:
            initial_context = json.loads(context_json)
        except json.JSONDecodeError as exc:
            from rich.console import Console as _C

            _C(stderr=True).print(
                f"[bold red]✗[/bold red] --context n'est pas un JSON valide : {exc}"
            )
            raise typer.Exit(4) from exc

    if persist:
        job_run = engine.run_with_storage(
            job_name,
            initial_context=initial_context,
            run_id=run_id,
        )
    else:
        job = engine.get_job(job_name)
        if job is None:
            from pyworkflow_engine.ports.storage import JobNotFoundError

            raise JobNotFoundError(f"Job '{job_name}' introuvable dans le backend.")
        job_run = engine.run(job, initial_context=initial_context, run_id=run_id)

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import run_to_json

        typer.echo(run_to_json(job_run))
    else:
        from pyworkflow_engine.adapters.cli.formatters.tables import render_run_result

        render_run_result(console, job_run)

    # Exit code reflète le statut du run
    from pyworkflow_engine.models.enums import RunStatus

    if job_run.status == RunStatus.FAILED:
        raise typer.Exit(2)
    if job_run.status not in (RunStatus.SUCCESS, RunStatus.SUSPENDED):
        raise typer.Exit(1)


@app.command("status")
@error_handler
def run_status(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="ID du run à interroger"),
) -> None:
    """Affiche le statut courant d'un run (depuis le backend de persistence)."""
    engine = load_engine(ctx.obj["app_path"])
    job_run = engine.get_job_run(run_id)

    if job_run is None:
        from rich.console import Console as _C

        _C(stderr=True).print(
            f"[bold red]✗[/bold red] Run [cyan]{run_id}[/cyan] introuvable."
        )
        raise typer.Exit(1)

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import run_to_json

        typer.echo(run_to_json(job_run))
    else:
        from pyworkflow_engine.adapters.cli.formatters.tables import render_run_status

        render_run_status(console, job_run)


@app.command("history")
@error_handler
def run_history(
    ctx: typer.Context,
    job_name: Optional[str] = typer.Option(
        None,
        "--job",
        "-j",
        help="Filtrer par nom de job.",
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help="Filtrer par statut (SUCCESS, FAILED, RUNNING, …).",
    ),
    limit: Optional[int] = typer.Option(
        20,
        "--limit",
        "-n",
        help="Nombre maximum de runs à afficher.",
    ),
) -> None:
    """Liste l'historique des runs (depuis le backend de persistence)."""
    engine = load_engine(ctx.obj["app_path"])
    runs = engine.list_job_runs(job_name=job_name, status=status, limit=limit)

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import runs_to_json

        typer.echo(runs_to_json(runs))
    else:
        from pyworkflow_engine.adapters.cli.formatters.tables import render_run_history

        render_run_history(console, runs)


@app.command("resume")
@error_handler
def run_resume(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="ID du run suspendu à reprendre"),
    outputs_json: Optional[str] = typer.Option(
        None,
        "--outputs",
        "-o",
        help="Outputs des steps humains, JSON en ligne, ex: '{\"approve\": true}'.",
    ),
) -> None:
    """Reprend un workflow suspendu (approbation humaine, etc.)."""
    engine = load_engine(ctx.obj["app_path"])

    step_outputs: dict | None = None
    if outputs_json:
        try:
            step_outputs = json.loads(outputs_json)
        except json.JSONDecodeError as exc:
            from rich.console import Console as _C

            _C(stderr=True).print(
                f"[bold red]✗[/bold red] --outputs n'est pas un JSON valide : {exc}"
            )
            raise typer.Exit(4) from exc

    job_run = engine.resume(run_id, step_outputs=step_outputs)

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import run_to_json

        typer.echo(run_to_json(job_run))
    else:
        from pyworkflow_engine.adapters.cli.formatters.tables import render_run_result

        render_run_result(console, job_run)

    from pyworkflow_engine.models.enums import RunStatus

    if job_run.status == RunStatus.FAILED:
        raise typer.Exit(2)


@app.command("cancel")
@error_handler
def run_cancel(
    ctx: typer.Context,
    run_id: str = typer.Argument(help="ID du run suspendu à annuler"),
) -> None:
    """Annule un run suspendu."""
    engine = load_engine(ctx.obj["app_path"])
    cancelled = engine.cancel(run_id)

    if cancelled:
        console.print(f"[bold green]✓[/bold green]  Run [cyan]{run_id}[/cyan] annulé.")
    else:
        console.print(
            f"[yellow]⚠[/yellow]  Run [cyan]{run_id}[/cyan] introuvable "
            f"ou déjà terminé — aucune action effectuée."
        )
        raise typer.Exit(1)
