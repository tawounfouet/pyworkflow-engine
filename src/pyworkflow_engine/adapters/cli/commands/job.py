"""
Commandes de gestion des jobs : list, inspect, validate, plan, sync.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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


# ── Helpers sync ──────────────────────────────────────────────────────────

_PLACEHOLDER = "[dim]—[/dim]"


def _render_dry_run_table(enriched: list[dict]) -> None:
    """Affiche le tableau dry-run des jobs à synchroniser."""
    table = Table(
        title="🔍  Dry-run — jobs à synchroniser",
        show_lines=False,
        header_style="bold",
    )
    table.add_column("Nom", style="bold cyan", no_wrap=True)
    table.add_column("Version", style="dim")
    table.add_column("Steps", justify="right", style="magenta")
    table.add_column("Schedule", style="dim")
    table.add_column("Owner", style="dim")
    table.add_column("Tags", style="dim")

    for item in enriched:
        j = item["job"]
        table.add_row(
            j.name,
            j.version,
            str(len(j.steps)),
            item.get("schedule") or _PLACEHOLDER,
            item.get("owner") or _PLACEHOLDER,
            ", ".join(item.get("tags", [])) or _PLACEHOLDER,
        )

    console.print(table)
    console.print(
        f"\n[dim]{len(enriched)} job(s) seraient synchronisés "
        "(--dry-run, rien n'a été écrit)[/dim]"
    )


def _render_catalog_table(catalog: list[dict]) -> None:
    """Affiche le tableau des jobs persistés en base."""
    show_table = Table(
        title="📦  Jobs persistés dans workflow.db",
        show_lines=False,
        header_style="bold",
    )
    show_table.add_column("Nom", style="bold cyan", no_wrap=True)
    show_table.add_column("Version", style="dim")
    show_table.add_column("Enabled", justify="center")
    show_table.add_column("Description")
    show_table.add_column("Updated", style="dim")

    for row in catalog:
        enabled_icon = "✅" if row.get("enabled") else "❌"
        desc = (row.get("description") or "")[:60]
        updated_at = (row.get("updated_at") or "")[:19]
        show_table.add_row(
            row["name"],
            row.get("version", "?"),
            enabled_icon,
            desc,
            updated_at,
        )

    console.print(show_table)
    console.print(f"\n[dim]{len(catalog)} job(s) en base[/dim]")


# ── Commande sync ─────────────────────────────────────────────────────────


@app.command("sync")
@error_handler
def sync_jobs(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Affiche ce qui serait synchronisé sans rien écrire en base.",
    ),
    show: bool = typer.Option(
        False,
        "--show",
        "-s",
        help="Affiche le tableau des jobs persistés après la sync.",
    ),
) -> None:
    """Synchronise le catalogue de jobs (manifest.yaml) → workflow.db (table jobs).

    Lit chaque job déclaré dans jobs/manifest.yaml + modules Python,
    puis effectue un UPSERT dans la table ``jobs``.

    Idempotent : peut être rejoué sans risque à chaque déploiement.
    """
    from jobs.shared.loader import JobLoadError, load_all_jobs_with_metadata
    from jobs.shared.persistence import JobCatalogPersistence

    if dry_run:
        try:
            enriched = load_all_jobs_with_metadata()
        except (FileNotFoundError, JobLoadError) as exc:
            console.print(f"[bold red]✗[/bold red] {exc}")
            raise typer.Exit(1) from exc
        _render_dry_run_table(enriched)
        return

    pers = JobCatalogPersistence()
    if not pers.available():
        console.print(
            "[bold red]✗[/bold red] workflow.db introuvable ou table 'jobs' absente.\n"
            "[dim]Lancez d'abord une commande pyworkflow pour initialiser la DB.[/dim]"
        )
        raise typer.Exit(1)

    try:
        with console.status(
            "[bold cyan]Synchronisation du catalogue de jobs…[/bold cyan]"
        ):
            stats = pers.sync_catalog()
    except (JobLoadError, FileNotFoundError) as exc:
        console.print(f"[bold red]✗ Erreur catalogue:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    inserted = stats["inserted"]
    updated = stats["updated"]
    total = stats["total"]

    lines: list[str] = []
    if inserted:
        lines.append(f"[bold green]+{inserted}[/bold green] job(s) insérés")
    if updated:
        lines.append(f"[bold yellow]~{updated}[/bold yellow] job(s) mis à jour")
    if not lines:
        lines.append("[dim]Aucun changement (déjà à jour)[/dim]")

    console.print(
        Panel(
            "  ".join(lines) + f"  [dim]({total} total)[/dim]",
            title="✅  Synchronisation terminée",
            border_style="green",
        )
    )

    if show:
        catalog = pers.list_catalog()
        if catalog:
            _render_catalog_table(catalog)
        else:
            console.print("[dim]Aucun job en base.[/dim]")
