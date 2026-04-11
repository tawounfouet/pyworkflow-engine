"""Sous-commande API — lance le serveur REST FastAPI.

Usage :
    pyworkflow api serve --app myproject.workflows:engine --port 8000
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="api",
    help="Lancer le serveur REST API (FastAPI + uvicorn).",
    no_args_is_help=True,
)

_console = Console()


@app.command("serve")
@error_handler
def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Adresse d'écoute."),
    port: int = typer.Option(8000, "--port", "-p", help="Port du serveur."),
    db: str = typer.Option("workflow.db", "--db", help="Chemin du fichier SQLite."),
    reload: bool = typer.Option(False, "--reload", help="Hot-reload (développement)."),
    cors_origins: Optional[list[str]] = typer.Option(
        None, "--cors-origins", help="Origines CORS autorisées."
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="Clé API (active l'authentification)."
    ),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Nombre de workers uvicorn."
    ),
) -> None:
    """Lance le serveur REST API PyWorkflow.

    Exemple :
        pyworkflow api serve --app myproject:engine --port 8000 --reload
    """
    try:
        from pyworkflow_engine.adapters.api.app import create_app
        from pyworkflow_engine.adapters.api.config import APIConfig
    except ImportError:
        from rich.console import Console

        Console(stderr=True).print(
            "[bold red]✗[/bold red] L'API nécessite 'fastapi' et 'uvicorn'. "
            "Installez avec : [cyan]pip install pyworkflow-engine\\[api][/cyan]"
        )
        raise typer.Exit(4)

    import uvicorn

    # ── Résolution du moteur ──────────────────────────────────────────────
    # Si --app est fourni, on charge l'instance existante de l'utilisateur.
    # Sinon on crée un WorkflowEngine autonome avec SQLitePersistence
    # (comportement par défaut : serveur "standalone" persisté sur disque).
    app_path = ctx.obj.get("app_path") if ctx.obj else None
    if app_path:
        engine = load_engine(app_path)
    else:
        from pyworkflow_engine import WorkflowEngine
        from pyworkflow_engine.adapters.persistence.sqlite import SQLitePersistence

        _console.print(
            f"[dim]ℹ  Aucun --app fourni — moteur autonome avec SQLite "
            f"([cyan]{db}[/cyan])[/dim]"
        )
        _engine = WorkflowEngine()
        _engine.persistence = SQLitePersistence(database_path=db)
        engine = _engine

    config = APIConfig(
        host=host,
        port=port,
        db_path=db,
        cors_origins=cors_origins or ["*"],
        api_key=api_key,
        require_auth=api_key is not None,
    )

    base_url = f"http://{host}:{port}"
    db_note = f"\n  [dim]🗄  SQLite     :[/dim]  [dim]{db}[/dim]" if not app_path else ""
    auth_note = (
        f"\n  [dim]🔑 Auth     :[/dim]  API key activée"
        if api_key
        else "\n  [dim]🔑 Auth     :[/dim]  [dim]désactivée[/dim]"
    )
    _console.print(
        Panel(
            f"  [bold cyan]🌐 Base URL  :[/bold cyan]  [link={base_url}]{base_url}[/link]\n"
            f"  [bold cyan]📖 Swagger   :[/bold cyan]  [link={base_url}/api/v1/docs]{base_url}/api/v1/docs[/link]\n"
            f"  [bold cyan]📄 ReDoc     :[/bold cyan]  [link={base_url}/api/v1/redoc]{base_url}/api/v1/redoc[/link]\n"
            f"  [bold cyan]⚙  OpenAPI   :[/bold cyan]  [link={base_url}/api/v1/openapi.json]{base_url}/api/v1/openapi.json[/link]\n"
            f"  [bold cyan]❤  Health    :[/bold cyan]  [link={base_url}/api/v1/health]{base_url}/api/v1/health[/link]"
            f"{db_note}"
            f"{auth_note}",
            title="[bold green]✓  PyWorkflow API[/bold green]",
            subtitle="[dim]Ctrl+C pour arrêter[/dim]",
            expand=False,
        )
    )

    api_app = create_app(engine=engine, config=config)
    uvicorn.run(
        api_app,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )
