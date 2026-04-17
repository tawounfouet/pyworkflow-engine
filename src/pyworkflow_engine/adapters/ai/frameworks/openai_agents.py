"""
adapters/ai/frameworks/openai_agents — Runtime OpenAI Agents SDK.

Requiert : ``pip install openai-agents``

Encapsule l'OpenAI Agents SDK derrière le port ``BaseAgentRuntime``.
Convertit les agents pyworkflow → OAI Agent, exécute via Runner.run(),
et normalise la réponse en ``AgentResponse``.

Architecture : ADR-022

Usage::

    from pyworkflow_engine.adapters.ai.frameworks.openai_agents import (
        OpenAIAgentsRuntime,
    )

    runtime = OpenAIAgentsRuntime.from_pyworkflow_agent(my_agent, tools=[...])
    response = await runtime.arun("Analyse ce fichier")
    print(response.content)
    print(response.handoff_target)  # slug si handoff a eu lieu
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pyworkflow_engine.ports.ai.runtime import AgentResponse, BaseAgentRuntime

try:
    from agents import Agent as OAIAgent
    from agents import Runner as OAIRunner
except ImportError as exc:
    raise ImportError(
        "OpenAI Agents SDK adapter requires 'openai-agents'. "
        "Install with: pip install openai-agents"
    ) from exc


class OpenAIAgentsRuntime(BaseAgentRuntime):
    """Runtime qui délègue à l'OpenAI Agents SDK.

    L'agent pyworkflow est converti en ``agents.Agent`` du SDK OpenAI.
    L'exécution passe par ``Runner.run()`` qui gère le tool-calling loop
    et les handoffs nativement.

    Limitations :
      - OpenAI-only (pas de multi-provider)
      - Les appels LLM passent par le SDK, pas par ``BaseLLMClient``
      - La persistence par-message n'est pas intégrée (seul ``AgentResponse``
        est retourné — le caller doit persister)
    """

    def __init__(
        self,
        oai_agent: OAIAgent,
        *,
        slug: str = "",
        model_name: str = "",
    ) -> None:
        self._oai_agent = oai_agent
        self._slug = slug or oai_agent.name
        self._model = model_name or getattr(oai_agent, "model", None) or "gpt-4o"
        self._turn = 0

    @classmethod
    def from_pyworkflow_agent(
        cls,
        agent: Any,  # pyworkflow_engine.models.ai.agent.Agent
        *,
        tools: list[Any] | None = None,
        handoffs: list[Any] | None = None,
    ) -> OpenAIAgentsRuntime:
        """Factory : convertit un Agent pyworkflow → OAI Agent → Runtime.

        Mapping des champs :
          ``agent.name``          → ``OAIAgent.name``
          ``agent.system_prompt`` → ``OAIAgent.instructions``
          ``agent.model``         → ``OAIAgent.model``

        Args:
            agent: Agent pyworkflow (``models.ai.agent.Agent``).
            tools: Liste d'outils OpenAI SDK (``@function_tool`` ou ``BaseTool``
                   convertis via ``bridge_tool()``).
            handoffs: Liste d'agents OAI vers lesquels handoff est possible.

        Returns:
            Instance ``OpenAIAgentsRuntime``.
        """
        oai_agent = OAIAgent(
            name=agent.name,
            instructions=agent.system_prompt,
            model=agent.model or "gpt-4o",
            tools=tools or [],
            handoffs=handoffs or [],
        )
        return cls(
            oai_agent,
            slug=agent.slug,
            model_name=agent.model or "gpt-4o",
        )

    # ── BaseAgentRuntime interface ──────────────────────────────────

    def run(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution synchrone (wraps async via ``asyncio.run()``)."""
        return asyncio.run(self.arun(prompt, **kwargs))

    async def arun(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution asynchrone — délègue à ``Runner.run()``."""
        self._turn += 1
        start = time.time()

        result = await OAIRunner.run(self._oai_agent, prompt)

        elapsed_ms = (time.time() - start) * 1000

        # Agréger les métriques token depuis les raw_responses
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        for raw in result.raw_responses:
            usage = getattr(raw, "usage", None)
            if usage:
                total_tokens += getattr(usage, "total_tokens", 0) or 0
                prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens += getattr(usage, "completion_tokens", 0) or 0

        # Détecter un éventuel handoff
        handoff_target = None
        if result.last_agent.name != self._oai_agent.name:
            handoff_target = result.last_agent.name

        return AgentResponse(
            content=result.final_output,
            model=self._model,
            agent_slug=self._slug,
            turn=self._turn,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            response_time_ms=elapsed_ms,
            handoff_target=handoff_target,
            metadata={
                "oai_last_agent": result.last_agent.name,
                "oai_raw_responses_count": len(result.raw_responses),
            },
        )

    def reset(self) -> None:
        self._turn = 0

    @property
    def agent_slug(self) -> str:
        return self._slug

    @property
    def model(self) -> str:
        return self._model
