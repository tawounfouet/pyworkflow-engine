"""Celery integration for PyConnectors."""
from __future__ import annotations

from typing import Any, Dict, Optional

from pyconnectors.config.base import ConnectorConfig
from pyconnectors.models.result import ConnectorResult
from pyconnectors.services.factory import ConnectorFactory

try:
    from celery import shared_task, Task
except ImportError:
    shared_task = None
    Task = object


def make_connector_task(name: str, config_dict: Optional[Dict[str, Any]] = None) -> Any:
    """
    Create a Celery shared task that executes a connector.

    Usage::

        run_pg = make_connector_task("db.pg", {"host": "localhost"})

        # In a Celery worker:
        run_pg.delay(query="SELECT 1")
    """
    if shared_task is None:
        raise ImportError(
            "Celery is not installed. Install it with: pip install celery"
        )

    config = ConnectorConfig.from_dict(config_dict or {})

    @shared_task(name=f"pyconnectors.{name}")
    def _task(**kwargs: Any) -> Dict[str, Any]:
        factory = ConnectorFactory()
        result = factory.execute(name, config, **kwargs)
        return result.to_dict()

    return _task


def connector_task(
    connector_name: str,
    config_dict: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Decorator that wraps a Celery task to receive a ConnectorResult.

    Usage::

        @connector_task("http.rest", {"base_url": "https://api.example.com"})
        def process_response(result: ConnectorResult): ...
    """
    if shared_task is None:
        raise ImportError(
            "Celery is not installed. Install it with: pip install celery"
        )

    def decorator(fn: Any) -> Any:
        config = ConnectorConfig.from_dict(config_dict or {})

        @shared_task(name=f"pyconnectors.{connector_name}.{fn.__name__}")
        def _task(**kwargs: Any) -> Any:
            factory = ConnectorFactory()
            result = factory.execute(connector_name, config, **kwargs)
            return fn(result)

        return _task

    return decorator
