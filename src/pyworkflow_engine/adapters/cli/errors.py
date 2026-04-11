"""
Error handler decorator et exit codes structurés pour la CLI PyWorkflow.

Centralise la gestion des exceptions domaine en messages Rich + typer.Exit.
Chaque code de sortie correspond à une catégorie d'erreur identifiable
dans les scripts et pipelines CI.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

import typer
from rich.console import Console

from pyworkflow_engine.exceptions import (
    DAGValidationError,
    StepExecutionError,
    WorkflowError,
    WorkflowFailed,
)
from pyworkflow_engine.ports.persistence import JobNotFoundError, PersistenceError

err = Console(stderr=True)

# ---------------------------------------------------------------------------
# Exit codes structurés
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_JOB_ERROR = 1  # JobNotFoundError, DAGValidationError, WorkflowError
EXIT_STEP_ERROR = 2  # StepExecutionError, WorkflowFailed
EXIT_IMPORT_ERROR = 3  # ImportError, module/attribut introuvable
EXIT_CONFIG_ERROR = 4  # PersistenceError, configuration manquante
EXIT_UNEXPECTED = 5  # Exception inattendue


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def error_handler(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator qui intercepte les exceptions domaine et produit des messages Rich.

    Doit être appliqué APRÈS ``@app.command()`` (i.e. plus proche du ``def``).

    Example::

        @app.command("list")
        @error_handler
        def list_jobs(ctx: typer.Context) -> None: ...
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except typer.Exit:
            raise
        except typer.Abort:
            raise
        except JobNotFoundError as e:
            err.print(f"[bold red]✗[/bold red] Job introuvable : {e}")
            raise typer.Exit(EXIT_JOB_ERROR) from e
        except DAGValidationError as e:
            err.print(f"[bold red]✗[/bold red] DAG invalide : {e}")
            raise typer.Exit(EXIT_JOB_ERROR) from e
        except StepExecutionError as e:
            err.print(f"[bold red]✗[/bold red] Échec step : {e}")
            raise typer.Exit(EXIT_STEP_ERROR) from e
        except WorkflowFailed as e:
            err.print(f"[bold red]✗[/bold red] Workflow échoué : {e}")
            raise typer.Exit(EXIT_STEP_ERROR) from e
        except PersistenceError as e:
            err.print(f"[bold red]✗[/bold red] Erreur persistence : {e}")
            raise typer.Exit(EXIT_CONFIG_ERROR) from e
        except WorkflowError as e:
            err.print(f"[bold red]✗[/bold red] Erreur workflow : {e}")
            raise typer.Exit(EXIT_JOB_ERROR) from e
        except Exception as e:
            err.print(
                f"[bold red]✗[/bold red] Erreur inattendue ({type(e).__name__}) : {e}"
            )
            raise typer.Exit(EXIT_UNEXPECTED) from e

    return wrapper
