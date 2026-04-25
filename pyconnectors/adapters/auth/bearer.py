"""BearerAuthAdapter — Bearer token authentication."""
from __future__ import annotations

from typing import Any, Dict

from pyconnectors.ports.auth_strategy import AuthStrategyPort


class BearerAuthAdapter(AuthStrategyPort):
    """Injects ``Authorization: Bearer <token>`` into request headers."""

    def get_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        token = config.get("bearer_token") or config.get("access_token", "")
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}
