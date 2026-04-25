"""
api.py — PyConnectors public façade.

Provides decorator-based and functional APIs for common operations:

    @connector("my.service")
    class MyConnector(BaseConnector): ...

    @connect("my.service")
    def my_operation(connector, **kwargs): ...

    use("my.service", config)          # execute
    configure("my.service", config)    # register a pre-built config
    reset()                            # clear the default registry
    list_types()                       # list registered connector names

ADR-002 §5 — original Decorator API.
ADR-004    — TaskFlow decorators (@connect on functions, @flow).
"""
from __future__ import annotations

import time
import warnings
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type

from pyconnectors.adapters.registry.memory import _default_registry
from pyconnectors.config.base import ConnectorConfig
from pyconnectors.models.base import BaseConnector
from pyconnectors.models.result import ConnectorResult
from pyconnectors.models.specs import ConnectSpec, FlowSpec
from pyconnectors.adapters.registry.memory import connector  # re-export

__all__ = [
    "connector",
    "connect",
    "flow",
    "use",
    "configure",
    "reset",
    "list_types",
    "ConnectSpec",
    "FlowSpec",
]

# ── Module-level config store ──────────────────────────────────────────

_configs: Dict[str, ConnectorConfig] = {}


# ── Decorators ─────────────────────────────────────────────────────────


