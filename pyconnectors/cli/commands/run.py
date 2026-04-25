import json

import typer
from rich.console import Console

from pyconnectors.config.base import ConnectorConfig
from pyconnectors.services.factory import ConnectorFactory

app = typer.Typer()
console = Console()


@app.callback(invoke_without_command=True)
def main(
    config_file: str = typer.Argument(..., help="Path to the JSON configuration file"),
) -> None:
    """Run a connector from a JSON configuration file."""
    try:
        config = ConnectorConfig.from_json_file(config_file)

        # Get connector name from config params (for CLI purposes)
        # Ideally, we pass the connector name as an argument
        connector_name = config.params.get("connector_name")
        if not connector_name:
            console.print(
                "[red]Error: 'connector_name' must be provided in the JSON file params.[/red]"
            )
            raise typer.Exit(1)

        connector = ConnectorFactory.create(connector_name, config=config)

        # Extract arguments for the execute method
        args = config.params.get("execute_args", [])
        kwargs = config.params.get("execute_kwargs", {})

        console.print(f"[cyan]Running connector '{connector_name}'...[/cyan]")
        result = connector.safe_execute(*args, **kwargs)

        if result.success:
            console.print(f"[green]Success![/green] Duration: {result.duration:.4f}s")
            console.print(json.dumps(result.data, indent=2))
        else:
            console.print(f"[red]Error:[/red] {result.error}")

    except Exception as e:
        console.print(f"[red]Execution failed: {e}[/red]")
        raise typer.Exit(1)
