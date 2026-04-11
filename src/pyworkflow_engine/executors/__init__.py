"""
PyWorkflow Engine — couche exécution.

Ce package contient les executors spécialisés :

- ``base``         : BaseExecutor, ExecutorRegistry
- ``local``        : LocalExecutor (synchrone, même processus)
- ``thread_pool``  : ThreadPoolStepExecutor (I/O-bound)
- ``process_pool`` : ProcessPoolStepExecutor (CPU-bound)
- ``async_exec``   : AsyncStepExecutor
- ``retryable``    : RetryableExecutor
"""

from __future__ import annotations

from .async_exec import AsyncStepExecutor
from .base import BaseExecutor, ExecutorRegistry
from .local import LocalExecutor
from .process_pool import ProcessPoolStepExecutor
from .retryable import RetryableExecutor
from .thread_pool import ThreadPoolStepExecutor

__all__ = [
    "BaseExecutor",
    "ExecutorRegistry",
    "LocalExecutor",
    "ThreadPoolStepExecutor",
    "ProcessPoolStepExecutor",
    "AsyncStepExecutor",
    "RetryableExecutor",
]
