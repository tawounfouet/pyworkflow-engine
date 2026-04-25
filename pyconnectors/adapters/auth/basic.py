"""BasicAuthAdapter — HTTP Basic authentication."""
from __future__ import annotations

import base64
from typing import Any, Dict

from pyconnectors.ports.auth_strategy import AuthStrategyPort


class BasicAuthAdapter(AuthStrategyPort):
    """Injects ``Authorization: Basic <base64(user:pass)>`` into request headers."""

    def get_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        username = config.get("username", "")
        password = config.get("password", "")
        if username:
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}
