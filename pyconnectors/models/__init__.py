"""Models — domain objects, stdlib only, zero external dependencies."""

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

__all__ = [
    "BaseConnector",
    "AsyncBaseConnector",
    "ConnectorResult",
    "ConnectorLifecycle",
    "AuthMethod",
    "ConnectorStatus",
    "PyConnectorsError",
    "ConnectorNotFoundError",
    "ConnectorConfigurationError",
    "ConnectorExecutionError",
    "ConnectorInactiveError",
    "ConnectorConnectionError",
    "ConnectorAuthError",
    "ConnectorTimeoutError",
]
