"""Domain enums — stdlib only, zero external dependencies."""
from __future__ import annotations

from enum import Enum


class AuthMethod(str, Enum):
    """Supported authentication methods."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    CUSTOM = "custom"


class ConnectorStatus(str, Enum):
    """Connector lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
