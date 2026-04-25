"""ConnectorResult — standardized result envelope for connector execution."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class ConnectorResult:
    """
    Standardized result envelope for connector execution.

    Supports functional-style chaining via ``map()``, ``flat_map()``,
    ``on_error()``, ``unwrap()``, and ``unwrap_or()``.

    Example::

        result = connector.safe_execute(query="SELECT * FROM users")

        # Railway-oriented chaining
        names = (
            result
            .map(lambda rows: [r["name"] for r in rows])
            .on_error(lambda e: logger.error("query failed: %s", e))
            .unwrap_or([])
        )
    """

    success: bool
    data: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── Functional combinators ─────────────────────────────────────────

    def map(self, fn: Callable[[Any], Any]) -> "ConnectorResult":
        """Apply *fn* to ``data`` if successful; passthrough on failure."""
        if not self.success:
            return self
        try:
            return ConnectorResult(
                success=True,
                data=fn(self.data),
                duration=self.duration,
                metadata=self.metadata,
            )
        except Exception as exc:
            return ConnectorResult(
                success=False,
                error=str(exc),
                duration=self.duration,
                metadata={**self.metadata, "exception_type": type(exc).__name__},
            )

    def flat_map(self, fn: Callable[[Any], "ConnectorResult"]) -> "ConnectorResult":
        """Apply *fn* to ``data`` if successful; *fn* must return a ``ConnectorResult``."""
        if not self.success:
            return self
        try:
            return fn(self.data)
        except Exception as exc:
            return ConnectorResult(
                success=False,
                error=str(exc),
                duration=self.duration,
                metadata={**self.metadata, "exception_type": type(exc).__name__},
            )

    def on_error(self, fn: Callable[[str], Any]) -> "ConnectorResult":
        """Call *fn* with the error message if the result is a failure; passthrough otherwise."""
        if not self.success and self.error is not None:
            try:
                fn(self.error)
            except Exception:
                pass
        return self

    def unwrap(self) -> Any:
        """Return ``data`` if successful, otherwise raise ``ValueError``."""
        if not self.success:
            raise ValueError(f"ConnectorResult.unwrap() called on a failure: {self.error!r}")
        return self.data

    def unwrap_or(self, default: Any = None) -> Any:
        """Return ``data`` if successful, otherwise return *default*."""
        return self.data if self.success else default

    def unwrap_or_else(self, fn: Callable[[str], Any]) -> Any:
        """Return ``data`` if successful, otherwise call *fn* with the error."""
        if self.success:
            return self.data
        return fn(self.error or "")

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the result to a plain dictionary."""
        return asdict(self)

    # ── Dunder helpers ─────────────────────────────────────────────────

    def __bool__(self) -> bool:
        """Allow ``if result:`` as a shorthand for ``if result.success:``."""
        return self.success

    def __repr__(self) -> str:
        if self.success:
            return f"ConnectorResult(success=True, data={self.data!r})"
        return f"ConnectorResult(success=False, error={self.error!r})"
