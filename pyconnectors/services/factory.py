"""
services/factory.py — ConnectorFactory (creation pure, sans side-effects).

This is the canonical location post-ADR-003.
pyconnectors/factory.py re-exports from here for backward compatibility.
"""
from __future__ import annotations

import importlib
import time
from typing import Any, Dict, List, Optional, Tuple, Type, cast

from pyconnectors.adapters.logging.stdlib import StdlibLoggerAdapter
from pyconnectors.adapters.registry.memory import _default_registry
from pyconnectors.config.base import ConnectorConfig
from pyconnectors.models.base import BaseConnector
from pyconnectors.models.exceptions import ConnectorConfigurationError, ConnectorInactiveError
from pyconnectors.models.result import ConnectorResult
from pyconnectors.ports.logger import LoggerPort

# ── Auto-loading built-in connectors ───────────────────────────────────

_builtins_loaded = False

_BUILTIN_MODULES = [
    "pyconnectors.connectors.http",
    "pyconnectors.connectors.database",
    "pyconnectors.connectors.email",
    "pyconnectors.connectors.storage",
    "pyconnectors.connectors.social",
    "pyconnectors.connectors.payment",
    "pyconnectors.connectors.auth",
    "pyconnectors.connectors.fitness",
    "pyconnectors.connectors.messaging",
]


def _ensure_builtins_loaded(logger: LoggerPort) -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    for mod_name in _BUILTIN_MODULES:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            logger.debug(
                "Built-in connector module '%s' not available (optional dependency).",
                mod_name,
            )
        except Exception:
            logger.exception("Error loading connector module '%s'.", mod_name)


# ── Factory ────────────────────────────────────────────────────────────


class ConnectorFactory:
    """
    Factory for creating, executing, and testing connectors.

    Can be used as a **class** (``ConnectorFactory.create(…)``) for simple
    cases, or as an **instance** (``factory = ConnectorFactory(logger=…)``)
    when you need logging and convenience shortcuts.
    """

    def __init__(
        self,
        logger: Optional[LoggerPort] = None,
        auto_load_builtins: bool = True,
    ) -> None:
        self._logger = logger or StdlibLoggerAdapter("pyconnectors")
        if auto_load_builtins:
            _ensure_builtins_loaded(self._logger)

    # ── Class-level (stateless) API ────────────────────────────────────

    @classmethod
    def create(
        cls,
        name: str,
        config: Optional[ConnectorConfig] = None,
        config_dict: Optional[Dict[str, Any]] = None,
        config_cls: Optional[Type[ConnectorConfig]] = None,
    ) -> BaseConnector:
        """Create a connector by name from the registry."""
        _ensure_builtins_loaded(StdlibLoggerAdapter("pyconnectors"))
        connector_cls = cast(Type[BaseConnector], _default_registry.get(name))

        if config is None:
            if config_dict is None:
                config_dict = {}
            if config_cls is None:
                config_cls = ConnectorConfig
            try:
                config = config_cls.from_dict(config_dict)
            except Exception as e:
                raise ConnectorConfigurationError(f"Failed to load connector config: {e}")

        return connector_cls(config)

    # ── Instance-level (stateful) API ──────────────────────────────────

    def get_connector(self, config: ConnectorConfig | Dict[str, Any]) -> BaseConnector:
        """Instantiate a connector from a config."""
        if isinstance(config, dict):
            config = ConnectorConfig.from_dict(config)

        if not config.is_active:
            raise ConnectorInactiveError(f"Connector '{config.name}' is inactive")

        connector_name = config.params.get("connector_type") or config.name
        connector_cls = cast(Type[BaseConnector], _default_registry.get(connector_name))
        return connector_cls(config)

    def execute(
        self, name: str, config: ConnectorConfig | Dict[str, Any], **kwargs: Any
    ) -> ConnectorResult:
        """Shortcut: instantiate → safe_execute → log → return result."""
        if isinstance(config, dict):
            config = ConnectorConfig.from_dict(config)

        conn = self.create(name, config=config)
        start = time.perf_counter()
        result = conn.safe_execute(**kwargs)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        if result.success:
            self._logger.info(
                "Connector '%s' executed in %dms", config.name or name, elapsed_ms
            )
        else:
            self._logger.error(
                "Connector '%s' failed in %dms: %s",
                config.name or name,
                elapsed_ms,
                result.error,
            )

        config.increment_usage()
        return result

    def test_connector(
        self, name: str, config: ConnectorConfig | Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Test a connector's connectivity. Returns ``(success, message)``."""
        if isinstance(config, dict):
            config = ConnectorConfig.from_dict(config)

        conn = self.create(name, config=config)
        start = time.perf_counter()
        try:
            success, message = conn.test_connection()
        except Exception as e:
            success, message = False, f"Exception: {e}"
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        if success:
            self._logger.info(
                "Connector '%s' tested OK in %dms", config.name or name, elapsed_ms
            )
            config.mark_active()
        else:
            self._logger.warning(
                "Connector '%s' test failed in %dms: %s",
                config.name or name,
                elapsed_ms,
                message,
            )
            config.mark_error(message)

        return success, message

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def list_types() -> List[str]:
        """List all registered connector names."""
        return _default_registry.list_names()

    @staticmethod
    def is_registered(name: str) -> bool:
        return _default_registry.is_registered(name)
