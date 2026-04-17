# ADR-022 — Patterns d'intégration : OpenAI Agents SDK, LangGraph, AutoGen comme adapters

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-022                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | 📐 Proposition (blueprint)          |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (hexagonal), ADR-020 (framework strategy), ADR-021 (industry comparison) |
| **Version cible** | v0.13.0+                       |

---

## Contexte

L'ADR-020 et l'ADR-021 ont décidé de **ne pas adopter** OpenAI Agents SDK, LangGraph ou AutoGen comme dépendances. Cependant, la question reste ouverte :

> **Comment ces frameworks pourraient-ils s'intégrer comme adapters optionnels derrière les ports hexagonaux existants, sans modifier le core ?**

Ce document fournit les **blueprints concrets** — avec code, point d'insertion, et impact — pour chaque framework.

---

## Principe architectural : l'Adapter Sandwich

L'intégration suit toujours le même pattern. Le framework externe est **encapsulé** dans un adapter qui implémente un port existant. Le code métier (agents, runner, CLI) ne voit jamais le framework.

```
                ┌─────────────────────────────────────────┐
                │          Code métier (inchangé)          │
                │  AgentRunner / CLI / Pipeline            │
                └───────────────┬─────────────────────────┘
                                │ appelle le port
                                ▼
                ┌─────────────────────────────────────────┐
                │          Port (ABC inchangé)             │
                │  BaseLLMClient / BaseTool / BaseSkill    │
                │  BaseAgentRuntime (nouveau, optionnel)   │
                └───────────────┬─────────────────────────┘
                                │ implémenté par
                                ▼
                ┌─────────────────────────────────────────┐
                │    Adapter (NOUVEAU — lazy-imported)     │
                │  adapters/ai/frameworks/openai_agents.py │
                │  adapters/ai/frameworks/langgraph.py     │
                │  adapters/ai/frameworks/autogen.py       │
                └───────────────┬─────────────────────────┘
                                │ wraps
                                ▼
                ┌─────────────────────────────────────────┐
                │    Framework SDK (optional dependency)   │
                │  openai-agents / langgraph / autogen     │
                └─────────────────────────────────────────┘
```

Règle d'or : **aucun import du framework SDK ne doit exister en dehors de son adapter**.

---

## Nouveau port : `BaseAgentRuntime`

Avant d'intégrer des frameworks, il faut **extraire un port** de la classe `AgentRunner` actuelle. Aujourd'hui `AgentRunner` est un adapter concret sans port — ce qui empêche de le substituer.

### Fichier : `ports/ai/runtime.py`

```python
"""
Port IA — interface abstraite pour l'exécution d'un agent.

Tout runtime (natif, OpenAI Agents SDK, LangGraph, AutoGen) implémente
ce contrat. Le code métier (CLI, tests, orchestrateurs) n'interagit
qu'avec ce port.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResponse:
    """Réponse normalisée d'un runtime agent (framework-agnostic)."""
    content: str
    model: str = ""
    agent_slug: str = ""
    turn: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    response_time_ms: float = 0.0
    finish_reason: str | None = None
    tool_calls_made: list[str] = field(default_factory=list)
    handoff_target: str | None = None  # slug of agent handed off to
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgentRuntime(ABC):
    """Interface abstraite pour exécuter un agent.

    Implémentations concrètes :
      - NativeAgentRuntime   (wrap actuel AgentRunner)
      - OpenAIAgentsRuntime  (OpenAI Agents SDK)
      - LangGraphRuntime     (LangGraph StateGraph)
      - AutoGenRuntime       (AutoGen ConversableAgent)
    """

    @abstractmethod
    def run(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution synchrone one-shot."""

    @abstractmethod
    async def arun(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution asynchrone one-shot."""

    @abstractmethod
    def reset(self) -> None:
        """Réinitialise l'état (historique, mémoire de session)."""

    @property
    @abstractmethod
    def agent_slug(self) -> str:
        """Identifiant unique de l'agent exécuté."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Modèle LLM utilisé."""
```

### Adapter natif : wrap de l'actuel `AgentRunner`

