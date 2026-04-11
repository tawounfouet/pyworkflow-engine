"""
RetryableExecutor — retry avancé avec backoff exponentiel et jitter.

À utiliser pour wraper un BaseExecutor avec une stratégie de retry
configurable (contrairement au RetryHandler interne du WorkflowEngine
qui utilise la config ``step.retry_count``).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..engine.context import WorkflowContext
    from ..models import Step

from ..exceptions import StepExecutionError
from .base import BaseExecutor


class RetryableExecutor(BaseExecutor):
    """Wrapper d'executor avec retry exponentiel et jitter."""

    def __init__(
        self,
        base_executor: BaseExecutor,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retry_on: list[type] | None = None,
    ):
        self.base_executor = base_executor
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retry_on = retry_on or [Exception]

    def _should_retry(self, exc: Exception) -> bool:
        return any(isinstance(exc, t) for t in self.retry_on)

    def _delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)
        if self.jitter:
            import random

            delay += random.uniform(-delay * 0.25, delay * 0.25)
        return max(0.0, delay)

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                return self.base_executor.execute(step, context)
            except Exception as e:
                last_exc = e
                if attempt >= self.max_retries or not self._should_retry(e):
                    raise
                delay = self._delay(attempt)
                if delay > 0:
                    time.sleep(delay)

        if last_exc:
            raise last_exc
        raise StepExecutionError(
            f"Step '{step.name}' failed after {self.max_retries} retries",
            step_name=step.name,
        )
