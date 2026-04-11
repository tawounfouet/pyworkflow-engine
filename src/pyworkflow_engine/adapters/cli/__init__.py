"""
CLI adapter pour PyWorkflow Engine (Typer + Rich).

Import conditionnel : typer et rich sont des dépendances optionnelles.
Installez-les avec ``pip install pyworkflow-engine[cli]``.

L'attribut ``app`` est chargé en lazy via ``__getattr__`` pour éviter
le RuntimeWarning de Python lors de l'invocation ``-m`` et pour ne pas
planter à l'import si typer/rich ne sont pas installés.
"""

from __future__ import annotations

__all__ = ["app"]


def __getattr__(name: str) -> object:
    if name == "app":
        try:
            from pyworkflow_engine.adapters.cli.main import app  # noqa: PLC0415

            return app
        except ImportError as _exc:  # pragma: no cover
            _missing = "typer" if "typer" in str(_exc) else "rich"
            raise ImportError(
                f"Le CLI PyWorkflow nécessite '{_missing}'. "
                "Installez les dépendances avec : pip install pyworkflow-engine[cli]"
            ) from _exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