L'implémentation par défaut (`NativeAgentRuntime`) wrap `AgentRunner` tel quel, sans casser le code existant :

```python
# adapters/ai/frameworks/native.py
from agents.shared.runner import AgentRunner
from pyworkflow_engine.ports.ai.runtime import BaseAgentRuntime, AgentResponse

class NativeAgentRuntime(BaseAgentRuntime):
    """Runtime natif — délègue à AgentRunner existant."""

    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    def run(self, prompt: str, **kwargs) -> AgentResponse:
        resp = self._runner.ask(prompt, **kwargs)
        return AgentResponse(
            content=resp.content,
            model=resp.model,
            agent_slug=self._runner.agent.slug,
            turn=self._runner._turn,
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
            total_tokens=resp.usage.total_tokens if resp.usage else 0,
            response_time_ms=resp.response_time_ms or 0.0,
            finish_reason=resp.finish_reason,
        )

    async def arun(self, prompt: str, **kwargs) -> AgentResponse:
        resp = await self._runner.aask(prompt, **kwargs)
        return AgentResponse(
            content=resp.content,
            model=resp.model,
            agent_slug=self._runner.agent.slug,
            turn=self._runner._turn,
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
            total_tokens=resp.usage.total_tokens if resp.usage else 0,
            response_time_ms=resp.response_time_ms or 0.0,
            finish_reason=resp.finish_reason,
        )

    def reset(self) -> None:
        self._runner.reset()

    @property
    def agent_slug(self) -> str:
        return self._runner.agent.slug

    @property
    def model(self) -> str:
        return self._runner.model
```

---

## Intégration 1 : OpenAI Agents SDK

### Ce que le SDK apporte vs le natif

| Feature | Natif pyworkflow | OpenAI Agents SDK |
|---------|-----------------|-------------------|
| Agent + tools + loop | ✅ AgentRunner + ToolExecutor | ✅ `Agent` + `Runner.run()` |
| **Handoff** | ❌ (gap ADR-021 Phase 1) | ✅ `agent.handoff()` natif |
| **Guardrails** | ❌ (gap ADR-021 Phase 4) | ✅ `InputGuardrail` / `OutputGuardrail` |
| **Tracing** | ✅ Structured logging + persistence | ✅ Traces API intégrée |
| Multi-provider | ✅ 5 providers | ❌ OpenAI uniquement |

**Intérêt** : utile uniquement si le projet veut les handoffs et guardrails clé-en-main de l'SDK, et que les agents utilisent exclusivement OpenAI.

### Point d'insertion dans l'architecture

```
ports/ai/runtime.py  ← BaseAgentRuntime (nouveau port)
    │
    ├── adapters/ai/frameworks/native.py        ← NativeAgentRuntime (défaut)
    └── adapters/ai/frameworks/openai_agents.py  ← OpenAIAgentsRuntime (opt.)
```

### Adapter : `adapters/ai/frameworks/openai_agents.py`

```python
"""
Adapter OpenAI Agents SDK → BaseAgentRuntime.

Requiert : pip install openai-agents
Usage :
    from adapters.ai.frameworks.openai_agents import OpenAIAgentsRuntime
    runtime = OpenAIAgentsRuntime.from_pyworkflow_agent(my_agent)
    response = runtime.run("Analyse ce fichier")
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from pyworkflow_engine.ports.ai.runtime import AgentResponse, BaseAgentRuntime

try:
    from agents import Agent as OAIAgent  # openai-agents SDK
    from agents import Runner as OAIRunner
    from agents import function_tool
except ImportError as exc:
    raise ImportError(
        "OpenAI Agents SDK requires 'openai-agents'. "
        "Install with: pip install openai-agents"
    ) from exc


class OpenAIAgentsRuntime(BaseAgentRuntime):
    """Runtime qui délègue à l'OpenAI Agents SDK.

    Convertit un Agent pyworkflow en OAI Agent, exécute via Runner.run(),
    et normalise la réponse en AgentResponse.
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
        self._model = model_name or oai_agent.model or "gpt-4o"
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
          agent.name          → OAIAgent.name
          agent.system_prompt → OAIAgent.instructions
          agent.model         → OAIAgent.model
          agent.tool_ids      → résolu via ToolRegistry → @function_tool
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

    # ── BaseAgentRuntime interface ──────────────────────────────

    def run(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution synchrone via asyncio.run()."""
        return asyncio.run(self.arun(prompt, **kwargs))

    async def arun(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution async — délègue à OAI Runner.run()."""
        self._turn += 1
        start = time.time()

        result = await OAIRunner.run(self._oai_agent, prompt)

        elapsed_ms = (time.time() - start) * 1000

        # Extraire les tool calls effectués depuis le raw_responses
        tool_calls_made = []
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        for raw in result.raw_responses:
            if hasattr(raw, "usage") and raw.usage:
                total_tokens += getattr(raw.usage, "total_tokens", 0)
                prompt_tokens += getattr(raw.usage, "prompt_tokens", 0)
                completion_tokens += getattr(raw.usage, "completion_tokens", 0)

        # Détecter si un handoff a eu lieu
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
```

### Bridging des Tools pyworkflow → OpenAI Agents SDK

Les `BaseTool` de pyworkflow doivent être convertis en `@function_tool` du SDK :

```python
# adapters/ai/frameworks/openai_agents_tools.py
"""Bridge : BaseTool pyworkflow → @function_tool OpenAI Agents SDK."""

from agents import function_tool  # openai-agents SDK
from pyworkflow_engine.ports.ai.tool import BaseTool


def bridge_tool(pw_tool: BaseTool):
    """Convertit un BaseTool pyworkflow en function_tool OpenAI Agents SDK.

    Le schéma JSON parameters_schema est réutilisé tel quel car il est
    déjà au format OpenAI function-calling.
    """
    @function_tool(
        name_override=pw_tool.key,
        description_override=pw_tool.description,
    )
    def _wrapped(**kwargs):
        return pw_tool.run(**kwargs)

    return _wrapped


def bridge_all_tools(tools: list[BaseTool]) -> list:
    """Convertit une liste de BaseTool → liste de function_tool."""
    return [bridge_tool(t) for t in tools]
```

### Bridging des Handoffs

Le concept de **handoff** du SDK OpenAI se traduit par un transfert entre `BaseAgentRuntime` instances :

```python
# adapters/ai/frameworks/openai_agents_handoff.py
"""Bridge : handoff OpenAI Agents SDK → AgentResponse.handoff_target."""

from agents import Agent as OAIAgent


def create_handoff_agents(
    agents_map: dict[str, "Agent"],  # slug → pyworkflow Agent
) -> dict[str, OAIAgent]:
    """Crée des OAI Agents avec handoffs croisés.

    Usage :
        agents = create_handoff_agents({
            "code-reviewer": code_reviewer_agent,
            "doc-researcher": doc_researcher_agent,
        })
        # agents["code-reviewer"] peut handoff vers "doc-researcher" et vice-versa
    """
    oai_agents = {}
    for slug, pw_agent in agents_map.items():
        oai_agents[slug] = OAIAgent(
            name=pw_agent.name,
            instructions=pw_agent.system_prompt,
            model=pw_agent.model or "gpt-4o",
        )

    # Wiring des handoffs (chaque agent peut handoff vers tous les autres)
    for slug, oai_agent in oai_agents.items():
        oai_agent.handoffs = [
            a for s, a in oai_agents.items() if s != slug
        ]

    return oai_agents
```

---

## Intégration 2 : LangGraph

### Ce que LangGraph apporte vs le natif

| Feature | Natif pyworkflow | LangGraph |
|---------|-----------------|-----------|
| DAG / Pipeline | ✅ `Pipeline` + `DAGResolver` | ✅ `StateGraph` |
| Conditional edges | ✅ `PipelineStage.condition` | ✅ `add_conditional_edges()` |
| **Checkpointing** | ❌ (gap ADR-021 Phase 2) | ✅ `MemorySaver` / `SqliteSaver` |
| **Time-travel** | ❌ (gap ADR-021 Phase 2) | ✅ `get_state_history()` |
| Human-in-the-loop | ✅ `SuspensionManager` | ✅ `interrupt_before` |
| Multi-provider | ✅ 5 providers | ⚠️ Via `langchain-openai`, `langchain-anthropic`... |

