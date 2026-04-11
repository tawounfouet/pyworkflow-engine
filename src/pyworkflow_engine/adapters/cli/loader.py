"""
Loader — import dynamique de l'instance WorkflowEngine depuis le code utilisateur.

Pattern inspiré de Celery (--app) et Uvicorn (module:attr).
Convention :
  - "myproject.workflows:engine"  → attribut explicite
  - "myproject.workflows"         → cherche l'attribut "engine" par défaut
"""

from __future__ import annotations

import importlib
import os
import sys

import typer
from rich.console import Console

from pyworkflow_engine.adapters.cli.errors import EXIT_IMPORT_ERROR

_err = Console(stderr=True)

_DEFAULT_ATTR = "engine"
_ENV_VAR = "PYWORKFLOW_APP"


def load_engine(app_path: str | None) -> object:
    """Importe le module et retourne l'instance WorkflowEngine.

    Args:
        app_path: Chemin Python de la forme ``"module.path:attr"`` ou
            ``"module.path"`` (utilise alors l'attribut ``engine`` par défaut).
            Si ``None``, consulte la variable d'environnement ``PYWORKFLOW_APP``.

    Returns:
        L'instance ``WorkflowEngine`` résolue.

    Raises:
        SystemExit(3): Module introuvable, attribut absent, ou objet de
            mauvais type.
    """
    # Résolution finale du chemin (option CLI > env var)
    resolved = app_path or os.environ.get(_ENV_VAR)

    if not resolved:
        _err.print(
            f"[bold red]✗[/bold red] Aucune application spécifiée.\n"
            f"  Utilisez [cyan]--app module.path:engine[/cyan] "
            f"ou définissez [cyan]{_ENV_VAR}[/cyan].\n"
            f"  Exemple : [cyan]pyworkflow --app examples.tui_demo:engine tui[/cyan]"
        )
        raise typer.Exit(EXIT_IMPORT_ERROR)

    # Séparer module_path et attr_name
    if ":" in resolved:
        module_path, attr_name = resolved.rsplit(":", 1)
    else:
        module_path = resolved
        attr_name = _DEFAULT_ATTR

    # S'assurer que le répertoire courant est dans sys.path
    # (comportement attendu quand on lance depuis la racine du projet)
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    # Import du module
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        _err.print(
            f"[bold red]✗[/bold red] Module introuvable : [cyan]{module_path}[/cyan]\n"
            f"  Répertoire courant : [dim]{cwd}[/dim]\n"
            f"  Lancez la commande depuis la racine du projet, ou ajoutez le "
            f"répertoire contenant votre module au PYTHONPATH :\n"
            f"  [cyan]PYTHONPATH=. pyworkflow --app {resolved} ...[/cyan]"
        )
        raise typer.Exit(EXIT_IMPORT_ERROR) from exc
    except ImportError as exc:
        _err.print(
            f"[bold red]✗[/bold red] Impossible d'importer [cyan]{module_path}[/cyan] : {exc}"
        )
        raise typer.Exit(EXIT_IMPORT_ERROR) from exc

    # Résolution de l'attribut
    engine = getattr(module, attr_name, None)
    if engine is None:
        _err.print(
            f"[bold red]✗[/bold red] Attribut [cyan]{attr_name!r}[/cyan] "
            f"introuvable dans [cyan]{module_path}[/cyan].\n"
            f"  Exposez votre instance WorkflowEngine comme "
            f"[cyan]{module_path}:{attr_name}[/cyan]."
        )
        raise typer.Exit(EXIT_IMPORT_ERROR)

    # Validation du type (import tardif pour éviter la circularité)
    from pyworkflow_engine.facade import WorkflowEngine

    if not isinstance(engine, WorkflowEngine):
        _err.print(
            f"[bold red]✗[/bold red] [cyan]{resolved}[/cyan] n'est pas une instance "
            f"[bold]WorkflowEngine[/bold] (type : [yellow]{type(engine).__name__}[/yellow])."
        )
        raise typer.Exit(EXIT_IMPORT_ERROR)

    return engine
