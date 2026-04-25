"""
Frozen dataclasses for decorator metadata — ``ConnectSpec`` and ``FlowSpec``.

These specs are attached to decorated functions via ``__connect_spec__``
and ``__flow_spec__`` attributes, following the same pattern as
``StepSpec`` / ``JobBuilder`` in pyworkflow-engine.

ADR-004 §7.1 / §7.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional


@dataclass(frozen=True)
class ConnectSpec:
    """
    Metadata for a ``@connect``-decorated function.

    Stored as ``fn.__connect_spec__`` by the ``@connect`` decorator.

    Attributes:
        connector_type: Registry key, e.g. ``"http.rest"``, ``"database.sqlite"``.
        name:           Human-readable name (defaults to the function name).
        config:         Optional config dict frozen at decoration time.
        tags:           Arbitrary tags for filtering / introspection.
    """

    connector_type: str
    name: str
    config: Optional[Dict[str, Any]] = None
    tags: FrozenSet[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class FlowSpec:
    """
    Metadata for a ``@flow``-decorated function.

    Stored as ``fn.__flow_spec__`` by the ``@flow`` decorator (v0.5.0).

    Attributes:
        name:        Human-readable name for the flow.
        connects:    Tuple of ``@connect`` function names detected in the flow body.
        description: Optional description.
        tags:        Arbitrary tags for filtering / introspection.
    """

    name: str
    connects: tuple[str, ...] = ()
    description: str = ""
    tags: FrozenSet[str] = field(default_factory=frozenset)
