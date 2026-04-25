"""PyConnectors exception hierarchy — stdlib only, zero external dependencies."""


class PyConnectorsError(Exception):
    """Base exception for all PyConnectors errors."""


class ConnectorNotFoundError(PyConnectorsError, KeyError):
    """Raised when a connector is not found in the registry."""


class ConnectorConfigurationError(PyConnectorsError, ValueError):
    """Raised when there is an issue with connector configuration."""


class ConnectorExecutionError(PyConnectorsError, RuntimeError):
    """Raised when a connector fails to execute."""


class ConnectorInactiveError(PyConnectorsError, ValueError):
    """Raised when attempting to use an inactive connector."""


class ConnectorConnectionError(PyConnectorsError, ConnectionError):
    """Raised when a connection to an external service fails."""


class ConnectorAuthError(PyConnectorsError):
    """Raised when authentication fails."""


class ConnectorTimeoutError(PyConnectorsError, TimeoutError):
    """Raised when a connection or execution times out."""
