"""
Adapters — concrete implementations of PyConnectors ports.

Hexagonal Architecture: ports/ defines the contracts, adapters/ implements them.

Public surface:
    InMemoryRegistryAdapter   — default thread-safe registry
    StdlibLoggerAdapter       — default logger (delegates to stdlib logging)
    NullLoggerAdapter         — no-op logger for tests / silent environments
    BearerAuthAdapter         — Bearer token auth
    ApiKeyAuthAdapter         — API key auth
    BasicAuthAdapter          — HTTP Basic auth
    OAuth2AuthAdapter         — OAuth2 Bearer auth
    CompositeAuthAdapter      — chain of auth strategies
"""

from pyconnectors.adapters.auth.api_key import ApiKeyAuthAdapter
from pyconnectors.adapters.auth.basic import BasicAuthAdapter
from pyconnectors.adapters.auth.bearer import BearerAuthAdapter
from pyconnectors.adapters.auth.composite import CompositeAuthAdapter
from pyconnectors.adapters.auth.oauth2 import OAuth2AuthAdapter
from pyconnectors.adapters.logging.stdlib import NullLoggerAdapter, StdlibLoggerAdapter
from pyconnectors.adapters.registry.memory import InMemoryRegistryAdapter

__all__ = [
    "InMemoryRegistryAdapter",
    "StdlibLoggerAdapter",
    "NullLoggerAdapter",
    "BearerAuthAdapter",
    "ApiKeyAuthAdapter",
    "BasicAuthAdapter",
    "OAuth2AuthAdapter",
    "CompositeAuthAdapter",
]
