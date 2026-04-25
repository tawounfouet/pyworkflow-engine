"""PyConnectors: A universal framework for accessing external services."""

# ── Ports (ABCs) ──────────────────────────────────────────────────────
from pyconnectors.ports.auth_strategy import AuthStrategyPort
from pyconnectors.ports.logger import LoggerPort
from pyconnectors.ports.registry import RegistryPort

# ── Models ────────────────────────────────────────────────────────────
from pyconnectors.models.async_base import AsyncBaseConnector
from pyconnectors.models.base import BaseConnector
from pyconnectors.models.enums import AuthMethod, ConnectorStatus
from pyconnectors.models.exceptions import (
    ConnectorAuthError,
    ConnectorConfigurationError,
    ConnectorConnectionError,
    ConnectorExecutionError,
    ConnectorInactiveError,
    ConnectorNotFoundError,
    ConnectorTimeoutError,
    PyConnectorsError,
)
from pyconnectors.models.lifecycle import ConnectorLifecycle
from pyconnectors.models.result import ConnectorResult
from pyconnectors.models.specs import ConnectSpec, FlowSpec

# ── Config ────────────────────────────────────────────────────────────
from pyconnectors.config.base import ConnectorConfig

# ── Adapters ──────────────────────────────────────────────────────────
from pyconnectors.adapters.auth import build_auth_headers
from pyconnectors.adapters.auth.api_key import ApiKeyAuthAdapter
from pyconnectors.adapters.auth.basic import BasicAuthAdapter
from pyconnectors.adapters.auth.bearer import BearerAuthAdapter
from pyconnectors.adapters.auth.composite import CompositeAuthAdapter
from pyconnectors.adapters.auth.oauth2 import OAuth2AuthAdapter
from pyconnectors.adapters.logging.stdlib import NullLoggerAdapter, StdlibLoggerAdapter
from pyconnectors.adapters.registry.memory import InMemoryRegistryAdapter, connector

# ── Services ──────────────────────────────────────────────────────────
from pyconnectors.services.connector_service import ConnectorService
from pyconnectors.services.factory import ConnectorFactory
from pyconnectors.services.loader import ConnectorLoader

# ── Public API helpers ────────────────────────────────────────────────
from pyconnectors.api import connect, configure, flow, list_types, reset, use

__version__ = "0.4.0"

__all__ = [
    # Ports
    "LoggerPort",
    "RegistryPort",
    "AuthStrategyPort",
    # Models
    "BaseConnector",
    "AsyncBaseConnector",
    "ConnectorResult",
    "ConnectorLifecycle",
    "AuthMethod",
    "ConnectorStatus",
    # Config
    "ConnectorConfig",
    # Services
    "ConnectorFactory",
    "ConnectorService",
    "ConnectorLoader",
    # Adapters — logging
    "StdlibLoggerAdapter",
    "NullLoggerAdapter",
    # Adapters — registry
    "InMemoryRegistryAdapter",
    # Adapters — auth
    "BearerAuthAdapter",
    "ApiKeyAuthAdapter",
    "BasicAuthAdapter",
    "OAuth2AuthAdapter",
    "CompositeAuthAdapter",
    "build_auth_headers",
    # Public API — decorators
    "connector",
    "connect",
    "flow",
    # Public API — specs (introspection)
    "ConnectSpec",
    "FlowSpec",
    # Public API — functional
    "configure",
    "use",
    "reset",
    "list_types",
    # Exceptions
    "PyConnectorsError",
    "ConnectorNotFoundError",
    "ConnectorConfigurationError",
    "ConnectorExecutionError",
    "ConnectorInactiveError",
    "ConnectorConnectionError",
    "ConnectorAuthError",
    "ConnectorTimeoutError",
]
