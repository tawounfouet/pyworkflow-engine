"""
adapters/ai/frameworks/langgraph — Runtime LangGraph StateGraph.

Requiert : ``pip install langgraph``
NE requiert PAS ``langchain`` ni ``langchain-openai`` — les appels LLM
passent par ``BaseLLMClient`` natif de pyworkflow.

Seul le moteur d'orchestration (graph, checkpointing, conditional edges,
time-travel) vient de LangGraph.

Architecture : ADR-022

Usage::

    from pyworkflow_engine.adapters.ai.frameworks.langgraph import LangGraphRuntime
    from pyworkflow_engine.adapters.ai.llm.factory import get_llm_client

    client = get_llm_client(provider_config)
    runtime = LangGraphRuntime.from_pyworkflow_agent(my_agent, client=client)

    response = runtime.run("Analyse ce code et propose des corrections")
    print(response.content)

    # Time-travel (LangGraph-specific)
    history = runtime.get_state_history()
"""

from __future__ import annotations

import time
import uuid
from typing import Any, TypedDict

from pyworkflow_engine.ports.ai.llm import BaseLLMClient, LLMRequest
from pyworkflow_engine.ports.ai.runtime import AgentResponse, BaseAgentRuntime

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph
except ImportError as exc:
    raise ImportError(
        "LangGraph adapter requires 'langgraph'. " "Install with: pip install langgraph"
    ) from exc


class _AgentState(TypedDict):
    """State propagé dans le graph LangGraph."""

    messages: list[dict[str, str]]
    agent_slug: str
    turn: int
    final_content: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int


