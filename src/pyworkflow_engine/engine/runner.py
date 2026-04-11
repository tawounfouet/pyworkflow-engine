"""
WorkflowRunner — exécution pure des steps d'un workflow.

Responsabilité unique : orchestrer l'appel aux executors dans l'ordre
topologique. Pas de retry, pas de persistence, pas de suspension.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from pyworkflow_engine.engine.context import WorkflowContext

from pyworkflow_engine.exceptions import StepExecutionError, WorkflowSuspended
from pyworkflow_engine.executors import BaseExecutor, ExecutorRegistry
from pyworkflow_engine.models import JobRun, RunStatus, Step, StepRun, StepType
from pyworkflow_engine.models.enums import ExecutorType


class WorkflowRunner:
    """Exécute les steps d'un workflow dans l'ordre topologique.

    Responsabilité unique : orchestrer l'appel aux executors.
    Pas de retry, pas de persistence, pas de suspension — ces
    préoccupations sont gérées par l'appelant (WorkflowEngine).
    """

    def __init__(
        self,
        executor_registry: ExecutorRegistry | None = None,
        default_executor: Callable | None = None,
        step_executors: dict[StepType, Callable] | None = None,
    ):
        self._registry = executor_registry or ExecutorRegistry()
        self._default_executor = default_executor or self._execute_function_step
        self._step_executors = step_executors or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        job_run: JobRun,
        execution_order: list[str],
        context: WorkflowContext,
        retry_handler: Any | None = None,
    ) -> None:
        """Exécute une série de steps dans l'ordre donné.

        Args:
            job_run: Instance JobRun en cours.
            execution_order: Liste ordonnée des noms de steps.
            context: Contexte d'exécution.
            retry_handler: RetryHandler optionnel (None = pas de retry).

        Raises:
            WorkflowSuspended: Si un step demande une suspension.
            StepExecutionError: Si un step échoue sans retry réussi.
        """
        steps_by_name = {step.name: step for step in job_run.job.steps}

        for step_name in execution_order:
            step = steps_by_name[step_name]

            if not self._should_execute_step(step, context):
                continue

            step_run = StepRun(
                step_name=step.name,
                job_run_id=job_run.job_run_id,
                status=RunStatus.PENDING,
            )
            job_run.step_runs.append(step_run)

            try:
                step_run.start_execution()
                result = self.execute_single(step, context)
                step_run.complete_success(result or {})
                context.set_step_output(step.name, result)

            except WorkflowSuspended as e:
                step_run.suspend(str(e))
                raise

            except Exception as e:
                step_run.complete_failure(str(e))
                self._log_step_error(step_run, e)

                if retry_handler and step.retry_count > 0:
                    success = retry_handler.attempt(
                        step, step_run, context, self.execute_single
                    )
                    if success:
                        continue

                raise StepExecutionError(
                    f"Step '{step.name}' failed: {e}",
                    details={
                        "step_name": step.name,
                        "job_name": job_run.job.name,
                        "run_id": job_run.job_run_id,
                        "error_type": type(e).__name__,
                        "retry_count": step.retry_count,
                    },
                    job_name=job_run.job.name,
                    step_name=step.name,
                ) from e

    def execute_single(self, step: Step, context: WorkflowContext) -> Any:
        """Exécute un step individuel.

        Le routing se fait dans cet ordre de priorité :
        1. ``step.executor_name`` → lookup dans l'ExecutorRegistry (CUSTOM/named)
        2. ``step.executor_type`` → executor dédié (THREAD, PROCESS, ASYNC)
        3. ``step_executors[step.step_type]`` ou ``default_executor`` (LOCAL)

        Args:
            step: Définition du step.
            context: Contexte d'exécution.

        Returns:
            Résultat de l'exécution.

        Raises:
            StepExecutionError: Si l'exécution échoue.
            WorkflowSuspended: Si le step demande une suspension.
        """
        # 1. Named executor (CUSTOM) — priorité maximale
        if hasattr(step, "executor_name") and step.executor_name:
            advanced_executor = self._registry.get(step.executor_name)
            if advanced_executor:
                return advanced_executor.execute(step, context)

        # 2. ExecutorType routing
        typed_executor = self._resolve_executor(step)
        if typed_executor is not None:
            return typed_executor.execute(step, context)

        # 3. Fallback : step_type mapping ou default_executor (LOCAL)
        executor = self._step_executors.get(step.step_type, self._default_executor)
        if step.timeout:
            return self._execute_with_timeout(step, context, executor)
        return executor(step, context)

    def _resolve_executor(self, step: Step) -> BaseExecutor | None:
        """Route un step vers son executor selon ``step.executor_type``.

        Args:
            step: Step dont l'executor_type détermine le routing.

        Returns:
            Instance BaseExecutor, ou None si exécution locale (comportement
            par défaut via ``_execute_function_step``).

        Raises:
            StepExecutionError: Si le type CUSTOM n'est pas trouvé dans le
                registry.
        """
        et = step.executor_type

        if et == ExecutorType.LOCAL:
            return None  # Handled by default executor path

        if et == ExecutorType.THREAD:
            from pyworkflow_engine.executors.thread_pool import ThreadPoolStepExecutor

            return ThreadPoolStepExecutor()

        if et == ExecutorType.PROCESS:
            from pyworkflow_engine.executors.process_pool import ProcessPoolStepExecutor

            return ProcessPoolStepExecutor()

        if et == ExecutorType.ASYNC:
            from pyworkflow_engine.executors.async_exec import AsyncStepExecutor

            return AsyncStepExecutor()

        if et == ExecutorType.CUSTOM:
            # Fall through to named executor lookup (already handled above)
            return None

        # CELERY, KUBERNETES, HUMAN, EXTERNAL → not implemented in core
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_execute_step(self, step: Step, context: WorkflowContext) -> bool:
        if step.condition:
            try:
                return bool(step.condition(context.to_dict()))
            except Exception as e:
                self._log_condition_error(step, e)
                return False
        return True

    def _execute_with_timeout(
        self, step: Step, context: WorkflowContext, executor: Callable
    ) -> Any:
        import threading
        from queue import Queue

        result_q: Queue = Queue()
        exc_q: Queue = Queue()

        def target():
            try:
                result_q.put(executor(step, context))
            except Exception as exc:
                exc_q.put(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        timeout_seconds = step.timeout.total_seconds()
        thread.join(timeout_seconds)

        if thread.is_alive():
            raise StepExecutionError(
                f"Step '{step.name}' timed out after {timeout_seconds}s",
                details={
                    "step_name": step.name,
                    "timeout_seconds": timeout_seconds,
                    "error_type": "TimeoutError",
                },
                step_name=step.name,
            )

        if not exc_q.empty():
            raise exc_q.get()
        if not result_q.empty():
            return result_q.get()

        raise StepExecutionError(
            f"Step '{step.name}' completed without result",
            step_name=step.name,
        )

    def _execute_function_step(self, step: Step, context: WorkflowContext) -> Any:
        """Executor par défaut pour les steps FUNCTION.

        Utilise ``inspect.signature`` pour détecter si le handler
        accepte un argument (contexte) ou non.
        """
        if not step.handler:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function", step_name=step.name
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
                f"Function execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.handler, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                },
                step_name=step.name,
            ) from e

    def _log_step_error(self, step_run: StepRun, error: Exception) -> None:
        from pyworkflow_engine.logging import get_logger

        get_logger("engine.runner").error(
            "STEP ERROR [%s]: %s", step_run.step_name, error
        )

    def _log_condition_error(self, step: Step, error: Exception) -> None:
        from pyworkflow_engine.logging import get_logger

        get_logger("engine.runner").error("CONDITION ERROR [%s]: %s", step.name, error)
