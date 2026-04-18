"""
Point d'entrée CLI principal de PyWorkflow Engine.

Commandes disponibles :
  pyworkflow job  list|inspect|validate|plan
  pyworkflow run  start|status|history|resume|cancel
  pyworkflow executor list

Options globales (transmises via ``ctx.obj``) :
  --app / -a   Chemin Python de l'instance WorkflowEngine (module:attr).
  --format     Formatage de sortie : table (défaut) ou json.
  --verbose    Active les messages de debug.
  --version    Affiche la version et quitte.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from pyworkflow_engine.adapters.cli.callbacks import VERSION_OPTION
from pyworkflow_engine.adapters.cli.commands import agent as agent_commands
from pyworkflow_engine.adapters.cli.commands import executor as executor_commands
from pyworkflow_engine.adapters.cli.commands import job as job_commands
from pyworkflow_engine.adapters.cli.commands import run as run_commands


def _bootstrap_catalog_path() -> None:
    """Injecte la racine du projet dans sys.path pour rendre agents/ importable.

    Cherche un dossier ``agents/`` en remontant depuis src/pyworkflow_engine/
    jusqu'à la racine du dépôt.  Sans cela, ``pyworkflow agent run`` échoue
    avec ``ModuleNotFoundError: No module named 'agents'`` car le catalogue
    n'est pas un package installé dans le .venv.

    Ordre de recherche :
      1. Depuis ``__file__`` (src/pyworkflow_engine/adapters/cli/main.py)
         → remonte 5 niveaux jusqu'à la racine du projet.
      2. Depuis le répertoire courant (``Path.cwd()``).
    """
    candidates: list[Path] = [
        # src/pyworkflow_engine/adapters/cli/main.py  →  5 parents  →  racine
        Path(__file__).resolve().parents[4],
        Path.cwd(),
    ]
    for candidate in candidates:
        if (candidate / "agents").is_dir() and (
            candidate / "agents" / "manifest.yaml"
        ).exists():
            root_str = str(candidate)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            return


# Injecter le path catalog dès le démarrage du module CLI
_bootstrap_catalog_path()


def _load_dotenv() -> None:
    """Charge le fichier .env le plus proche si python-dotenv est disponible.

    Cherche .env en remontant depuis le répertoire courant puis depuis la
    racine du projet déduite de sys.path — même logique que les scripts
    examples/*.py.  Sans cela, ``OPENAI_API_KEY`` définie dans .env n'est
    pas visible lors d'un appel CLI (``pyworkflow agent chat``).
    """
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return  # python-dotenv optionnel

    # Priorité 1 : .env dans le CWD ou un parent
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path, override=False)
        return

    # Priorité 2 : .env à la racine du projet (parents[4] de ce fichier)
    project_root = Path(__file__).resolve().parents[4]
    candidate = project_root / ".env"
    if candidate.exists():
        load_dotenv(candidate, override=False)


_load_dotenv()

# ---------------------------------------------------------------------------
# Root app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="pyworkflow",
    help=(
        "PyWorkflow Engine — orchestration de workflows Python.\n\n"
        "Spécifiez votre application via [cyan]--app module:engine[/cyan] "
        "ou la variable d'environnement [cyan]PYWORKFLOW_APP[/cyan]."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)

# Sub-command groups
app.add_typer(agent_commands.app, name="agent")
app.add_typer(job_commands.app, name="job")
app.add_typer(run_commands.app, name="run")
app.add_typer(executor_commands.app, name="executor")

# API sub-command — optionnel, n'apparaît que si fastapi est installé
try:
    from pyworkflow_engine.adapters.cli.commands import api as api_commands

    app.add_typer(api_commands.app, name="api")
except ImportError:
    pass

# TUI sub-command — optionnel, n'apparaît que si textual est installé
try:
    from pyworkflow_engine.adapters.cli.commands import tui as tui_commands

    app.add_typer(tui_commands.app, name="tui")
except ImportError:
    pass

# GUI sub-command — optionnel, n'apparaît que si nicegui est installé
try:
    from pyworkflow_engine.adapters.cli.commands import gui as gui_commands

    app.add_typer(gui_commands.app, name="gui")
except ImportError:
    pass

_err = Console(stderr=True)


# ---------------------------------------------------------------------------
# Global callback — options globales
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    app_path: Optional[str] = typer.Option(
        None,
        "--app",
        "-a",
        envvar="PYWORKFLOW_APP",
        help=(
            "Chemin Python de l'instance WorkflowEngine.\n"
            "Format : [cyan]module.path:attr[/cyan] "
            "ou [cyan]module.path[/cyan] (attr par défaut : [cyan]engine[/cyan])."
        ),
        show_envvar=True,
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Format de sortie : [cyan]table[/cyan] (défaut) ou [cyan]json[/cyan].",
        metavar="FORMAT",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Active les messages de debug.",
    ),
    version: Optional[bool] = VERSION_OPTION,
) -> None:
    """Initialise le contexte partagé pour tous les sous-commandes."""
    # Validation du format
    valid_formats = {"table", "json"}
    if output_format not in valid_formats:
        _err.print(
            f"[bold red]✗[/bold red] Format inconnu : [cyan]{output_format}[/cyan]. "
            f"Valeurs acceptées : {', '.join(sorted(valid_formats))}."
        )
        raise typer.Exit(4)

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    # Stockage dans ctx.obj — accessible par tous les sous-commandes via ctx.obj
    ctx.ensure_object(dict)
    ctx.obj["app_path"] = app_path
    ctx.obj["format"] = output_format
    ctx.obj["verbose"] = verbose


# ---------------------------------------------------------------------------
# Entrypoint (script direct)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
