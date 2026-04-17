"""
adapters/ai/frameworks/factory — Factory pour créer un BaseAgentRuntime.

Résout le type de runtime vers l'implémentation concrète.
Les frameworks tiers sont lazy-importés pour ne pas casser l'import si
une dépendance optionnelle est absente.

Architecture : ADR-022

Usage::

    from pyworkflow_engine.adapters.ai.frameworks.factory import get_agent_runtime

    runtime = get_agent_runtime(agent, runtime_type="native")
    response = runtime.run("Hello")
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pyworkflow_engine.ports.ai.runtime import BaseAgentRuntime


class RuntimeType(StrEnum):
    """Types de runtime agent disponibles."""

    NATIVE = "native"
    OPENAI_AGENTS = "openai-agents"
    LANGGRAPH = "langgraph"
    AUTOGEN = "autogen"


def get_agent_runtime(
    agent: Any,
    *,
    runtime_type: str | RuntimeType = RuntimeType.NATIVE,
    **kwargs: Any,
) -> BaseAgentRuntime:
    """Factory : crée le runtime agent approprié.

    Args:
        agent: Agent pyworkflow (``models.ai.agent.Agent``).
        runtime_type: ``"native"`` | ``"openai-agents"`` | ``"langgraph"`` | ``"autogen"``.
        **kwargs: Options spécifiques au runtime :
            - ``native``: ``api_key``, ``model``, ``provider_type``, ``verbose``, ``persist``
            - ``openai-agents``: ``tools``, ``handoffs``
            - ``langgraph``: ``client`` (BaseLLMClient), ``enable_checkpointing``, ``extra_nodes``
            - ``autogen``: ⚠️  Utiliser ``AutoGenRuntime.from_pyworkflow_agents()`` directement

    Returns:
        Instance ``BaseAgentRuntime``.

    Raises:
        ImportError: Si le SDK du framework n'est pas installé.
        ValueError: Si le ``runtime_type`` est inconnu ou incompatible.
    """
    rtype = RuntimeType(runtime_type) if isinstance(runtime_type, str) else runtime_type

    if rtype == RuntimeType.NATIVE:
        from agents.shared.runner import AgentRunner  # noqa: PLC0415
        from pyworkflow_engine.adapters.ai.frameworks.native import (  # noqa: PLC0415
            NativeAgentRuntime,
        )

        runner = AgentRunner(agent, **kwargs)
        return NativeAgentRuntime(runner)

    if rtype == RuntimeType.OPENAI_AGENTS:
        from pyworkflow_engine.adapters.ai.frameworks.openai_agents import (  # noqa: PLC0415
            OpenAIAgentsRuntime,
        )

        return OpenAIAgentsRuntime.from_pyworkflow_agent(agent, **kwargs)

    if rtype == RuntimeType.LANGGRAPH:
        from pyworkflow_engine.adapters.ai.frameworks.langgraph import (  # noqa: PLC0415
            LangGraphRuntime,
        )

        return LangGraphRuntime.from_pyworkflow_agent(agent, **kwargs)

    if rtype == RuntimeType.AUTOGEN:
        raise ValueError(
            "AutoGen runtime requires multiple agents. "
            "Use AutoGenRuntime.from_pyworkflow_agents([...]) directly."
        )

    raise ValueError(f"Unknown runtime_type: {runtime_type!r}")
