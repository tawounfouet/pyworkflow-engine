"""
ConnectorLoader — discovers and registers connector plugins via entry_points.

Third-party packages expose connectors by declaring an entry point in their
``pyproject.toml``::

    [project.entry-points."pyconnectors.connectors"]
    my_connector = "mypackage.connector:MyConnector"

ConnectorLoader scans these entry points at startup and registers each
class into the global registry.

Usage::

    loader = ConnectorLoader()
    loader.load()          # registers all discovered plugins
    loader.load_all()      # alias
"""
from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Optional

from pyconnectors.adapters.registry.memory import _default_registry
from pyconnectors.ports.logger import LoggerPort

_logger = logging.getLogger("pyconnectors.loader")

ENTRY_POINT_GROUP = "pyconnectors.connectors"


class ConnectorLoader:
    """
    Discovers and registers connector plugins via ``importlib.metadata`` entry_points.
    """

    def __init__(self, logger: Optional[LoggerPort] = None) -> None:
        from pyconnectors.adapters.logging.stdlib import StdlibLoggerAdapter
        self._logger = logger or StdlibLoggerAdapter("pyconnectors.loader")

    def load(self) -> int:
        """
        Discover and register all connectors exposed via entry_points.

        Returns:
            Number of connectors successfully registered.
        """
        eps = entry_points(group=ENTRY_POINT_GROUP)
        count = 0
        for ep in eps:
            try:
                cls = ep.load()
                _default_registry.register(ep.name, cls)
                self._logger.debug("Loaded connector plugin: %s → %s", ep.name, cls.__name__)
                count += 1
            except Exception as exc:
                self._logger.warning(
                    "Failed to load connector plugin '%s': %s", ep.name, exc
                )
        return count

    def load_all(self) -> int:
        """Alias for ``load()``."""
        return self.load()
