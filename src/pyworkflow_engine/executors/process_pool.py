"""
ProcessPoolStepExecutor — exécution CPU-bound en sous-processus.

Utilise ``concurrent.futures.ProcessPoolExecutor`` pour isoler les steps
dans des processus séparés. Les fonctions passées en handler doivent être
**picklables** (pas de lambdas, pas de fonctions imbriquées).

Zéro dépendance externe — stdlib uniquement.
"""

from __future__ import annotations

import inspect
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext
    from pyworkflow_engine.models import Step

from pyworkflow_engine.exceptions import StepExecutionError
from pyworkflow_engine.executors.base import BaseExecutor


def _has_positional_params(fn) -> bool:
    """Retourne True si le callable accepte au moins un argument positionnel."""
    try:
        sig = inspect.signature(fn)
        params = [
            p
            for p in sig.parameters.values()
            if p.name not in ("self", "cls")
            and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        ]
        return bool(params)
    except (ValueError, TypeError):
        return False


class ProcessPoolStepExecutor(BaseExecutor):
    """Executor utilisant ProcessPoolExecutor.

    Idéal pour les opérations CPU-bound.

    Note:
        Les handlers doivent être **picklables** (définis au niveau module,
        pas de lambdas ni de closures). Le contexte est converti en ``dict``
        avant sérialisation inter-processus.

    Args:
        max_workers: Nombre maximum de processus. ``None`` = ``os.cpu_count()``.

    Examples:
        >>> from pyworkflow_engine.executors import ProcessPoolStepExecutor
        >>> from pyworkflow_engine.executors import ExecutorRegistry
        >>> registry = ExecutorRegistry()
        >>> registry.register("cpu", ProcessPoolStepExecutor(max_workers=4))
    """

    def __init__(self, max_workers: int | None = None) -> None:
        self.max_workers = max_workers
        self._executor: ProcessPoolExecutor | None = None

    def _get_executor(self) -> ProcessPoolExecutor:
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=self.max_workers)
        return self._executor

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Exécute le handler du step dans un processus séparé.

        Args:
            step: Step à exécuter. Le handler doit être picklable.
            context: Contexte converti en ``dict`` avant transmission.

        Returns:
            Valeur de retour du handler.

        Raises:
            StepExecutionError: Si le step n'a pas de handler ou si l'exécution
                échoue.
        """
        if not step.handler:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function", step_name=step.name
            )

        pool = self._get_executor()
        try:
            # Le contexte est sérialisé en dict pour le passage inter-processus
            context_data = context.to_dict() if hasattr(context, "to_dict") else {}

            if _has_positional_params(step.handler):
                future = pool.submit(step.handler, context_data)
            else:
                future = pool.submit(step.handler)

            timeout = step.timeout.total_seconds() if step.timeout else None
            return future.result(timeout=timeout)

        except Exception as e:
            raise StepExecutionError(
                f"Process pool execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.handler, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                    "executor_type": "ProcessPool",
                },
                step_name=step.name,
            ) from e

    def shutdown(self) -> None:
        """Arrête le pool de processus."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
