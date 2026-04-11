"""
Adapter executors — implémentations concrètes du port BaseExecutor.

Chaque executor implémente le contrat défini dans
``pyworkflow_engine.ports.executor.BaseExecutor``.

Executors disponibles (stdlib uniquement) :
    - :class:`LocalExecutor`          — synchrone, même processus
    - :class:`ThreadPoolStepExecutor` — I/O-bound via threads
    - :class:`ProcessPoolStepExecutor`— CPU-bound via sous-processus
    - :class:`AsyncStepExecutor`      — fonctions async/await
    - :class:`RetryableExecutor`      — wrapper avec retry exponentiel
"""

from __future__ import annotations

from pyworkflow_engine.adapters.executors.async_exec import AsyncStepExecutor
from pyworkflow_engine.adapters.executors.local import LocalExecutor
from pyworkflow_engine.adapters.executors.process_pool import ProcessPoolStepExecutor
from pyworkflow_engine.adapters.executors.retryable import RetryableExecutor
from pyworkflow_engine.adapters.executors.thread_pool import ThreadPoolStepExecutor

__all__ = [
    "LocalExecutor",
    "ThreadPoolStepExecutor",
    "ProcessPoolStepExecutor",
    "AsyncStepExecutor",
    "RetryableExecutor",
]