**Intérêt** : utile uniquement pour le checkpointing/replay sur des pipelines agents longues. La plupart des cas sont couverts nativement.

### Point d'insertion dans l'architecture

LangGraph ne remplace PAS `BaseLLMClient` — il se place **au-dessus**, comme un runtime alternatif pour les pipelines agents complexes :

```
ports/ai/runtime.py  ← BaseAgentRuntime
    │
    ├── adapters/ai/frameworks/native.py       ← NativeAgentRuntime (défaut)
    └── adapters/ai/frameworks/langgraph.py    ← LangGraphRuntime (opt.)
                                                    │
                                                    └── utilise BaseLLMClient
                                                        en interne (pas langchain LLM)
```

**Point clé** : l'adapter LangGraph utilise les **`BaseLLMClient` de pyworkflow** pour les appels LLM, pas les classes LangChain. Seul le moteur d'orchestration (graph, checkpointing) vient de LangGraph.

### Adapter : `adapters/ai/frameworks/langgraph.py`

```python
"""
Adapter LangGraph → BaseAgentRuntime.

Requiert : pip install langgraph
NE requiert PAS langchain ni langchain-openai — utilise BaseLLMClient natif.

Usage :
    from adapters.ai.frameworks.langgraph import LangGraphRuntime
    runtime = LangGraphRuntime.from_pyworkflow_agent(my_agent, client=llm_client)
    response = runtime.run("Analyse ce code et propose des corrections")
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, TypedDict

from pyworkflow_engine.ports.ai.llm import BaseLLMClient, LLMRequest
from pyworkflow_engine.ports.ai.runtime import AgentResponse, BaseAgentRuntime

try:
    from langgraph.graph import END, StateGraph
    from langgraph.checkpoint.memory import MemorySaver
except ImportError as exc:
    raise ImportError(
        "LangGraph adapter requires 'langgraph'. "
        "Install with: pip install langgraph"
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

    L'appel LLM est fait via BaseLLMClient (pyworkflow natif),
    seul le moteur d'orchestration (graph, checkpointing, conditional
    edges) vient de LangGraph.
    """

    def __init__(
        self,
        graph: StateGraph,
        compiled_graph: Any,
        *,
        slug: str = "",
        model_name: str = "",
        checkpointer: Any | None = None,
    ) -> None:
        self._graph = graph
        self._compiled = compiled_graph
        self._slug = slug
        self._model = model_name
        self._checkpointer = checkpointer
        self._turn = 0
        self._thread_id = "default"

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

        Le graph par défaut est :
            START → agent_node → END

        Les extra_nodes permettent d'ajouter des étapes (review, validate, ...)
        avec des edges conditionnels.
        """
        from pyworkflow_engine.models.ai.message import Message
        from pyworkflow_engine.models.ai.types import MessageRole

        system_prompt = agent.system_prompt

        def agent_node(state: _AgentState) -> _AgentState:
            """Node principal : appelle le LLM via BaseLLMClient natif."""
            messages = []
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

            new_state = dict(state)
            new_state["final_content"] = response.content
            new_state["turn"] = state["turn"] + 1
            new_state["messages"] = state["messages"] + [
                {"role": "assistant", "content": response.content}
            ]
            if response.usage:
                new_state["total_tokens"] = (
                    state["total_tokens"] + response.usage.total_tokens
                )
                new_state["prompt_tokens"] = (
                    state["prompt_tokens"] + response.usage.prompt_tokens
                )
                new_state["completion_tokens"] = (
                    state["completion_tokens"] + response.usage.completion_tokens
                )
            return new_state

        # Build the graph
        graph = StateGraph(_AgentState)
        graph.add_node("agent", agent_node)

        # Add extra nodes if provided (e.g., review, validate)
        if extra_nodes:
            for name, node_fn in extra_nodes.items():
                graph.add_node(name, node_fn)

        graph.set_entry_point("agent")

        # Default: agent → END (override with extra_nodes for complex flows)
        if not extra_nodes:
            graph.add_edge("agent", END)

        checkpointer = MemorySaver() if enable_checkpointing else None
        compiled = graph.compile(checkpointer=checkpointer)

        return cls(
            graph=graph,
            compiled_graph=compiled,
            slug=agent.slug,
            model_name=agent.model or client.get_model(),
            checkpointer=checkpointer,
        )

    # ── BaseAgentRuntime interface ──────────────────────────────

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
        import uuid
        self._thread_id = str(uuid.uuid4())

    @property
    def agent_slug(self) -> str:
        return self._slug

    @property
    def model(self) -> str:
        return self._model

    # ── LangGraph-specific extras ───────────────────────────────

    def get_state_history(self) -> list[dict]:
        """Retourne l'historique des checkpoints (time-travel).

        Spécifique LangGraph — non exposé via BaseAgentRuntime.
        """
        if not self._checkpointer:
            return []
        config = {"configurable": {"thread_id": self._thread_id}}
        return list(self._compiled.get_state_history(config))

    def replay_from_checkpoint(self, checkpoint_id: str) -> AgentResponse:
        """Rejoint l'exécution à partir d'un checkpoint donné.

        Spécifique LangGraph — non exposé via BaseAgentRuntime.
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
```

