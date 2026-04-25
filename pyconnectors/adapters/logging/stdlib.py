"""
Standard Library logging adapter.

This is the default LoggerPort implementation used by ConnectorFactory
when no custom logger is provided. It delegates entirely to Python's
stdlib logging module — zero opinion, zero overhead.

Usage:
    # Default (auto-named logger)
    factory = ConnectorFactory()  # uses StdlibLoggerAdapter("pyconnectors")

    # Custom logger name
    factory = ConnectorFactory(logger=StdlibLoggerAdapter("myapp.connectors"))

    # Bring your own (structlog, loguru, etc.)
    factory = ConnectorFactory(logger=MyStructlogAdapter())
"""
from __future__ import annotations

import logging
from typing import Any

from pyconnectors.ports.logger import LoggerPort


class StdlibLoggerAdapter(LoggerPort):
    """
    LoggerPort implementation wrapping Python's stdlib logging.

    This is the default. Zero configuration required. The application
    controls log levels, handlers, and formatters through its own
    logging setup — PyConnectors never touches basicConfig().
    """

    def __init__(self, name: str = "pyconnectors") -> None:
        self._logger = logging.getLogger(name)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.exception(message, *args, **kwargs)


class NullLoggerAdapter(LoggerPort):
    """
    No-op LoggerPort — discards all log messages.

    Useful for:
    - Unit tests (suppress noise)
    - Lambda/serverless environments where logging is external
    - Performance-critical paths

    Example (pytest conftest.py):
        @pytest.fixture
        def factory():
            return ConnectorFactory(logger=NullLoggerAdapter())
    """

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None: ...
    def info(self, message: str, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, message: str, *args: Any, **kwargs: Any) -> None: ...
    def error(self, message: str, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, message: str, *args: Any, **kwargs: Any) -> None: ...
