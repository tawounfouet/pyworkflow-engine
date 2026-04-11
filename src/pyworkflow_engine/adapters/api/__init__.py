"""API adapter — serveur REST pour PyWorkflow Engine.

Installation : ``pip install pyworkflow-engine[api]``

Usage::

    from pyworkflow_engine.adapters.api import create_app
    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.adapters.storage.sqlite import SQLiteStorage

    engine = WorkflowEngine(storage=SQLiteStorage("workflow.db"))
    app = create_app(engine)

    # Lancer avec uvicorn
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""

from __future__ import annotations

__all__ = ["create_app"]


def __getattr__(name: str) -> object:
    """PEP 562 — lazy import pour éviter les erreurs si fastapi n'est pas installé."""
    if name == "create_app":
        try:
            from pyworkflow_engine.adapters.api.app import create_app

            return create_app
        except ImportError as exc:
            raise ImportError(
                "L'API adapter nécessite 'fastapi' et 'uvicorn'. "
                "Installez-le avec : pip install pyworkflow-engine[api]"
            ) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
