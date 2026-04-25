import inspect as pyinspect

import typer
from rich.console import Console

from pyconnectors.adapters.registry.memory import _default_registry

app = typer.Typer()
console = Console()


@app.callback(invoke_without_command=True)
def main(connector: str = typer.Argument(..., help="Name of the connector to inspect")) -> None:
    """Inspect a connector to see its docstring and methods."""
    try:
        cls = _default_registry.get(connector)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Connector: {connector}[/bold cyan]")
    console.print(f"[bold magenta]Class: {cls.__name__}[/bold magenta]")

    doc = pyinspect.getdoc(cls)
    if doc:
        console.print("\n[bold]Description:[/bold]")
        console.print(f"{doc}")

    console.print("\n[bold]Execute Method Signature:[/bold]")
    sig = pyinspect.signature(cls.execute)
    console.print(f"execute{sig}")
