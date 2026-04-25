"""OAuth2AuthAdapter — OAuth2 Bearer token authentication."""
from __future__ import annotations

from typing import Any, Dict

from pyconnectors.ports.auth_strategy import AuthStrategyPort


class OAuth2AuthAdapter(AuthStrategyPort):
    """
    Injects ``Authorization: Bearer <access_token>`` for OAuth2 flows.

    Expects ``access_token`` in the config (already obtained via the
    OAuth2 flow — token refresh is the caller's responsibility).
    """

    def get_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        token = config.get("access_token", "")
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}