def connect(
    connector_type: str,
    config: Optional[ConnectorConfig | Dict[str, Any]] = None,
    *,
    name: Optional[str] = None,
    tags: frozenset[str] = frozenset(),
) -> Callable:
    """
    Dual-purpose decorator — handles both **classes** and **functions**.

    On a **class** (legacy, deprecated since v0.4.0)::

        @connect("myapp.service")
        class MyConnector(BaseConnector):
            def execute(self, **kwargs): ...

    On a **function** (TaskFlow API — ADR-004)::

        @connect("http.rest")
        def fetch_users(connector, org="octocat"):
            return connector.execute(method="GET", url=f"/users/{org}/repos")

        result = fetch_users(org="python")   # → ConnectorResult

    The decorated function receives a **live connector instance** as its first
    argument.  Config resolution order:

    1. ``_config=`` keyword at call-time (highest priority)
    2. ``config=`` passed to the decorator
    3. Pre-registered config via ``configure()``
    """

    def decorator(obj: Any) -> Any:
        # ── Class branch (legacy @connect → alias of @connector) ───────
        if isinstance(obj, type):
            warnings.warn(
                f"@connect on class {obj.__name__!r} is deprecated since v0.4.0. "
                f"Use @connector({connector_type!r}) instead. "
                f"@connect on classes will be removed in v1.0.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            return connector(connector_type)(obj)

        # ── Function branch (TaskFlow — ADR-004) ──────────────────────
        if not callable(obj):
            raise TypeError(
                f"@connect({connector_type!r}) can only decorate a class or a callable, "
                f"got {type(obj).__name__!r}."
            )

        spec = ConnectSpec(
            connector_type=connector_type,
            name=name or obj.__name__,
            config=dict(config) if isinstance(config, dict) else None,
            tags=frozenset(tags),
        )

        @wraps(obj)
        def wrapper(
            *args: Any,
            _config: Optional[ConnectorConfig | Dict[str, Any]] = None,
            **kwargs: Any,
        ) -> ConnectorResult:
            from pyconnectors.services.factory import ConnectorFactory

            # 1. Resolve config: call-time → decorator → pre-registered
            resolved = _config or config
            if resolved is None:
                if connector_type in _configs:
                    resolved = _configs[connector_type]
                else:
                    raise KeyError(
                        f"No config for '{connector_type}'. "
                        f"Call configure('{connector_type}', config) first, "
                        f"pass config= to @connect(), or use _config= at call-time."
                    )

            if isinstance(resolved, dict):
                resolved = ConnectorConfig.from_dict(resolved)

            # 2. Instantiate connector
            instance = ConnectorFactory.create(connector_type, config=resolved)

            # 3. Call the user function — connector injected as 1st arg
            start = time.perf_counter()
            try:
                result = obj(instance, *args, **kwargs)
                duration = time.perf_counter() - start

                # 4. Wrap raw returns in ConnectorResult
                if isinstance(result, ConnectorResult):
                    return result
                return ConnectorResult(success=True, data=result, duration=duration)
            except Exception as exc:
                duration = time.perf_counter() - start
                return ConnectorResult(
                    success=False,
                    error=str(exc),
                    duration=duration,
                    metadata={"exception_type": type(exc).__name__},
                )

        # Attach metadata for introspection
        wrapper.__connect_spec__ = spec  # type: ignore[attr-defined]
        wrapper._is_pyconnector_connect = True  # type: ignore[attr-defined]
        wrapper._connector_type = connector_type  # type: ignore[attr-defined]

        return wrapper

    return decorator


def flow(
    name: Optional[str] = None,
    *,
    connects: Optional[List[Callable]] = None,
    tags: frozenset[str] = frozenset(),
    description: str = "",
) -> Callable:
    """
    Compose ``@connect``-decorated functions into a named flow.

    The decorated function is wrapped so that:

    * Its return value is always a ``ConnectorResult``.
    * Exceptions are captured into a failed ``ConnectorResult``.
    * Total duration is measured.
    * ``@connect`` functions used inside are detected via ``co_names``
      (implicit mode) or the explicit ``connects=`` argument.

    Usage::

        @flow(name="github-to-sqlite")
        def sync_github():
            repos = fetch_repos(org="octocat")
            if repos.success:
                return save_repos(repos=repos.data)
            return repos

        result = sync_github()

    ADR-004 §5.
    """

    def decorator(fn: Callable) -> Callable:
        flow_name = name or fn.__name__

        # ── Detect @connect functions referenced in the body ───────────
        if connects is not None:
            connect_names = tuple(
                getattr(
                    c,
                    "__connect_spec__",
                    ConnectSpec(connector_type="?", name=c.__name__),
                ).name
                for c in connects
            )
        else:
            # Implicit mode: inspect co_names from the function's code object
            connect_names = _detect_connects(fn)

        spec = FlowSpec(
            name=flow_name,
            connects=connect_names,
            description=description or fn.__doc__ or "",
            tags=frozenset(tags),
        )

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> ConnectorResult:
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                duration = time.perf_counter() - start

                if isinstance(result, ConnectorResult):
                    # Preserve the inner result but update total duration
                    return ConnectorResult(
                        success=result.success,
                        data=result.data,
                        error=result.error,
                        duration=duration,
                        metadata={**result.metadata, "flow": flow_name},
                    )
                return ConnectorResult(
                    success=True,
                    data=result,
                    duration=duration,
                    metadata={"flow": flow_name},
                )
            except Exception as exc:
                duration = time.perf_counter() - start
                return ConnectorResult(
                    success=False,
                    error=str(exc),
                    duration=duration,
                    metadata={
                        "exception_type": type(exc).__name__,
                        "flow": flow_name,
                    },
                )

        # Attach metadata for introspection
        wrapper.__flow_spec__ = spec  # type: ignore[attr-defined]
        wrapper._is_pyconnector_flow = True  # type: ignore[attr-defined]

        return wrapper

    return decorator


def _detect_connects(fn: Callable) -> tuple[str, ...]:
    """
    Detect ``@connect``-decorated functions referenced in *fn*'s code body.

    Uses ``co_names`` from the function's code object (implicit mode),
    then checks ``fn.__globals__`` for functions that carry ``__connect_spec__``.

    Same pattern as pyworkflow-engine's ``_detect_steps()``.
    """
    code = getattr(fn, "__code__", None)
    if code is None:
        return ()

    fn_globals = getattr(fn, "__globals__", {})
    names: list[str] = []

    for ref_name in code.co_names:
        obj = fn_globals.get(ref_name)
        if obj is not None and getattr(obj, "_is_pyconnector_connect", False):
            spec: ConnectSpec = obj.__connect_spec__
            names.append(spec.name)

    return tuple(names)


# ── Functional API ─────────────────────────────────────────────────────


def configure(name: str, config: ConnectorConfig | Dict[str, Any]) -> None:
    """
    Pre-register a configuration for a connector name.

    Subsequent calls to ``use(name)`` will use this config unless overridden.
    """
    if isinstance(config, dict):
        config = ConnectorConfig.from_dict(config)
    _configs[name] = config


def use(
    name: str,
    config: Optional[ConnectorConfig | Dict[str, Any]] = None,
    **kwargs: Any,
) -> ConnectorResult:
    """
    Execute a connector by name.

    Uses the pre-registered config (via ``configure()``) if none is provided.

    Usage::

        configure("db.pg", {"host": "localhost", "port": 5432})
        result = use("db.pg", query="SELECT 1")
    """
    from pyconnectors.services.factory import ConnectorFactory

    if config is None:
        if name not in _configs:
            raise KeyError(
                f"No config registered for '{name}'. "
                f"Call configure('{name}', config) first, or pass config directly."
            )
        config = _configs[name]

    factory = ConnectorFactory()
    return factory.execute(name, config, **kwargs)


def reset() -> None:
    """Clear the default registry and all pre-registered configs."""
    _default_registry.clear()
    _configs.clear()


def list_types() -> list:
    """Return sorted list of all registered connector names."""
    return _default_registry.list_names()