### Architecture clé : LLM via pyworkflow, orchestration via LangGraph

```
┌─────────────────────────────────────────────────────┐
│                LangGraphRuntime                      │
│                                                     │
│  ┌──────────────┐     ┌───────────────────────┐     │
│  │ StateGraph    │────▶│ agent_node()           │     │
│  │ (LangGraph)   │     │                       │     │
│  │               │     │  ┌──────────────────┐ │     │
│  │ checkpointing │     │  │ BaseLLMClient    │ │     │
│  │ conditionals  │     │  │ (pyworkflow natif)│ │     │
│  │ time-travel   │     │  │                  │ │     │
│  └──────────────┘     │  │ OpenAIClient     │ │     │
│                        │  │ AnthropicClient  │ │     │
│                        │  │ GroqClient       │ │     │
│                        │  └──────────────────┘ │     │
│                        └───────────────────────┘     │
└─────────────────────────────────────────────────────┘

= Les appels LLM passent par NOS adapters (multi-provider)
= Seul le moteur d'orchestration vient de LangGraph
= Pas de dépendance langchain-openai / langchain-anthropic
```

---

## Intégration 3 : AutoGen

### Ce que AutoGen apporte vs le natif

| Feature | Natif pyworkflow | AutoGen |
|---------|-----------------|---------|
| Multi-agent conversation | ❌ | ✅ `ConversableAgent` + `GroupChat` |
| Code execution sandbox | ❌ | ✅ Docker executor |
| Self-reflection | ❌ (faisable en ~50 lignes) | ✅ natif |
| Multi-provider | ✅ 5 providers | ⚠️ Via config dict |
| Persistence | ✅ `AgentSessionPersistence` | ❌ Rien de durable |

