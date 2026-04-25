"""ConnectorConfig — base configuration dataclass for all connectors."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyconnectors.models.enums import AuthMethod, ConnectorStatus


@dataclass
class ConnectorConfig:
    """
    Base configuration for all connectors.

    Supports both a flat ``params`` dict for simple use-cases and explicit
    ``secrets`` / ``auth_method`` fields for structured configurations.
    """

    # Identity
    name: str = ""
    # Extra parameters dynamically loaded
    params: Dict[str, Any] = field(default_factory=dict)
    # Secrets separated from params (never serialized by default)
    secrets: Dict[str, Any] = field(default_factory=dict)
    # Authentication
    auth_method: AuthMethod = AuthMethod.NONE

    # Lifecycle
    status: ConnectorStatus = ConnectorStatus.ACTIVE
    is_active: bool = True
    tags: List[str] = field(default_factory=list)

    # Metadata
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    usage_count: int = 0

    # ── Merged config ──────────────────────────────────────────────────

    def get_merged_config(self) -> Dict[str, Any]:
        """Return ``params`` merged with ``secrets``."""
        merged = dict(self.params)
        merged.update(self.secrets)
        return merged

    # ── Lifecycle helpers ──────────────────────────────────────────────

    def increment_usage(self) -> None:
        self.usage_count += 1
        self.updated_at = datetime.now(timezone.utc)

    def mark_active(self) -> None:
        self.status = ConnectorStatus.ACTIVE
        self.is_active = True
        self.updated_at = datetime.now(timezone.utc)

    def mark_error(self, message: str = "") -> None:  # noqa: ARG002
        self.status = ConnectorStatus.ERROR
        self.updated_at = datetime.now(timezone.utc)

    def mark_inactive(self) -> None:
        self.status = ConnectorStatus.INACTIVE
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)

    # ── Constructors (delegate to loaders) ────────────────────────────

    @classmethod
    def from_dict(cls, data: "Dict[str, Any]") -> "ConnectorConfig":
        from pyconnectors.config.loaders import from_dict
        return from_dict(data, config_cls=cls)

    @classmethod
    def from_json_file(cls, filepath: "Any") -> "ConnectorConfig":
        from pyconnectors.config.loaders import from_json_file
        return from_json_file(filepath, config_cls=cls)

    @classmethod
    def from_yaml_file(cls, filepath: "Any") -> "ConnectorConfig":
        from pyconnectors.config.loaders import from_yaml_file
        return from_yaml_file(filepath, config_cls=cls)

    @classmethod
    def from_env(cls, prefix: str) -> "ConnectorConfig":
        from pyconnectors.config.loaders import from_env
        return from_env(prefix, config_cls=cls)

    # ── Serialization (delegate to serializers) ────────────────────────

    def to_dict(self, include_secrets: bool = False) -> "Dict[str, Any]":
        from pyconnectors.config.serializers import to_dict
        return to_dict(self, include_secrets=include_secrets)

    def to_json(self, path: "Any", include_secrets: bool = False) -> None:
        from pyconnectors.config.serializers import to_json
        to_json(self, path, include_secrets=include_secrets)

    def __str__(self) -> str:
        label = self.name or self.id[:8]
        return f"ConnectorConfig({label})"

    def __repr__(self) -> str:
        label = self.name or self.id[:8]
        return f"<ConnectorConfig name={label!r} status={self.status.value}>"
