"""ApiKeyAuthAdapter — API key authentication."""
from __future__ import annotations

from typing import Any, Dict

from pyconnectors.ports.auth_strategy import AuthStrategyPort


class ApiKeyAuthAdapter(AuthStrategyPort):
    """
    Injects an API key header into request headers.

    The header name defaults to ``X-API-Key`` but can be overridden via
    ``api_key_header`` in the config.
    """

    def get_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        api_key = config.get("api_key", "")
        header_name = config.get("api_key_header", "X-API-Key")
        if api_key:
            return {header_name: api_key}
        return {}