**Intérêt** : utile uniquement si un vrai besoin de conversation multi-agent émerge (voir ADR-021 : aucun cas d'usage actuel).

### Point d'insertion : runtime multi-agent

AutoGen ne s'insère pas en tant que runtime simple — il orchestre **plusieurs agents**. Le point d'insertion naturel est un nouveau concept `MultiAgentRuntime` qui étend `BaseAgentRuntime` :

```
ports/ai/runtime.py  ← BaseAgentRuntime
    │
    ├── adapters/ai/frameworks/native.py       ← NativeAgentRuntime (single)
    ├── adapters/ai/frameworks/openai_agents.py ← OpenAIAgentsRuntime (single+handoff)
    ├── adapters/ai/frameworks/langgraph.py     ← LangGraphRuntime (graph)
    └── adapters/ai/frameworks/autogen.py       ← AutoGenRuntime (multi-agent)
```

### Adapter : `adapters/ai/frameworks/autogen.py`

```python
"""
Adapter AutoGen → BaseAgentRuntime.

Requiert : pip install autogen-agentchat
Usage :
    from adapters.ai.frameworks.autogen import AutoGenRuntime
    runtime = AutoGenRuntime.from_pyworkflow_agents(
        agents=[researcher, coder, reviewer],
        max_rounds=5,
    )
    response = runtime.run("Review and document this codebase")
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from pyworkflow_engine.ports.ai.runtime import AgentResponse, BaseAgentRuntime

try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_agentchat.conditions import MaxMessageTermination
    from autogen_ext.models.openai import OpenAIChatCompletionClient
except ImportError as exc:
    raise ImportError(
        "AutoGen adapter requires 'autogen-agentchat' and 'autogen-ext'. "
        "Install with: pip install autogen-agentchat autogen-ext[openai]"
    ) from exc


def _make_autogen_model_client(
    agent: Any,  # pyworkflow Agent
) -> OpenAIChatCompletionClient:
    """Crée un model client AutoGen depuis la config d'un Agent pyworkflow.

    Note : AutoGen v0.4+ gère ses propres clients LLM. On ne peut pas
    injecter BaseLLMClient directement (API incompatible). Le bridge
    est donc au niveau config, pas au niveau client.
    """
    # Résoudre le provider type depuis l'agent
    pid = agent.provider_id.lower()
    if "anthropic" in pid:
        # AutoGen supporte Anthropic via un wrapper compatible OpenAI
        return OpenAIChatCompletionClient(
            model=agent.model or "claude-3-5-sonnet-latest",
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            base_url="https://api.anthropic.com/v1",
        )
    # Default : OpenAI
    return OpenAIChatCompletionClient(
        model=agent.model or "gpt-4o",
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )


class AutoGenRuntime(BaseAgentRuntime):
    """Runtime multi-agent via AutoGen GroupChat.

    Encapsule N agents AutoGen dans un GroupChat avec max_rounds.
    Le résultat est la dernière réponse du dernier agent.
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
          agent.name          → AssistantAgent.name
          agent.system_prompt → AssistantAgent.system_message
          agent.model         → model_client config
        """
        autogen_agents = []
        slugs = []
        for pw_agent in agents:
            model_client = _make_autogen_model_client(pw_agent)
            ag_agent = AssistantAgent(
                name=pw_agent.slug.replace("-", "_"),  # AutoGen no dashes
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

    # ── BaseAgentRuntime interface ──────────────────────────────

    def run(self, prompt: str, **kwargs: Any) -> AgentResponse:
        return asyncio.run(self.arun(prompt, **kwargs))

    async def arun(self, prompt: str, **kwargs: Any) -> AgentResponse:
        from autogen_agentchat.messages import TextMessage
        from autogen_core import CancellationToken

        self._turn += 1
        start = time.time()

        task = TextMessage(content=prompt, source="user")
        result = await self._team.run(task=task)

        elapsed_ms = (time.time() - start) * 1000

        # Extraire le contenu du dernier message
        final_content = ""
        all_messages = []
        for msg in result.messages:
            all_messages.append(f"[{msg.source}] {msg.content[:200]}")
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
                "autogen_conversation": all_messages,
            },
        )

    def reset(self) -> None:
        self._turn = 0
        # AutoGen teams are stateless per run — no reset needed

    @property
    def agent_slug(self) -> str:
        return self._slug

    @property
    def model(self) -> str:
        return self._model
```

### Limitation architecturale : AutoGen gère ses propres LLM clients

Contrairement à l'adapter LangGraph (qui réutilise `BaseLLMClient`), AutoGen v0.4 impose ses propres clients LLM via `model_client`. Le bridge est donc **au niveau configuration** (on passe l'API key et le model), pas au niveau appel.

