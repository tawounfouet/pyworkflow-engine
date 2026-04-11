"""GUI adapter — interface web interactive pour PyWorkflow Engine.

Basé sur NiceGUI (FastAPI + WebSocket natif).

Installation : ``pip install pyworkflow-engine[gui]``

Usage::

    from pyworkflow_engine.adapters.gui import WorkflowGUI
    from pyworkflow_engine import WorkflowEngine

    engine = WorkflowEngine(storage=my_backend)
    gui = WorkflowGUI(engine)
    gui.run(port=8080)
"""

from __future__ import annotations

__all__ = ["WorkflowGUI"]


def __getattr__(name: str) -> object:
    if name == "WorkflowGUI":
        try:
            from pyworkflow_engine.adapters.gui.app import WorkflowGUI

            return WorkflowGUI
        except ImportError as exc:
            raise ImportError(
                "Le GUI adapter nécessite 'nicegui'. "
                "Installez-le avec : pip install pyworkflow-engine[gui]"
            ) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
