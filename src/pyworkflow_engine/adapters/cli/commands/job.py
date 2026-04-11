"""
Commandes de gestion des jobs : list, inspect, validate, plan.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="job",
    help="Gérer les workflow jobs (list, inspect, validate, plan).",
    no_args_is_help=True,
)
console = Console()


@app.command("list")
@error_handler
def list_jobs(ctx: typer.Context) -> None:
    """Liste tous les jobs enregistrés dans le backend de persistence."""
    engine = load_engine(ctx.obj["app_path"])
    jobs = engine.list_jobs()

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import jobs_to_json

        typer.echo(jobs_to_json(jobs))
    else:
        from pyworkflow_engine.adapters.cli.formatters.tables import render_job_table

        render_job_table(console, jobs)


@app.command("inspect")
@error_handler
def inspect_job(
    ctx: typer.Context,
    name: str = typer.Argument(help="Nom du job à inspecter"),
) -> None:
    """Affiche la structure complète d'un job (steps, DAG, metadata)."""
    engine = load_engine(ctx.obj["app_path"])
    job = engine.get_job(name)

    if job is None:
        from pyworkflow_engine.ports.storage import JobNotFoundError

        raise JobNotFoundError(f"Job '{name}' introuvable dans le backend.")

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import jobs_to_json

        typer.echo(jobs_to_json([job]))
    else:
        from pyworkflow_engine.adapters.cli.formatters.trees import render_job_tree

        render_job_tree(console, job)


@app.command("validate")
@error_handler
def validate_job(
    ctx: typer.Context,
    name: str = typer.Argument(help="Nom du job à valider"),
) -> None:
    """Valide un job sans l'exécuter. Affiche les avertissements."""
    engine = load_engine(ctx.obj["app_path"])
    job = engine.get_job(name)

    if job is None:
        from pyworkflow_engine.ports.storage import JobNotFoundError

        raise JobNotFoundError(f"Job '{name}' introuvable dans le backend.")

    warnings = engine.validate_job(job)
    if warnings:
        for w in warnings:
            console.print(f"[yellow]⚠[/yellow]  {w}")
        raise typer.Exit(1)
    else:
        console.print("[bold green]✓[/bold green]  Job valide — aucun avertissement.")


@app.command("plan")
@error_handler
def execution_plan(
    ctx: typer.Context,
    name: str = typer.Argument(help="Nom du job"),
) -> None:
    """Affiche le plan d'exécution (ordre topologique, groupes parallèles)."""
    engine = load_engine(ctx.obj["app_path"])
    job = engine.get_job(name)

    if job is None:
        from pyworkflow_engine.ports.storage import JobNotFoundError

        raise JobNotFoundError(f"Job '{name}' introuvable dans le backend.")

    plan = engine.get_execution_plan(job)

    if ctx.obj["format"] == "json":
        from pyworkflow_engine.adapters.cli.formatters.json_output import (
            execution_plan_to_json,
        )

        typer.echo(execution_plan_to_json(plan))
    else:
        from rich.table import Table

        console.print(f"\n[bold]Plan d'exécution[/bold] : [cyan]{name}[/cyan]\n")

        # Ordre d'exécution
        order_table = Table(title="Ordre topologique", show_lines=True)
        order_table.add_column("#", style="dim", justify="right")
        order_table.add_column("Step", style="cyan")
        for i, step_name in enumerate(plan["execution_order"], 1):
            order_table.add_row(str(i), step_name)
        console.print(order_table)

        # Groupes parallèles
        if plan.get("parallel_groups"):
            groups_table = Table(title="Groupes parallèles", show_lines=True)
            groups_table.add_column("Groupe", style="dim", justify="right")
            groups_table.add_column("Steps", style="cyan")
            for i, group in enumerate(plan["parallel_groups"], 1):
                groups_table.add_row(str(i), ", ".join(group))
            console.print(groups_table)

        # Avertissements
        if plan.get("validation_warnings"):
            console.print()
            for w in plan["validation_warnings"]:
                console.print(f"[yellow]⚠[/yellow]  {w}")
        console.print()
