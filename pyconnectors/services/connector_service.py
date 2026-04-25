"""
ConnectorService — high-level orchestration layer.

Wraps ConnectorFactory with lifecycle management, structured logging,
and a clean API for application-layer use.

    service = ConnectorService(ConnectorFactory())
    result = service.execute("db.pg", config)
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from pyconnectors.adapters.logging.stdlib import StdlibLoggerAdapter
from pyconnectors.config.base import ConnectorConfig
from pyconnectors.models.result import ConnectorResult
from pyconnectors.ports.logger import LoggerPort
from pyconnectors.services.factory import ConnectorFactory


class ConnectorService:
    """
    Orchestration service for connector lifecycle.

    Provides a unified entry point for executing and testing connectors,
    with dependency-injected logging.

    Usage::

        factory = ConnectorFactory()
        service = ConnectorService(factory)
        result = service.execute("http.rest", config, endpoint="/users")
    """

    def __init__(
        self,
        factory: ConnectorFactory,
        logger: Optional[LoggerPort] = None,
    ) -> None:
        self._factory = factory
        self._logger = logger or StdlibLoggerAdapter("pyconnectors")

    def execute(
        self,
        name: str,
        config: ConnectorConfig | Dict[str, Any],
        **kwargs: Any,
    ) -> ConnectorResult:
        """Execute a connector by name and return the result."""
        self._logger.debug("ConnectorService.execute: %s", name)
        return self._factory.execute(name, config, **kwargs)

    def test(
        self,
        name: str,
        config: ConnectorConfig | Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Test a connector's connectivity."""
        self._logger.debug("ConnectorService.test: %s", name)
        return self._factory.test_connector(name, config)

    def list_types(self) -> list:
        """List all registered connector names."""
        return self._factory.list_types()

    def is_registered(self, name: str) -> bool:
        return self._factory.is_registered(name)
