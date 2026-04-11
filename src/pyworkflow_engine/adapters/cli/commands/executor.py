"""
Commandes de gestion des executors : list.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="executor",
    help="Inspecter les executors enregistrés dans le moteur.",
    no_args_is_help=True,
)
console = Console()


@app.command("list")
@error_handler
def list_executors(ctx: typer.Context) -> None:
    """Liste tous les executors enregistrés dans le moteur."""
    engine = load_engine(ctx.obj["app_path"])
    names = engine.list_executors()

    if ctx.obj["format"] == "json":
        import json

        typer.echo(json.dumps({"executors": names}, indent=2))
    else:
        if not names:
            console.print(
                "[dim]Aucun executor enregistré (le moteur utilise l'executor local par défaut).[/dim]"
            )
            return

        table = Table(
            title="⚙️  Executors enregistrés",
            show_lines=True,
            expand=False,
        )
        table.add_column("#", style="dim", justify="right")
        table.add_column("Nom", style="bold cyan")

        for i, name in enumerate(names, 1):
            table.add_row(str(i), name)

        console.print(table)
