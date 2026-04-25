"""
ConnectorLifecycle — mutable lifecycle entity, separate from ConnectorConfig.

ConnectorConfig is the static configuration (what a connector IS).
ConnectorLifecycle is the runtime state (what a connector HAS DONE).

Separation of concerns:
    config   = identity + credentials + parameters  (stable)
    lifecycle = status + usage + timestamps          (mutable at runtime)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from pyconnectors.models.enums import ConnectorStatus


@dataclass
class ConnectorLifecycle:
    """
    Mutable runtime state for a connector instance.

    Usage::

        lc = ConnectorLifecycle()
        lc.mark_active()
        lc.increment_usage()
        print(lc.status, lc.usage_count)
    """

    status: ConnectorStatus = ConnectorStatus.ACTIVE
    is_active: bool = True
    usage_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    last_error: Optional[str] = None

    # ── Lifecycle transitions ──────────────────────────────────────────

    def mark_active(self) -> None:
        self.status = ConnectorStatus.ACTIVE
        self.is_active = True
        self.last_error = None
        self.updated_at = datetime.now(timezone.utc)

    def mark_inactive(self) -> None:
        self.status = ConnectorStatus.INACTIVE
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)

    def mark_error(self, message: str = "") -> None:
        self.status = ConnectorStatus.ERROR
        self.last_error = message
        self.updated_at = datetime.now(timezone.utc)

    def increment_usage(self) -> None:
        self.usage_count += 1
        self.updated_at = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return (
            f"<ConnectorLifecycle status={self.status.value} "
            f"usage={self.usage_count}>"
        )
