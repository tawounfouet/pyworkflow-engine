"""
ThreadPoolStepExecutor — exécution I/O-bound via threads.

Idéal pour les opérations réseau, fichiers, ou tout workload thread-safe.
Utilise ``inspect.signature`` pour la détection de signature (robuste aux
partials, méthodes de classe, *args/**kwargs).

Pour l'exécution CPU-bound en sous-processus, voir ``process_pool.py``.
"""

from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
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


class ThreadPoolStepExecutor(BaseExecutor):
    """Executor utilisant ThreadPoolExecutor.

    Idéal pour les opérations I/O-bound (réseau, fichiers).
    """

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._executor

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        if not step.handler:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function", step_name=step.name
            )

        pool = self._get_executor()
        try:
            if _has_positional_params(step.handler):
                future = pool.submit(step.handler, context)
            else:
                future = pool.submit(step.handler)

            timeout = step.timeout.total_seconds() if step.timeout else None
            return future.result(timeout=timeout)

        except Exception as e:
            raise StepExecutionError(
                f"Thread pool execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.handler, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                    "executor_type": "ThreadPool",
                },
                step_name=step.name,
            ) from e

    def shutdown(self) -> None:
        """Arrête le pool de threads."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
