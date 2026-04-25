"""
InMemoryRegistryAdapter — thread-safe in-memory connector registry.

Implements RegistryPort using a plain dict protected by a threading.Lock.
This is the default registry used by ConnectorFactory.

The global singleton ``_default_registry`` is shared by the ``@connector``
decorator and ConnectorFactory.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Type

from pyconnectors.models.exceptions import ConnectorNotFoundError
from pyconnectors.ports.registry import RegistryPort

_logger = logging.getLogger("pyconnectors.registry")


class InMemoryRegistryAdapter(RegistryPort):
    """
    Thread-safe in-memory registry for connector classes.

    Each instance is independent. The module-level ``_default_registry``
    is the singleton used by the ``@connector`` decorator.
    """

    def __init__(self) -> None:
        self._connectors: Dict[str, Type[Any]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, connector_cls: Type[Any]) -> None:
        """Register a connector class by name. Thread-safe."""
        from pyconnectors.models.base import BaseConnector

        if not issubclass(connector_cls, BaseConnector):
            raise TypeError(f"{connector_cls!r} must be a subclass of BaseConnector")

        with self._lock:
            if name in self._connectors:
                _logger.warning(
                    "Connector '%s' already registered — overwriting with %s",
                    name,
                    connector_cls.__name__,
                )
            self._connectors[name] = connector_cls

        _logger.debug("Registered connector: %s → %s", name, connector_cls.__name__)

    def get(self, name: str) -> Type[Any]:
        """Get a connector class by name. Thread-safe."""
        with self._lock:
            if name not in self._connectors:
                available = sorted(self._connectors.keys())
                raise ConnectorNotFoundError(
                    f"Connector '{name}' not found in registry. Available: {available}"
                )
            return self._connectors[name]

    def is_registered(self, name: str) -> bool:
        """Check whether a name is registered. Thread-safe."""
        with self._lock:
            return name in self._connectors

    def list_names(self) -> List[str]:
        """Return sorted list of registered connector names. Thread-safe."""
        with self._lock:
            return sorted(self._connectors.keys())

    def list_connectors(self) -> Dict[str, Type[Any]]:
        """Return a copy of the full registry. Thread-safe."""
        with self._lock:
            return self._connectors.copy()

    def clear(self) -> None:
        """Clear the registry. Thread-safe. Useful for tests."""
        with self._lock:
            self._connectors.clear()


# Module-level singleton — shared by @connector decorator and ConnectorFactory
_default_registry: InMemoryRegistryAdapter = InMemoryRegistryAdapter()


def connector(name: str) -> Callable[[Type[Any]], Type[Any]]:
    """Decorator to register a connector class in the global registry."""

    def wrapper(cls: Type[Any]) -> Type[Any]:
        _default_registry.register(name, cls)
        return cls

    return wrapper
