"""AuthStrategyPort — contract for authentication adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class AuthStrategyPort(ABC):
    """
    Port for HTTP authentication strategies.

    Each implementation produces the HTTP headers required by one
    authentication scheme (Bearer, API Key, Basic, OAuth2, …).

    Usage::

        class MyService:
            def __init__(self, auth: AuthStrategyPort) -> None:
                self._auth = auth

            def call(self, config: dict) -> dict:
                headers = self._auth.get_headers(config)
                ...
    """

    @abstractmethod
    def get_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        """
        Build and return HTTP authentication headers.

        Args:
            config: Merged configuration dict (params + secrets).

        Returns:
            Dict of HTTP header name → value.
        """
        ...
