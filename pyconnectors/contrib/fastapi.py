"""FastAPI integration for PyConnectors."""

from typing import Any, Callable

from pyconnectors.config.base import ConnectorConfig
from pyconnectors.services.factory import ConnectorFactory

try:
    from fastapi import Depends
except ImportError:
    Depends = None


def get_connector_dependency(
    name: str, config_dict: dict[str, Any] | None = None
) -> Callable[[], Any]:
    """
    Returns a FastAPI dependency that yields a configured connector.
    """
    if Depends is None:
        raise ImportError("FastAPI is not installed.")

    config = ConnectorConfig.from_dict(config_dict or {})

    def dependency() -> Any:
        return ConnectorFactory.create(name, config=config)

    return dependency
