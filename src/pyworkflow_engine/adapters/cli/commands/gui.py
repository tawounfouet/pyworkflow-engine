"""Sous-commande GUI — lance l'interface web NiceGUI interactive.

Usage :
    pyworkflow gui --port 8080
    pyworkflow gui --app myproject.workflows:engine --port 8080
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="gui",
    help="Lancer l'interface web interactive (NiceGUI).",
    no_args_is_help=False,
)

_console = Console()
_err = Console(stderr=True)


@app.callback(invoke_without_command=True)
@error_handler
def launch_gui(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Adresse d'écoute."),
    port: int = typer.Option(8080, "--port", "-p", help="Port du serveur."),
    db: str = typer.Option(
        "workflow.db", "--db", help="Chemin SQLite (mode standalone)."
    ),
    dark: bool = typer.Option(True, "--dark/--light", help="Mode sombre (défaut: activé)."),
    reload: bool = typer.Option(
        False, "--reload", help="Hot-reload (développement)."
    ),
    show: bool = typer.Option(
        False, "--show/--no-show", help="Ouvrir le navigateur au démarrage."
    ),
    title: str = typer.Option(
        "PyWorkflow Engine", "--title", help="Titre affiché dans l'onglet."
    ),
    refresh: float = typer.Option(
        3.0, "--refresh", help="Intervalle de rafraîchissement (secondes)."
    ),
) -> None:
    """Lance l'interface web interactive PyWorkflow (NiceGUI).

    Exemple :
        pyworkflow gui --port 8080
        pyworkflow gui --app myproject:engine --port 8080 --light
    """
    try:
        from pyworkflow_engine.adapters.gui import WorkflowGUI
        from pyworkflow_engine.adapters.gui.config import GUIConfig
    except ImportError:
        _err.print(
            "[bold red]✗[/bold red] Le GUI nécessite 'nicegui'. "
            "Installez avec : [cyan]pip install pyworkflow-engine\\[gui][/cyan]"
        )
        raise typer.Exit(4)

    # ── Résolution du moteur ──────────────────────────────────────────────
    app_path = ctx.obj.get("app_path") if ctx.obj else None
    standalone = not bool(app_path)

    if app_path:
        engine = load_engine(app_path)
    else:
        from pyworkflow_engine import WorkflowEngine
        from pyworkflow_engine.adapters.storage.sqlite import SQLiteStorage

        _engine = WorkflowEngine()
        _engine.storage = SQLiteStorage(database_path=db)
        engine = _engine

    # ── Bannière de démarrage ─────────────────────────────────────────────
    mode_line = (
        f"[dim]🗄  SQLite : [cyan]{db}[/cyan][/dim]"
        if standalone
        else f"[dim]🔌 App    : [cyan]{app_path}[/cyan][/dim]"
    )
    _console.print(
        Panel(
            f"[bold green]✓  GUI PyWorkflow Engine[/bold green]\n\n"
            f"  🌐 URL     : [link=http://{host}:{port}]http://{host}:{port}[/link]\n"
            f"  {mode_line}\n"
            f"  🎨 Thème   : {'sombre' if dark else 'clair'}\n"
            f"  ♻  Refresh : {refresh} s\n\n"
            f"[dim]Ctrl+C pour arrêter[/dim]",
            title="[bold]PyWorkflow GUI[/bold]",
            border_style="green",
        )
    )

    # ── Démarrage NiceGUI ─────────────────────────────────────────────────
    config = GUIConfig(
        host=host,
        port=port,
        db_path=db,
        title=title,
        dark_mode=dark,
        reload=reload,
        show_browser=show,
        refresh_interval=refresh,
    )
    gui = WorkflowGUI(engine, config)
    gui.run()
