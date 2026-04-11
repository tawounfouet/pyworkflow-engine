"""Celery adapter — exécution distribuée des workflow steps.

Installation : ``pip install pyworkflow-engine[celery]``

Usage::

    from pyworkflow_engine.adapters.celery import CeleryExecutor, CeleryConfig

    # Configuration minimale
    executor = CeleryExecutor(
        broker_url="redis://localhost:6379/0",
        result_backend="redis://localhost:6379/1",
    )
    engine.register_executor("celery", executor)

    # Via CeleryConfig
    config = CeleryConfig(
        broker_url="redis://localhost:6379/0",
        result_backend="redis://localhost:6379/1",
        task_timeout=120.0,
    )
    executor = CeleryExecutor(config=config)

Structure du package (ADR-007) :
    - config.py   → CeleryConfig dataclass (configuration)
    - app.py      → get_celery_app() factory
    - tasks.py    → execute_step_task (task worker)
    - executor.py → CeleryExecutor (implémente BaseExecutor)
"""

from __future__ import annotations

try:
    from pyworkflow_engine.adapters.celery.config import CeleryConfig
    from pyworkflow_engine.adapters.celery.executor import CeleryExecutor
except ImportError as exc:
    raise ImportError(
        "Le Celery adapter nécessite la dépendance 'celery'. "
        "Installez-la avec : pip install pyworkflow-engine[celery]"
    ) from exc

__all__ = ["CeleryExecutor", "CeleryConfig"]