```
┌─────────────────────────────────────────────────────┐
│              AutoGenRuntime                          │
│                                                     │
│  ┌──────────────┐     ┌───────────────────────┐     │
│  │ GroupChat     │────▶│ AssistantAgent (×N)    │     │
│  │ (AutoGen)     │     │                       │     │
│  │               │     │  ┌──────────────────┐ │     │
│  │ round-robin   │     │  │ model_client     │ │     │
│  │ termination   │     │  │ (AutoGen interne)│ │     │
│  │ max_rounds    │     │  │                  │ │     │
│  └──────────────┘     │  │ ≠ BaseLLMClient  │ │     │
│                        │  │ (bridge config)  │ │     │
│                        │  └──────────────────┘ │     │
│                        └───────────────────────┘     │
│                                                     │
│  ⚠️  LLM calls go through AutoGen, not pyworkflow   │
│     → no unified token counting                     │
│     → no unified persistence per-message            │
└─────────────────────────────────────────────────────┘
```

---

## Factory : `get_agent_runtime()`

Comme pour `get_llm_client()`, une factory résout le runtime au démarrage :

```python
# adapters/ai/frameworks/factory.py
"""Factory pour créer un BaseAgentRuntime selon la config."""
from __future__ import annotations

from typing import Any

from pyworkflow_engine.ports.ai.runtime import BaseAgentRuntime


class RuntimeType:
    NATIVE = "native"
    OPENAI_AGENTS = "openai-agents"
    LANGGRAPH = "langgraph"
    AUTOGEN = "autogen"


def get_agent_runtime(
    agent: Any,
    *,
    runtime_type: str = RuntimeType.NATIVE,
    **kwargs: Any,
) -> BaseAgentRuntime:
    """Factory : crée le runtime agent approprié.

    Args:
        agent: Agent pyworkflow (models.ai.agent.Agent)
        runtime_type: "native" | "openai-agents" | "langgraph" | "autogen"
        **kwargs: Options spécifiques au runtime (client, tools, handoffs, ...)

    Raises:
        ImportError: Si le SDK du framework n'est pas installé.
        ValueError: Si le runtime_type est inconnu.
    """
    if runtime_type == RuntimeType.NATIVE:
        from agents.shared.runner import AgentRunner
        from adapters.ai.frameworks.native import NativeAgentRuntime

        runner = AgentRunner(agent, **kwargs)
        return NativeAgentRuntime(runner)

    if runtime_type == RuntimeType.OPENAI_AGENTS:
        from adapters.ai.frameworks.openai_agents import OpenAIAgentsRuntime

        return OpenAIAgentsRuntime.from_pyworkflow_agent(agent, **kwargs)

    if runtime_type == RuntimeType.LANGGRAPH:
        from adapters.ai.frameworks.langgraph import LangGraphRuntime

        return LangGraphRuntime.from_pyworkflow_agent(agent, **kwargs)

    if runtime_type == RuntimeType.AUTOGEN:
        # AutoGen nécessite une liste d'agents
        raise ValueError(
            "AutoGen runtime requires multiple agents. "
            "Use AutoGenRuntime.from_pyworkflow_agents([...]) directly."
        )

    raise ValueError(f"Unknown runtime_type: {runtime_type!r}")
```

---

## Impact sur `pyproject.toml` : extras optionnels

```toml
[project.optional-dependencies]
# Frameworks agents (optionnels — aucun n'est requis)
openai-agents = ["openai-agents>=0.1"]
langgraph     = ["langgraph>=0.3"]
autogen       = ["autogen-agentchat>=0.4", "autogen-ext[openai]>=0.4"]

# Bundle tout
frameworks    = ["openai-agents>=0.1", "langgraph>=0.3", "autogen-agentchat>=0.4"]
```

Installation sélective :
```bash
pip install pyworkflow-engine[openai-agents]   # Juste OpenAI Agents SDK
pip install pyworkflow-engine[langgraph]        # Juste LangGraph
pip install pyworkflow-engine[frameworks]       # Tout
```

---

## Résumé comparatif des 3 intégrations

