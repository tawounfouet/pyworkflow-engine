"""
adapters/ai/storage/memory — Backend IA en mémoire (tests / prototypage).

Toutes les données sont stockées dans des dicts Python.
Aucune persistance entre les redémarrages.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pyworkflow_engine.models.ai.agent import Agent
from pyworkflow_engine.models.ai.conversation import Conversation
from pyworkflow_engine.models.ai.execution import Execution, ExecutionStep
from pyworkflow_engine.models.ai.graph import Graph
from pyworkflow_engine.models.ai.knowledge import KnowledgeSource
from pyworkflow_engine.models.ai.memory import AgentMemory
from pyworkflow_engine.models.ai.message import Message
from pyworkflow_engine.models.ai.provider import LLMProviderConfig
from pyworkflow_engine.models.ai.skill import AgentSkillAssignment, Skill
from pyworkflow_engine.models.ai.tool import ToolDefinition
from pyworkflow_engine.models.ai.types import AgentRole, ExecutionStatus, MemoryType
from pyworkflow_engine.ports.ai.storage import BaseAIStorage


class InMemoryAIStorage(BaseAIStorage):
    """Implémentation en mémoire de BaseAIStorage (tests / prototypage)."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProviderConfig] = {}
        self._agents: dict[str, Agent] = {}
        self._tools: dict[str, ToolDefinition] = {}
        self._skills: dict[str, Skill] = {}
        self._skill_assignments: dict[str, AgentSkillAssignment] = {}
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, Message] = {}
        self._executions: dict[str, Execution] = {}
        self._execution_steps: dict[str, ExecutionStep] = {}
        self._graphs: dict[str, Graph] = {}
        self._memories: dict[str, AgentMemory] = {}
        self._knowledge_sources: dict[str, KnowledgeSource] = {}

    # ── Providers ──────────────────────────────────────────────────────

    def save_provider(self, provider: LLMProviderConfig) -> LLMProviderConfig:
        self._providers[provider.id] = provider
        return provider

    def get_provider(self, provider_id: str) -> LLMProviderConfig | None:
        return self._providers.get(provider_id)

    def get_provider_by_name(self, name: str) -> LLMProviderConfig | None:
        return next((p for p in self._providers.values() if p.name == name), None)

    def list_providers(
        self, *, is_active: bool | None = None
    ) -> list[LLMProviderConfig]:
        providers = list(self._providers.values())
        if is_active is not None:
            providers = [p for p in providers if p.is_active == is_active]
        return providers

    def delete_provider(self, provider_id: str) -> bool:
        if provider_id in self._providers:
            del self._providers[provider_id]
            return True
        return False

    # ── Agents ─────────────────────────────────────────────────────────

    def save_agent(self, agent: Agent) -> Agent:
        self._agents[agent.id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def get_agent_by_slug(self, slug: str) -> Agent | None:
        return next((a for a in self._agents.values() if a.slug == slug), None)

    def list_agents(
        self,
        *,
        owner_id: str | None = None,
        role: AgentRole | None = None,
        is_active: bool | None = None,
    ) -> list[Agent]:
        agents = list(self._agents.values())
        if owner_id is not None:
            agents = [a for a in agents if a.owner_id == owner_id]
        if role is not None:
            agents = [a for a in agents if a.role == role]
        if is_active is not None:
            agents = [a for a in agents if a.is_active == is_active]
        return agents

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    # ── Tools ──────────────────────────────────────────────────────────

    def save_tool(self, tool: ToolDefinition) -> ToolDefinition:
        self._tools[tool.id] = tool
        return tool

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        return self._tools.get(tool_id)

    def get_tool_by_key(self, key: str) -> ToolDefinition | None:
        return next((t for t in self._tools.values() if t.key == key), None)

    def list_tools(self, *, is_active: bool | None = None) -> list[ToolDefinition]:
        tools = list(self._tools.values())
        if is_active is not None:
            tools = [t for t in tools if t.is_active == is_active]
        return tools

    def list_tools_for_agent(self, agent_id: str) -> list[ToolDefinition]:
        agent = self._agents.get(agent_id)
        if not agent:
            return []
        return [t for t in self._tools.values() if t.id in agent.tool_ids]

    def delete_tool(self, tool_id: str) -> bool:
        if tool_id in self._tools:
            del self._tools[tool_id]
            return True
        return False

    # ── Skills ─────────────────────────────────────────────────────────

    def save_skill(self, skill: Skill) -> Skill:
        self._skills[skill.id] = skill
        return skill

    def get_skill(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list_skills(self, *, is_active: bool | None = None) -> list[Skill]:
        skills = list(self._skills.values())
        if is_active is not None:
            skills = [s for s in skills if s.is_active == is_active]
        return skills

    def save_skill_assignment(
        self, assignment: AgentSkillAssignment
    ) -> AgentSkillAssignment:
        self._skill_assignments[assignment.id] = assignment
        return assignment

    def list_skill_assignments_for_agent(
        self, agent_id: str
    ) -> list[AgentSkillAssignment]:
        return [a for a in self._skill_assignments.values() if a.agent_id == agent_id]

    def delete_skill(self, skill_id: str) -> bool:
        if skill_id in self._skills:
            del self._skills[skill_id]
            return True
        return False

    # ── Conversations ──────────────────────────────────────────────────

    def save_conversation(self, conversation: Conversation) -> Conversation:
        self._conversations[conversation.id] = conversation
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def list_conversations(
        self,
        *,
        agent_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[Conversation]:
        convs = list(self._conversations.values())
        if agent_id is not None:
            convs = [c for c in convs if c.agent_id == agent_id]
        if owner_id is not None:
            convs = [c for c in convs if c.owner_id == owner_id]
        return convs

    def delete_conversation(self, conversation_id: str) -> bool:
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    # ── Messages ───────────────────────────────────────────────────────

    def save_message(self, message: Message) -> Message:
        self._messages[message.id] = message
        return message

    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Message]:
        msgs = sorted(
            [
                m
                for m in self._messages.values()
                if m.conversation_id == conversation_id
            ],
            key=lambda m: m.created_at,
        )
        msgs = msgs[offset:]
        if limit is not None:
            msgs = msgs[:limit]
        return msgs

    def count_messages(self, conversation_id: str) -> int:
        return sum(
            1 for m in self._messages.values() if m.conversation_id == conversation_id
        )

    # ── Executions ─────────────────────────────────────────────────────

    def save_execution(self, execution: Execution) -> Execution:
        self._executions[execution.id] = execution
        return execution

    def get_execution(self, execution_id: str) -> Execution | None:
        return self._executions.get(execution_id)

    def list_executions(
        self,
        *,
        agent_id: str | None = None,
        status: ExecutionStatus | None = None,
    ) -> list[Execution]:
        execs = list(self._executions.values())
        if agent_id is not None:
            execs = [e for e in execs if e.agent_id == agent_id]
        if status is not None:
            execs = [e for e in execs if e.status == status]
        return execs

    def save_execution_step(self, step: ExecutionStep) -> ExecutionStep:
        self._execution_steps[step.id] = step
        return step

    def get_execution_steps(self, execution_id: str) -> list[ExecutionStep]:
        return sorted(
            [
                s
                for s in self._execution_steps.values()
                if s.execution_id == execution_id
            ],
            key=lambda s: s.order,
        )

    # ── Graphs ─────────────────────────────────────────────────────────

    def save_graph(self, graph: Graph) -> Graph:
        self._graphs[graph.id] = graph
        return graph

    def get_graph(self, graph_id: str) -> Graph | None:
        return self._graphs.get(graph_id)

    def get_graph_by_slug(self, slug: str) -> Graph | None:
        return next((g for g in self._graphs.values() if g.slug == slug), None)

    def list_graphs(
        self,
        *,
        agent_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[Graph]:
        graphs = list(self._graphs.values())
        if agent_id is not None:
            graphs = [g for g in graphs if g.agent_id == agent_id]
        if owner_id is not None:
            graphs = [g for g in graphs if g.owner_id == owner_id]
        return graphs

    def delete_graph(self, graph_id: str) -> bool:
        if graph_id in self._graphs:
            del self._graphs[graph_id]
            return True
        return False

    # ── Memory ─────────────────────────────────────────────────────────

    def save_memory(self, memory: AgentMemory) -> AgentMemory:
        self._memories[memory.id] = memory
        return memory

    def get_memory(self, agent_id: str, key: str) -> AgentMemory | None:
        return next(
            (
                m
                for m in self._memories.values()
                if m.agent_id == agent_id and m.key == key
            ),
            None,
        )

    def list_memories(
        self,
        agent_id: str,
        *,
        memory_type: MemoryType | None = None,
    ) -> list[AgentMemory]:
        mems = [m for m in self._memories.values() if m.agent_id == agent_id]
        if memory_type is not None:
            mems = [m for m in mems if m.memory_type == memory_type]
        return mems

    def delete_memory(self, memory_id: str) -> bool:
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    def delete_expired_memories(self) -> int:
        now = datetime.now(UTC)
        expired = [
            mid
            for mid, mem in self._memories.items()
            if mem.expires_at is not None and mem.expires_at < now
        ]
        for mid in expired:
            del self._memories[mid]
        return len(expired)

    # ── Knowledge ──────────────────────────────────────────────────────

    def save_knowledge_source(self, source: KnowledgeSource) -> KnowledgeSource:
        self._knowledge_sources[source.id] = source
        return source

    def get_knowledge_source(self, source_id: str) -> KnowledgeSource | None:
        return self._knowledge_sources.get(source_id)

    def list_knowledge_sources(
        self, *, agent_id: str | None = None
    ) -> list[KnowledgeSource]:
        sources = list(self._knowledge_sources.values())
        if agent_id is not None:
            sources = [s for s in sources if agent_id in s.agent_ids]
        return sources

    def delete_knowledge_source(self, source_id: str) -> bool:
        if source_id in self._knowledge_sources:
            del self._knowledge_sources[source_id]
            return True
        return False
