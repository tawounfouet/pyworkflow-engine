"""
Advanced executors for the IAS Workflow Engine.

Provides specialized executors beyond the basic function executor:
- AsyncExecutor: For asynchronous operations
- ThreadPoolExecutor: For CPU-intensive parallel tasks
- ProcessPoolExecutor: For multi-process parallel execution
- RetryableExecutor: Advanced retry logic with backoff strategies
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Any, Callable, Optional, Dict, List, Union
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from ..core.models import Step, StepType
from ..core.context import WorkflowContext
from ..core.exceptions import StepExecutionError


class BaseExecutor(ABC):
    """Base class for all step executors."""

    @abstractmethod
    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Execute a step.

        Args:
            step: Step to execute.
            context: Workflow context.

        Returns:
            Step execution result.
        """
        pass


class ThreadPoolStepExecutor(BaseExecutor):
    """Executor using ThreadPoolExecutor for concurrent execution.

    Best for I/O-bound operations like network requests, file operations.
    """

    def __init__(self, max_workers: Optional[int] = None):
        """Initialize thread pool executor.

        Args:
            max_workers: Maximum number of worker threads.
        """
        self.max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None

    def _get_executor(self) -> ThreadPoolExecutor:
        """Get or create thread pool executor."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._executor

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Execute step in thread pool."""
        if not step.callable:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function", step_name=step.name
            )

        executor = self._get_executor()

        try:
            # Submit to thread pool
            if step.callable.__code__.co_argcount > 0:
                future = executor.submit(step.callable, context)
            else:
                future = executor.submit(step.callable)

            # Handle timeout if specified
            timeout_seconds = step.timeout.total_seconds() if step.timeout else None
            return future.result(timeout=timeout_seconds)

        except Exception as e:
            raise StepExecutionError(
                f"Thread pool execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.callable, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                    "executor_type": "ThreadPool",
                },
                step_name=step.name,
            ) from e

    def shutdown(self):
        """Shutdown thread pool executor."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


class ProcessPoolStepExecutor(BaseExecutor):
    """Executor using ProcessPoolExecutor for CPU-intensive tasks.

    Best for CPU-bound operations that can benefit from multiprocessing.
    Note: Functions must be picklable for process pool execution.
    """

    def __init__(self, max_workers: Optional[int] = None):
        """Initialize process pool executor.

        Args:
            max_workers: Maximum number of worker processes.
        """
        self.max_workers = max_workers
        self._executor: Optional[ProcessPoolExecutor] = None

    def _get_executor(self) -> ProcessPoolExecutor:
        """Get or create process pool executor."""
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=self.max_workers)
        return self._executor

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Execute step in process pool."""
        if not step.callable:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function", step_name=step.name
            )

        executor = self._get_executor()

        try:
            # For process pool, we can't pass the full context object
            # Extract relevant data as dict
            context_data = context.to_dict() if hasattr(context, "to_dict") else {}

            # Submit to process pool
            if step.callable.__code__.co_argcount > 0:
                future = executor.submit(step.callable, context_data)
            else:
                future = executor.submit(step.callable)

            # Handle timeout if specified
            timeout_seconds = step.timeout.total_seconds() if step.timeout else None
            return future.result(timeout=timeout_seconds)

        except Exception as e:
            raise StepExecutionError(
                f"Process pool execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.callable, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                    "executor_type": "ProcessPool",
                },
                step_name=step.name,
            ) from e

    def shutdown(self):
        """Shutdown process pool executor."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


class AsyncStepExecutor(BaseExecutor):
    """Executor for async functions using asyncio.

    Allows integration of async/await functions in workflows.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Initialize async executor.

        Args:
            loop: Event loop to use. If None, will get or create one.
        """
        self.loop = loop

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self.loop:
            return self.loop

        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in current thread, create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Execute async step."""
        if not step.callable:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function", step_name=step.name
            )

        if not asyncio.iscoroutinefunction(step.callable):
            raise StepExecutionError(
                f"Step '{step.name}' callable is not an async function",
                step_name=step.name,
            )

        loop = self._get_loop()

        try:
            # Create coroutine
            if step.callable.__code__.co_argcount > 0:
                coro = step.callable(context)
            else:
                coro = step.callable()

            # Handle timeout if specified
            if step.timeout:
                coro = asyncio.wait_for(coro, timeout=step.timeout.total_seconds())

            # Run coroutine
            return loop.run_until_complete(coro)

        except Exception as e:
            raise StepExecutionError(
                f"Async execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.callable, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                    "executor_type": "Async",
                },
                step_name=step.name,
            ) from e


class RetryableExecutor(BaseExecutor):
    """Executor with advanced retry capabilities.

    Provides exponential backoff, jitter, and custom retry conditions.
    """

    def __init__(
        self,
        base_executor: BaseExecutor,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retry_on: Optional[List[type]] = None,
    ):
        """Initialize retryable executor.

        Args:
            base_executor: Base executor to wrap.
            max_retries: Maximum number of retry attempts.
            base_delay: Base delay between retries (seconds).
            max_delay: Maximum delay between retries (seconds).
            exponential_base: Base for exponential backoff.
            jitter: Whether to add random jitter to delays.
            retry_on: List of exception types to retry on.
        """
        self.base_executor = base_executor
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retry_on = retry_on or [Exception]

    def _should_retry(self, exception: Exception) -> bool:
        """Determine if exception should trigger retry."""
        return any(isinstance(exception, exc_type) for exc_type in self.retry_on)

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt."""
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            import random

            # Add random jitter (±25% of delay)
            jitter_amount = delay * 0.25
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(0, delay)

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Execute step with advanced retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return self.base_executor.execute(step, context)

            except Exception as e:
                last_exception = e

                # Check if we should retry
                if attempt >= self.max_retries or not self._should_retry(e):
                    raise

                # Calculate and wait for retry delay
                delay = self._calculate_delay(attempt)
                if delay > 0:
                    time.sleep(delay)

        # This shouldn't be reached, but just in case
        if last_exception:
            raise last_exception
        else:
            raise StepExecutionError(
                f"Step '{step.name}' failed after {self.max_retries} retries",
                step_name=step.name,
            )


class ExecutorRegistry:
    """Registry for managing step executors."""

    def __init__(self):
        """Initialize executor registry."""
        self._executors: Dict[str, BaseExecutor] = {}

    def register(self, name: str, executor: BaseExecutor) -> None:
        """Register an executor.

        Args:
            name: Executor name.
            executor: Executor instance.
        """
        self._executors[name] = executor

    def get(self, name: str) -> Optional[BaseExecutor]:
        """Get executor by name.

        Args:
            name: Executor name.

        Returns:
            Executor instance or None if not found.
        """
        return self._executors.get(name)

    def list_executors(self) -> List[str]:
        """List all registered executor names.

        Returns:
            List of executor names.
        """
        return list(self._executors.keys())

    def shutdown_all(self) -> None:
        """Shutdown all executors that support it."""
        for executor in self._executors.values():
            if hasattr(executor, "shutdown"):
                try:
                    executor.shutdown()
                except Exception:
                    pass  # Ignore shutdown errors
