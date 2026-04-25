"""AsyncBaseConnector — abstract base class for all asynchronous connectors."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Tuple

from pyconnectors.models.result import ConnectorResult


class AsyncBaseConnector(ABC):
    """
    Abstract base class for async connectors.

    Mirror of BaseConnector with async execute / safe_execute.
    Connectors that integrate async I/O libraries (aiohttp, asyncpg, etc.)
    should subclass this instead of BaseConnector.
    """

    def __init__(self, config: Any) -> None:
        if isinstance(config, dict):
            from pyconnectors.config import ConnectorConfig
            config = ConnectorConfig.from_dict(config)
        self.config = config
        self._hooks: Dict[str, List[Callable[..., Any]]] = {
            "pre_execute": [],
            "post_execute": [],
            "on_error": [],
        }

    # ── Hooks ──────────────────────────────────────────────────────────

    def add_hook(self, event: str, hook: Callable[..., Any]) -> None:
        if event not in self._hooks:
            raise ValueError(f"Invalid hook event: {event}")
        self._hooks[event].append(hook)

    async def _trigger_hooks_async(self, event: str, *args: Any, **kwargs: Any) -> None:
        import asyncio
        for hook in self._hooks[event]:
            try:
                result = hook(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    # ── Abstract interface ─────────────────────────────────────────────

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Core async connector logic to be implemented by child classes."""
        ...

    async def test_connection(self) -> Tuple[bool, str]:
        """Test the connection. Override with a lightweight health-check."""
        result = await self.safe_execute()
        if result.success:
            return True, "Connection OK"
        return False, result.error or "Unknown error"

    # ── Safe async execution ───────────────────────────────────────────

    async def safe_execute(self, *args: Any, **kwargs: Any) -> ConnectorResult:
        """Execute the connector safely, capturing timing and exceptions."""
        start_time = time.perf_counter()
        await self._trigger_hooks_async("pre_execute", self, *args, **kwargs)

        try:
            result_data = await self.execute(*args, **kwargs)
            duration = time.perf_counter() - start_time
            result = ConnectorResult(success=True, data=result_data, duration=duration)
            await self._trigger_hooks_async("post_execute", self, result, *args, **kwargs)
            return result
        except Exception as e:
            duration = time.perf_counter() - start_time
            result = ConnectorResult(
                success=False,
                error=str(e),
                duration=duration,
                metadata={"exception_type": type(e).__name__},
            )
            await self._trigger_hooks_async("on_error", self, result, *args, **kwargs)
            return result

    # ── Auth helpers ───────────────────────────────────────────────────

    def get_auth_headers(self) -> Dict[str, str]:
        from pyconnectors.adapters.auth import build_auth_headers
        return build_auth_headers(
            auth_method=self.config.auth_method,
            config=self.config.get_merged_config(),
        )

    def get_merged_config(self) -> Dict[str, Any]:
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
