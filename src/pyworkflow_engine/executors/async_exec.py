"""
AsyncStepExecutor — exécution de fonctions async/await dans les workflows.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext
    from pyworkflow_engine.models import Step

from pyworkflow_engine.exceptions import StepExecutionError
from pyworkflow_engine.executors.base import BaseExecutor


class AsyncStepExecutor(BaseExecutor):
    """Executor pour fonctions async utilisant asyncio."""

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        self.loop = loop

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self.loop:
            return self.loop
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        if not step.handler:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function", step_name=step.name
            )

        if not asyncio.iscoroutinefunction(step.handler):
            raise StepExecutionError(
                f"Step '{step.name}' callable is not an async function",
                step_name=step.name,
            )

        loop = self._get_loop()
        try:
            sig = inspect.signature(step.handler)
            params = [
                p
                for p in sig.parameters.values()
                if p.name not in ("self", "cls")
                and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
            ]
            coro = step.handler(context) if params else step.handler()

            if step.timeout:
                coro = asyncio.wait_for(coro, timeout=step.timeout.total_seconds())

            return loop.run_until_complete(coro)

        except Exception as e:
            raise StepExecutionError(
                f"Async execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.handler, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                    "executor_type": "Async",
                },
                step_name=step.name,
            ) from e
