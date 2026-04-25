import typer
from rich.console import Console

from pyconnectors.config.base import ConnectorConfig
from pyconnectors.services.factory import ConnectorFactory

app = typer.Typer()
console = Console()


@app.callback(invoke_without_command=True)
def main(
    connector: str = typer.Argument(..., help="Name of the connector to test"),
) -> None:
    """Test a connector's instantiation and basic connectivity without full execution."""
    try:
        # Load empty config
        config = ConnectorConfig()

        console.print(f"[cyan]Testing connector '{connector}'...[/cyan]")
        conn = ConnectorFactory.create(connector, config=config)

        console.print(f"[green]Successfully instantiated {conn.__class__.__name__}![/green]")
        console.print(
            "[yellow]Note: Full connectivity test requires valid configuration and execute() arguments.[/yellow]"
        )

    except ImportError as e:
        console.print(f"[red]ImportError:[/red] {e}")
    except Exception as e:
        console.print(f"[red]Failed to instantiate connector:[/red] {e}")
        raise typer.Exit(1)
