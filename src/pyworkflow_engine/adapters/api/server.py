"""Server helper — lance uvicorn en standalone.

Utilitaire optionnel pour démarrer le serveur sans passer par la CLI.

Usage::

    from pyworkflow_engine.adapters.api.server import run_server
    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.adapters.persistence.sqlite import SQLitePersistence

    engine = WorkflowEngine(persistence=SQLitePersistence("workflow.db"))
    run_server(engine, host="0.0.0.0", port=8000)
"""

from __future__ import annotations

from typing import Any


def run_server(
    engine: Any,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    workers: int = 1,
    **kwargs: Any,
) -> None:
    """Lance le serveur uvicorn avec l'app FastAPI configurée.

    Args:
        engine: Instance WorkflowEngine.
        host: Adresse d'écoute.
        port: Port du serveur.
        reload: Active le hot-reload (développement).
        workers: Nombre de workers uvicorn.
        **kwargs: Arguments additionnels passés à ``create_app()``.
    """
    import uvicorn

    from pyworkflow_engine.adapters.api.app import create_app

    app = create_app(engine=engine, **kwargs)
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )
