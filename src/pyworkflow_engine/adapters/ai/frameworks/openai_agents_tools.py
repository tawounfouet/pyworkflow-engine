"""
adapters/ai/frameworks/openai_agents_tools — Bridge BaseTool → function_tool.

Convertit les ``BaseTool`` pyworkflow en ``@function_tool`` de l'OpenAI
Agents SDK, pour les passer en ``tools=`` à ``OpenAIAgentsRuntime``.

Requiert : ``pip install openai-agents``

Architecture : ADR-022

Usage::

    from pyworkflow_engine.adapters.ai.frameworks.openai_agents_tools import (
        bridge_tool,
        bridge_all_tools,
    )
    from my_tools import calculator_tool, search_tool

    oai_tools = bridge_all_tools([calculator_tool, search_tool])
    runtime = OpenAIAgentsRuntime.from_pyworkflow_agent(agent, tools=oai_tools)
"""

from __future__ import annotations

from typing import Any

try:
    from agents import function_tool
except ImportError as exc:
    raise ImportError(
        "Tool bridge requires 'openai-agents'. "
        "Install with: pip install openai-agents"
    ) from exc

from pyworkflow_engine.ports.ai.tool import BaseTool


def bridge_tool(pw_tool: BaseTool) -> Any:
    """Convertit un ``BaseTool`` pyworkflow en ``@function_tool`` OpenAI SDK.

    Le schéma ``parameters_schema`` est réutilisé tel quel car il est
    déjà au format OpenAI function-calling.

    Args:
        pw_tool: Instance ``BaseTool`` du registre pyworkflow.

    Returns:
        Objet function_tool compatible OpenAI Agents SDK.
    """

    @function_tool(
        name_override=pw_tool.key,
        description_override=pw_tool.description,
    )
    def _wrapped(**kwargs: Any) -> Any:
        return pw_tool.run(**kwargs)

    return _wrapped


def bridge_all_tools(tools: list[BaseTool]) -> list[Any]:
    """Convertit une liste de ``BaseTool`` → liste de function_tool.

    Args:
        tools: Instances ``BaseTool`` du registre pyworkflow.

    Returns:
        Liste d'objets function_tool compatibles OpenAI Agents SDK.
    """
    return [bridge_tool(t) for t in tools]
