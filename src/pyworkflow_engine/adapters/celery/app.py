"""Factory pour l'instance Celery application (singleton configurable).

Usage::

    from pyworkflow_engine.adapters.celery.app import get_celery_app

    app = get_celery_app(
        broker_url="redis://localhost:6379/0",
        result_backend="redis://localhost:6379/1",
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from celery import Celery


def get_celery_app(
    broker_url: str = "redis://localhost:6379/0",
    result_backend: str | None = None,
    app_name: str = "pyworkflow_engine",
    task_serializer: str = "json",
    task_default_queue: str = "pyworkflow",
    task_track_started: bool = True,
    task_soft_time_limit: float | None = None,
    task_time_limit: float | None = None,
) -> "Celery":
    """Crée et configure une application Celery.

    À chaque appel avec les mêmes paramètres, une nouvelle instance est créée.
    Pour réutiliser la même instance, conservez la référence retournée.

    Args:
        broker_url: URL du broker (Redis ou RabbitMQ).
        result_backend: URL du backend de résultats (``None`` = désactivé).
        app_name: Nom de l'application Celery.
        task_serializer: Sérialiseur pour les arguments des tasks.
        task_default_queue: Queue par défaut pour les tasks.
        task_track_started: Activer le suivi de l'état STARTED.
        task_soft_time_limit: Soft time limit en secondes.
        task_time_limit: Hard time limit en secondes.

    Returns:
        Instance Celery configurée.

    Raises:
        ImportError: Si celery n'est pas installé.
    """
    try:
        from celery import Celery
    except ImportError as exc:
        raise ImportError(
            "Le Celery adapter nécessite la dépendance 'celery'. "
            "Installez-la avec : pip install pyworkflow-engine[celery]"
        ) from exc

    app = Celery(app_name, broker=broker_url, backend=result_backend)

    conf: dict = {
        "task_serializer": task_serializer,
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "UTC",
        "enable_utc": True,
        "task_track_started": task_track_started,
        "task_default_queue": task_default_queue,
        # Autodiscovery désactivé — les tasks sont déclarées explicitement
        "task_always_eager": False,
    }

    if task_soft_time_limit is not None:
        conf["task_soft_time_limit"] = task_soft_time_limit
    if task_time_limit is not None:
        conf["task_time_limit"] = task_time_limit

    app.conf.update(conf)
    return app