| Critère | OpenAI Agents SDK | LangGraph | AutoGen |
|---------|------------------|-----------|---------|
| **Port utilisé** | `BaseAgentRuntime` | `BaseAgentRuntime` | `BaseAgentRuntime` |
| **Adapter** | `openai_agents.py` | `langgraph.py` | `autogen.py` |
| **LLM via pyworkflow ?** | ❌ SDK propre (lock-in OpenAI) | ✅ `BaseLLMClient` natif | ❌ `model_client` propre |
| **Tools bridge** | ✅ `BaseTool` → `@function_tool` | ✅ Natif (nodes = fonctions) | ⚠️ Mapping partiel |
| **Multi-provider** | ❌ OpenAI uniquement | ✅ Tous (via BaseLLMClient) | ⚠️ Via config bridge |
| **Persistence intégrée** | ❌ Il faut bridge `AgentResponse` → persistence | ✅ Checkpointing natif | ❌ Aucune |
| **Complexité adapter** | ~120 lignes | ~180 lignes | ~150 lignes |
| **Dep size** | ~5 deps | ~15 deps | ~60 deps |
| **Recommandé pour** | Prototypage rapide OpenAI-only | Pipelines complexes + checkpointing | Research / expérimentation multi-agent |

---

## Diagramme d'ensemble

```
                    ┌──────────────────────────┐
                    │   CLI / API / Tests       │
                    └──────────┬───────────────┘
                               │
                    ┌──────────▼───────────────┐
                    │    BaseAgentRuntime       │  ← PORT (ABC)
                    │    (ports/ai/runtime.py)  │
                    └──────────┬───────────────┘
                               │
          ┌────────────────────┼────────────────────┬──────────────────┐
          │                    │                    │                  │
 ┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐ ┌───────▼───────┐
 │NativeAgentRuntime│ │OpenAIAgentsRT   │ │LangGraphRuntime │ │AutoGenRuntime │
 │                  │ │                 │ │                 │ │               │
 │ AgentRunner      │ │ OAI Agent       │ │ StateGraph      │ │ GroupChat     │
 │ BaseLLMClient ✅ │ │ OAI Runner      │ │ BaseLLMClient ✅│ │ model_client  │
 │ ToolExecutor     │ │ function_tool   │ │ MemorySaver     │ │ AssistantAgent│
 │ Persistence ✅   │ │ Handoffs ✅     │ │ Checkpointing ✅│ │ max_rounds    │
 └─────────────────┘ └────────────────┘ └────────────────┘ └──────────────┘
    DEFAULT              OPTIONAL            OPTIONAL           OPTIONAL
    (0 deps)          (openai-agents)      (langgraph)       (autogen-agentchat)
```

---

## Plan d'implémentation

| Phase | Fichier | Lignes | Prérequis |
|-------|---------|--------|-----------|
| **0** | `ports/ai/runtime.py` | ~60 | Aucun |
| **0** | `adapters/ai/frameworks/native.py` | ~50 | Phase 0 port |
| **0** | `adapters/ai/frameworks/factory.py` | ~40 | Phase 0 port |
| **1** | `adapters/ai/frameworks/openai_agents.py` | ~120 | Phase 0 + `pip install openai-agents` |
| **1** | `adapters/ai/frameworks/openai_agents_tools.py` | ~30 | Phase 1 |
| **2** | `adapters/ai/frameworks/langgraph.py` | ~180 | Phase 0 + `pip install langgraph` |
| **3** | `adapters/ai/frameworks/autogen.py` | ~150 | Phase 0 + `pip install autogen-agentchat` |
| **∞** | Tests + exemples | ~200 | Toutes phases |

**Phase 0 est la seule obligatoire** — elle établit le port et le wrapper natif. Les phases 1-3 sont indépendantes et activables à la demande.

---

## Relation avec les ADR précédentes

- **ADR-020** (framework strategy) → Confirmé : pas d'adoption, intégration optionnelle via adapters
- **ADR-021** (industry comparison) → Les gaps identifiés (handoff, checkpointing, multi-agent, guardrails) sont adressables soit en interne (ADR-021 phases), soit via ces adapters
- **ADR-006** (hexagonal) → Respecté : le port `BaseAgentRuntime` est le point d'inversion de dépendance
