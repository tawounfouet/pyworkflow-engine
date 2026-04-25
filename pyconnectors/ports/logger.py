"""
LoggerPort — minimal logging contract for PyConnectors.

A library should never configure logging beyond providing a NullHandler.
This port exists solely to:
  1. Enable dependency injection in ConnectorFactory / ConnectorService (testability)
  2. Allow power users to plug in their own logger implementation
  3. Provide a stdlib adapter that delegates to Python's logging module

DO NOT add methods specific to connector domain logic (log_execution,
log_test, etc.) — those belong to the application layer, not the library.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LoggerPort(ABC):
    """
    Minimal logging contract.

    Implementations: StdlibLoggerAdapter, NullLoggerAdapter.

    Usage in ConnectorFactory:
        factory = ConnectorFactory(logger=StdlibLoggerAdapter("myapp"))
    """

    @abstractmethod
    def debug(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    @abstractmethod
    def info(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    @abstractmethod
    def warning(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    @abstractmethod
    def error(self, message: str, *args: Any, **kwargs: Any) -> None: ...

    @abstractmethod
    def exception(self, message: str, *args: Any, **kwargs: Any) -> None: ...
