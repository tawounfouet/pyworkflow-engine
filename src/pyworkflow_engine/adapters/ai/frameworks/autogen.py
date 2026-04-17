"""
adapters/ai/frameworks/autogen — Runtime AutoGen multi-agent.

Requiert : ``pip install autogen-agentchat autogen-ext[openai]``

Encapsule AutoGen v0.4+ GroupChat derrière ``BaseAgentRuntime``.
Convertit N agents pyworkflow → AssistantAgent AutoGen, orchestre via
RoundRobinGroupChat, et normalise le résultat en ``AgentResponse``.

Architecture : ADR-022

⚠️  Limitations :
  - AutoGen gère ses propres clients LLM (``model_client``) — les appels
    ne passent PAS par ``BaseLLMClient`` de pyworkflow.
  - Le bridge est au niveau **configuration** (API key + model), pas au
    niveau appel.
  - Pas de persistence par-message intégrée.

Usage::

    from pyworkflow_engine.adapters.ai.frameworks.autogen import AutoGenRuntime

    runtime = AutoGenRuntime.from_pyworkflow_agents(
        agents=[researcher, coder, reviewer],
        max_rounds=5,
    )
    response = await runtime.arun("Review and document this codebase")
    print(response.content)
    print(response.metadata["autogen_conversation"])  # trace complète
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from pyworkflow_engine.ports.ai.runtime import AgentResponse, BaseAgentRuntime

try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.conditions import MaxMessageTermination
    from autogen_agentchat.messages import TextMessage
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_ext.models.openai import OpenAIChatCompletionClient
except ImportError as exc:
    raise ImportError(
        "AutoGen adapter requires 'autogen-agentchat' and 'autogen-ext'. "
        "Install with: pip install autogen-agentchat 'autogen-ext[openai]'"
    ) from exc


def _make_autogen_model_client(
    agent: Any,  # pyworkflow Agent model
) -> OpenAIChatCompletionClient:
    """Crée un model client AutoGen depuis la config d'un Agent pyworkflow.

    AutoGen v0.4+ gère ses propres clients LLM.  On ne peut pas injecter
    ``BaseLLMClient`` directement (API incompatible).  Le bridge est
    au niveau configuration (API key + model name).

    Args:
        agent: Agent pyworkflow avec ``provider_id`` et ``model``.

    Returns:
        ``OpenAIChatCompletionClient`` configuré.
    """
    pid = agent.provider_id.lower()

    if "anthropic" in pid:
        return OpenAIChatCompletionClient(
            model=agent.model or "claude-3-5-sonnet-latest",
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            base_url="https://api.anthropic.com/v1",
        )
    if "groq" in pid:
        return OpenAIChatCompletionClient(
            model=agent.model or "llama-3.1-70b-versatile",
            api_key=os.environ.get("GROQ_API_KEY", ""),
            base_url="https://api.groq.com/openai/v1",
        )

    # Default: OpenAI
    return OpenAIChatCompletionClient(
        model=agent.model or "gpt-4o",
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )


class AutoGenRuntime(BaseAgentRuntime):
    """Runtime multi-agent via AutoGen GroupChat.

    Encapsule N agents AutoGen dans un ``RoundRobinGroupChat`` avec
    ``max_rounds``.  Le résultat est le contenu du dernier message
    du dernier agent.

    Ce runtime implémente ``BaseAgentRuntime`` mais est intrinsèquement
    **multi-agent** — le ``agent_slug`` retourné est un composite des
    slugs des agents participants.
    """

    def __init__(
        self,
        team: RoundRobinGroupChat,
        *,
        slug: str = "autogen-group",
        model_name: str = "gpt-4o",
        max_rounds: int = 5,
        agent_slugs: list[str] | None = None,
    ) -> None:
        self._team = team
        self._slug = slug
        self._model = model_name
        self._max_rounds = max_rounds
        self._agent_slugs = agent_slugs or []
        self._turn = 0

    @classmethod
    def from_pyworkflow_agents(
        cls,
        agents: list[Any],  # list of pyworkflow Agent models
        *,
        max_rounds: int = 5,
    ) -> AutoGenRuntime:
        """Factory : convertit N agents pyworkflow → AutoGen GroupChat.

        Mapping :
          ``agent.name``          → ``AssistantAgent.name``
          ``agent.system_prompt`` → ``AssistantAgent.system_message``
          ``agent.model``         → ``model_client`` config

        Note : AutoGen n'accepte pas les tirets dans les noms d'agents,
        ils sont remplacés par des underscores.

        Args:
            agents: Liste d'agents pyworkflow (``models.ai.agent.Agent``).
            max_rounds: Nombre max de tours de conversation.

        Returns:
            Instance ``AutoGenRuntime``.
        """
        autogen_agents = []
        slugs = []
        for pw_agent in agents:
            model_client = _make_autogen_model_client(pw_agent)
            ag_agent = AssistantAgent(
                name=pw_agent.slug.replace("-", "_"),
                model_client=model_client,
                system_message=pw_agent.system_prompt,
            )
            autogen_agents.append(ag_agent)
            slugs.append(pw_agent.slug)

        termination = MaxMessageTermination(max_messages=max_rounds * len(agents))
        team = RoundRobinGroupChat(
            participants=autogen_agents,
            termination_condition=termination,
        )

        return cls(
            team=team,
            slug=f"autogen-{'_'.join(slugs)}",
            model_name=agents[0].model or "gpt-4o" if agents else "gpt-4o",
            max_rounds=max_rounds,
            agent_slugs=slugs,
        )

    # ── BaseAgentRuntime interface ──────────────────────────────────

    def run(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution synchrone (wraps async via ``asyncio.run()``)."""
        return asyncio.run(self.arun(prompt, **kwargs))

    async def arun(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution async — lance le GroupChat avec le prompt donné."""
        self._turn += 1
        start = time.time()

        task = TextMessage(content=prompt, source="user")
        result = await self._team.run(task=task)

        elapsed_ms = (time.time() - start) * 1000

        # Extraire le contenu et la trace de conversation
        final_content = ""
        conversation_trace: list[str] = []
        for msg in result.messages:
            content_preview = (
                msg.content[:200] if len(msg.content) > 200 else msg.content
            )
            conversation_trace.append(f"[{msg.source}] {content_preview}")
            final_content = msg.content  # dernier message = résultat

        return AgentResponse(
            content=final_content,
            model=self._model,
            agent_slug=self._slug,
            turn=self._turn,
            response_time_ms=elapsed_ms,
            metadata={
                "autogen_rounds": len(result.messages),
                "autogen_agents": self._agent_slugs,
                "autogen_max_rounds": self._max_rounds,
                "autogen_conversation": conversation_trace,
            },
        )

    def reset(self) -> None:
        self._turn = 0
        # AutoGen teams are stateless per run() — no explicit reset needed

    @property
    def agent_slug(self) -> str:
        return self._slug

    @property
    def model(self) -> str:
        return self._model