class LangGraphRuntime(BaseAgentRuntime):
    """Runtime qui orchestre un agent via un StateGraph LangGraph.

    L'appel LLM est fait via ``BaseLLMClient`` (pyworkflow natif).
    Seul le moteur d'orchestration (graph, checkpointing, conditional
    edges) vient de LangGraph.

    Avantages vs natif :
      - Checkpointing automatique (``MemorySaver`` ou ``SqliteSaver``)
      - Time-travel / replay via ``get_state_history()``
      - Graphs complexes avec conditional edges et multi-nodes

    Limitations :
      - Dépendance ``langgraph`` (~15 deps)
      - Graph doit être construit à l'avance (pas de mode REPL interactif)
    """

    def __init__(
        self,
        compiled_graph: Any,
        *,
        slug: str = "",
        model_name: str = "",
        checkpointer: Any | None = None,
    ) -> None:
        self._compiled = compiled_graph
        self._slug = slug
        self._model = model_name
        self._checkpointer = checkpointer
        self._turn = 0
        self._thread_id = str(uuid.uuid4())

    @classmethod
    def from_pyworkflow_agent(
        cls,
        agent: Any,  # pyworkflow Agent model
        *,
        client: BaseLLMClient,
        enable_checkpointing: bool = True,
        extra_nodes: dict[str, Any] | None = None,
    ) -> LangGraphRuntime:
        """Factory : construit un StateGraph à partir d'un Agent pyworkflow.

        Le graph par défaut est simple : ``START → agent_node → END``.
        Les ``extra_nodes`` permettent d'ajouter des étapes (review,
        validate, …) avec des edges conditionnels.

        **Point clé** : l'appel LLM passe par ``BaseLLMClient``, pas par
        les classes LangChain.  Cela préserve le multi-provider natif
        (OpenAI, Anthropic, Groq, Ollama, Gemini).

        Args:
            agent: Agent pyworkflow (``models.ai.agent.Agent``).
            client: Client LLM pyworkflow (``BaseLLMClient``).
            enable_checkpointing: Active le ``MemorySaver`` pour les snapshots.
            extra_nodes: Nodes supplémentaires ``{name: callable}``.

        Returns:
            Instance ``LangGraphRuntime``.
        """
        from pyworkflow_engine.models.ai.message import Message  # noqa: PLC0415
        from pyworkflow_engine.models.ai.types import MessageRole  # noqa: PLC0415

        system_prompt = agent.system_prompt

        def agent_node(state: _AgentState) -> _AgentState:
            """Node principal : appelle le LLM via BaseLLMClient natif."""
            messages: list[Any] = []
            if system_prompt:
                messages.append(
                    Message(
                        conversation_id="langgraph",
                        role=MessageRole.SYSTEM,
                        content=system_prompt,
                    )
                )
            for msg in state["messages"]:
                messages.append(
                    Message(
                        conversation_id="langgraph",
                        role=MessageRole(msg["role"]),
                        content=msg["content"],
                    )
                )

            request = LLMRequest(
                messages=messages,
                temperature=agent.config.temperature,
                max_tokens=agent.config.max_tokens_per_response,
            )
            response = client.complete(request)

            new_messages = list(state["messages"]) + [
                {"role": "assistant", "content": response.content}
            ]

            new_total = state["total_tokens"]
            new_prompt = state["prompt_tokens"]
            new_completion = state["completion_tokens"]
            if response.usage:
                new_total += response.usage.total_tokens
                new_prompt += response.usage.prompt_tokens
                new_completion += response.usage.completion_tokens

            return {
                "messages": new_messages,
                "agent_slug": state["agent_slug"],
                "turn": state["turn"] + 1,
                "final_content": response.content,
                "total_tokens": new_total,
                "prompt_tokens": new_prompt,
                "completion_tokens": new_completion,
            }

        # Build the graph
        graph = StateGraph(_AgentState)
        graph.add_node("agent", agent_node)

        # Add extra nodes if provided
        if extra_nodes:
            for name, node_fn in extra_nodes.items():
                graph.add_node(name, node_fn)

        graph.set_entry_point("agent")

        # Default: agent → END (caller can override with extra_nodes + edges)
        if not extra_nodes:
            graph.add_edge("agent", END)

        checkpointer = MemorySaver() if enable_checkpointing else None
        compiled = graph.compile(checkpointer=checkpointer)

        return cls(
            compiled_graph=compiled,
            slug=agent.slug,
            model_name=agent.model or client.get_model(),
            checkpointer=checkpointer,
        )

    # ── BaseAgentRuntime interface ──────────────────────────────────

    def run(self, prompt: str, **kwargs: Any) -> AgentResponse:
        self._turn += 1
        start = time.time()

        initial_state: _AgentState = {
            "messages": [{"role": "user", "content": prompt}],
            "agent_slug": self._slug,
            "turn": 0,
            "final_content": "",
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

        config = {"configurable": {"thread_id": self._thread_id}}
        result = self._compiled.invoke(initial_state, config=config)

        elapsed_ms = (time.time() - start) * 1000

        return AgentResponse(
            content=result["final_content"],
            model=self._model,
            agent_slug=self._slug,
            turn=result["turn"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            total_tokens=result["total_tokens"],
            response_time_ms=elapsed_ms,
            metadata={
                "langgraph_thread_id": self._thread_id,
                "langgraph_checkpointed": self._checkpointer is not None,
            },
        )

    async def arun(self, prompt: str, **kwargs: Any) -> AgentResponse:
        self._turn += 1
        start = time.time()

        initial_state: _AgentState = {
            "messages": [{"role": "user", "content": prompt}],
            "agent_slug": self._slug,
            "turn": 0,
            "final_content": "",
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

        config = {"configurable": {"thread_id": self._thread_id}}
        result = await self._compiled.ainvoke(initial_state, config=config)

        elapsed_ms = (time.time() - start) * 1000

        return AgentResponse(
            content=result["final_content"],
            model=self._model,
            agent_slug=self._slug,
            turn=result["turn"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            total_tokens=result["total_tokens"],
            response_time_ms=elapsed_ms,
            metadata={
                "langgraph_thread_id": self._thread_id,
                "langgraph_checkpointed": self._checkpointer is not None,
            },
        )

    def reset(self) -> None:
        self._turn = 0
        # Changer de thread_id pour recommencer un historique vierge
        self._thread_id = str(uuid.uuid4())

    @property
    def agent_slug(self) -> str:
        return self._slug

    @property
    def model(self) -> str:
        return self._model

    # ── LangGraph-specific extras ───────────────────────────────────

    def get_state_history(self) -> list[dict[str, Any]]:
        """Retourne l'historique des checkpoints (time-travel).

        Spécifique LangGraph — non exposé via ``BaseAgentRuntime``.

        Returns:
            Liste de snapshots d'état.
        """
        if not self._checkpointer:
            return []
        config = {"configurable": {"thread_id": self._thread_id}}
        return list(self._compiled.get_state_history(config))

    def replay_from_checkpoint(self, checkpoint_id: str) -> AgentResponse:
        """Rejoint l'exécution à partir d'un checkpoint donné.

        Spécifique LangGraph — non exposé via ``BaseAgentRuntime``.

        Args:
            checkpoint_id: ID du checkpoint à rejoindre.

        Returns:
            ``AgentResponse`` de la re-exécution.
        """
        config = {
            "configurable": {
                "thread_id": self._thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
        result = self._compiled.invoke(None, config=config)
        return AgentResponse(
            content=result["final_content"],
            model=self._model,
            agent_slug=self._slug,
            turn=result["turn"],
        )
