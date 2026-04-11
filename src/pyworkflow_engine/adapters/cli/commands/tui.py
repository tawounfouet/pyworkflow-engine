"""Sous-commande TUI — lance l'interface Textual interactive."""

from __future__ import annotations

import typer
from rich.console import Console

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="tui",
    help="Lancer l'interface terminal interactive (Textual).",
    no_args_is_help=False,
)

_err = Console(stderr=True)


@app.callback(invoke_without_command=True)
@error_handler
def launch_tui(ctx: typer.Context) -> None:
    """Lance l'interface terminal interactive PyWorkflow."""
    try:
        from pyworkflow_engine.adapters.tui import WorkflowTUI
    except ImportError:
        _err.print(
            "[bold red]✗[/bold red] La TUI nécessite 'textual'. "
            "Installez avec : [cyan]pip install pyworkflow-engine[tui][/cyan]"
        )
        raise typer.Exit(4)

    engine = load_engine(ctx.obj["app_path"])
    tui_app = WorkflowTUI(engine)
    tui_app.run()
