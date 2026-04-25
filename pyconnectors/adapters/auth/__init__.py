"""Auth adapters — concrete AuthStrategyPort implementations."""
from __future__ import annotations

from typing import Any, Dict

from pyconnectors.adapters.auth.api_key import ApiKeyAuthAdapter
from pyconnectors.adapters.auth.basic import BasicAuthAdapter
from pyconnectors.adapters.auth.bearer import BearerAuthAdapter
from pyconnectors.adapters.auth.composite import CompositeAuthAdapter
from pyconnectors.adapters.auth.oauth2 import OAuth2AuthAdapter
from pyconnectors.models.enums import AuthMethod

__all__ = [
    "BearerAuthAdapter",
    "ApiKeyAuthAdapter",
    "BasicAuthAdapter",
    "OAuth2AuthAdapter",
    "CompositeAuthAdapter",
    "build_auth_headers",
]


def build_auth_headers(
    auth_method: str | AuthMethod,
    config: Dict[str, Any],
) -> Dict[str, str]:
    """
    Build HTTP authentication headers from a merged config dict.

    Dispatches to the appropriate auth adapter based on ``auth_method``.

    Args:
        auth_method: AuthMethod enum or string ("bearer", "api_key", etc.).
        config: Merged configuration dict (params + secrets).

    Returns:
        Dict of HTTP header name → value.

    Examples::

        build_auth_headers("bearer", {"bearer_token": "abc123"})
        # → {'Authorization': 'Bearer abc123'}

        build_auth_headers("api_key", {"api_key": "k", "api_key_header": "X-Token"})
        # → {'X-Token': 'k'}
    """
    auth = AuthMethod(auth_method) if isinstance(auth_method, str) else auth_method

    _adapters = {
        AuthMethod.BEARER: BearerAuthAdapter(),
        AuthMethod.API_KEY: ApiKeyAuthAdapter(),
        AuthMethod.BASIC: BasicAuthAdapter(),
        AuthMethod.OAUTH2: OAuth2AuthAdapter(),
    }

    adapter = _adapters.get(auth)
    if adapter is None:
        return {}
    return adapter.get_headers(config)
