"""BaseConnector — abstract base class for all synchronous connectors."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Tuple

from pyconnectors.models.result import ConnectorResult


class BaseConnector(ABC):
    """
    Abstract base class for all connectors.

    Provides hooks, safe execution with ``ConnectorResult``, centralized
    auth header generation, and an optional ``test_connection`` contract.
    """

    def __init__(self, config: Any) -> None:
        # Accept ConnectorConfig or dict; deferred import avoids circular deps
        if isinstance(config, dict):
            from pyconnectors.config import ConnectorConfig
            config = ConnectorConfig.from_dict(config)
        self.config = config
        self._hooks: Dict[str, List[Callable[..., Any]]] = {
            "pre_execute": [],
            "post_execute": [],
            "on_error": [],
        }

    # ── Hooks / Middleware ──────────────────────────────────────────────

    def add_hook(self, event: str, hook: Callable[..., Any]) -> None:
        """Register a hook to execute on specific events."""
        if event not in self._hooks:
            raise ValueError(f"Invalid hook event: {event}")
        self._hooks[event].append(hook)

    def _trigger_hooks(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Trigger registered hooks for the specified event."""
        for hook in self._hooks[event]:
            try:
                hook(*args, **kwargs)
            except Exception:
                pass

    # ── Abstract interface ─────────────────────────────────────────────

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Core connector logic to be implemented by child classes."""
        ...

    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the connection with the current configuration.

        Returns a ``(success, message)`` tuple.  The default implementation
        delegates to ``safe_execute`` with no arguments; subclasses should
        override this with a lightweight health-check.
        """
        result = self.safe_execute()
        if result.success:
            return True, "Connection OK"
        return False, result.error or "Unknown error"

    # ── Safe execution ─────────────────────────────────────────────────

    def safe_execute(self, *args: Any, **kwargs: Any) -> ConnectorResult:
        """
        Execute the connector safely, capturing timing and exceptions.
        Also triggers pre/post/on_error hooks.
        """
        start_time = time.perf_counter()
        self._trigger_hooks("pre_execute", self, *args, **kwargs)

        try:
            result_data = self.execute(*args, **kwargs)
            duration = time.perf_counter() - start_time
            result = ConnectorResult(success=True, data=result_data, duration=duration)
            self._trigger_hooks("post_execute", self, result, *args, **kwargs)
            return result
        except Exception as e:
            duration = time.perf_counter() - start_time
            result = ConnectorResult(
                success=False,
                error=str(e),
                duration=duration,
                metadata={"exception_type": type(e).__name__},
            )
            self._trigger_hooks("on_error", self, result, *args, **kwargs)
            return result

    # ── Auth helpers ───────────────────────────────────────────────────

    def get_auth_headers(self) -> Dict[str, str]:
        """Build HTTP auth headers from the connector's configuration."""
        from pyconnectors.adapters.auth import build_auth_headers
        return build_auth_headers(
            auth_method=self.config.auth_method,
            config=self.config.get_merged_config(),
        )

    def get_merged_config(self) -> Dict[str, Any]:
        """Shortcut to ``self.config.get_merged_config()``."""
        return self.config.get_merged_config()

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_active(self) -> bool:
        return self.config.is_active

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name or '?'})"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
