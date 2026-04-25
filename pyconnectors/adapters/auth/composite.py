"""CompositeAuthAdapter — chain multiple auth strategies."""
from __future__ import annotations

from typing import Any, Dict, List

from pyconnectors.ports.auth_strategy import AuthStrategyPort


class CompositeAuthAdapter(AuthStrategyPort):
    """
    Applies multiple auth strategies in order, merging their headers.

    Later adapters in the chain override keys set by earlier ones.

    Usage::

        auth = CompositeAuthAdapter([
            ApiKeyAuthAdapter(),
            BearerAuthAdapter(),
        ])
        headers = auth.get_headers(config)
    """

    def __init__(self, adapters: List[AuthStrategyPort]) -> None:
        self._adapters = adapters

    def get_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        for adapter in self._adapters:
            headers.update(adapter.get_headers(config))
        return headers
