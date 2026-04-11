"""TUI adapter — interface terminal interactive pour PyWorkflow Engine.

Installation : ``pip install pyworkflow-engine[tui]``

Usage::

    from pyworkflow_engine.adapters.tui import WorkflowTUI
    from pyworkflow_engine import WorkflowEngine

    engine = WorkflowEngine(persistence=my_backend)
    app = WorkflowTUI(engine)
    app.run()
"""

from __future__ import annotations

__all__ = ["WorkflowTUI"]


def __getattr__(name: str) -> object:
    if name == "WorkflowTUI":
        try:
            from pyworkflow_engine.adapters.tui.app import WorkflowTUI

            return WorkflowTUI
        except ImportError as exc:
            raise ImportError(
                "Le TUI adapter nécessite 'textual'. "
                "Installez-le avec : pip install pyworkflow-engine[tui]"
            ) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
