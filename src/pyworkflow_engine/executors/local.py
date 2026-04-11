"""
LocalExecutor — exécution synchrone dans le même processus.

C'est l'executor par défaut, équivalent à un appel direct de la fonction.
Zéro overhead de pool, zéro dépendance externe.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext
    from pyworkflow_engine.models import Step

from pyworkflow_engine.exceptions import StepExecutionError, WorkflowSuspended
from pyworkflow_engine.executors.base import BaseExecutor


class LocalExecutor(BaseExecutor):
    """Executor synchrone dans le même processus (comportement par défaut).

    Exécute le callable du step directement, sans pool ni sérialisation.
    Utilise ``inspect.signature`` pour détecter si le callable accepte
    un argument (contexte) ou non.

    Idéal pour :
        - Les steps légers et les tests
        - Les fonctions qui nécessitent un accès direct à WorkflowContext
        - Les environnements single-thread

    Examples:
        >>> from pyworkflow_engine import Job, Step, StepType, WorkflowEngine
        >>> from pyworkflow_engine import LocalExecutor, ExecutorRegistry
        >>>
        >>> def process(ctx):
        ...     return {"count": 42}
        >>>
        >>> registry = ExecutorRegistry()
        >>> registry.register("local", LocalExecutor())
        >>>
        >>> step = Step(
        ...     name="process",
        ...     step_type=StepType.FUNCTION,
        ...     handler=process,
        ...     executor_name="local",
        ... )
    """

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Exécute le callable du step dans le thread courant.

        Args:
            step: Step à exécuter. Doit avoir un ``callable`` non-None.
            context: Contexte de workflow transmis si le callable l'accepte.

        Returns:
            Valeur de retour du callable.

        Raises:
            StepExecutionError: Si le step n'a pas de callable ou si
                l'exécution échoue.
            WorkflowSuspended: Propagé tel quel si le callable le lève.
        """
        if not step.handler:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function",
                step_name=step.name,
            )

        try:
            sig = inspect.signature(step.handler)
            params = [
                p
                for p in sig.parameters.values()
                if p.name not in ("self", "cls")
                and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
            ]
            if params:
                return step.handler(context)
            return step.handler()

        except WorkflowSuspended:
            raise
        except Exception as e:
            raise StepExecutionError(
                f"Local execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.handler, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                    "executor_type": "Local",
                },
                step_name=step.name,
            ) from e
