"""
Callbacks globaux Typer (version, etc.).
"""

from __future__ import annotations

from typing import Optional

import typer


def version_callback(value: bool) -> None:
    """Affiche la version et quitte."""
    if value:
        from pyworkflow_engine import __version__

        typer.echo(f"PyWorkflow Engine v{__version__}")
        raise typer.Exit()


VERSION_OPTION = typer.Option(
    None,
    "--version",
    "-V",
    callback=version_callback,
    is_eager=True,
    help="Affiche la version et quitte.",
)
