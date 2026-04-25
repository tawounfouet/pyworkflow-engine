try:
    import typer
    from rich.console import Console
except ImportError:
    raise ImportError("CLI requires typer and rich. Install with: pip install pyconnectors[cli]")

from pyconnectors.cli.commands import inspect, list, run, test

app = typer.Typer(help="PyConnectors CLI: Manage and execute connectors.")
console = Console()

app.add_typer(list.app, name="list", help="List available connectors")
app.add_typer(inspect.app, name="inspect", help="Inspect a connector's configuration and methods")
app.add_typer(run.app, name="run", help="Run a connector from a config file")
app.add_typer(test.app, name="test", help="Test a connector's connectivity")

if __name__ == "__main__":
    app()
