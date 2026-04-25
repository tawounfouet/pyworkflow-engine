"""
Tests unitaires — SQLiteAIStorage (ADR-020 Phase 1a).

Vérifie que toutes les méthodes CRUD de BaseAIStorage sont correctement
implémentées sur SQLite. Utilise une base en mémoire (:memory:) pour
l'isolation totale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pyworkflow_engine.adapters.ai.storage.sqlite import SQLiteAIStorage
from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.conversation import Conversation
from pyworkflow_engine.models.ai.execution import Execution, ExecutionStep
from pyworkflow_engine.models.ai.graph import Graph, GraphEdge, GraphNode
from pyworkflow_engine.models.ai.knowledge import KnowledgeSource
from pyworkflow_engine.models.ai.memory import AgentMemory
from pyworkflow_engine.models.ai.message import Message
from pyworkflow_engine.models.ai.provider import LLMProviderConfig
from pyworkflow_engine.models.ai.skill import AgentSkillAssignment, Skill
from pyworkflow_engine.models.ai.tool import ToolDefinition
from pyworkflow_engine.models.ai.types import (
    AIStepType,
    AgentRole,
    ExecutionStatus,
    IndexStatus,
    MemoryType,
    MessageRole,
    NodeType,
    Proficiency,
    ProviderType,
    SkillCategory,
    SourceType,
    ToolType,
)
from pyworkflow_engine.models.enums import RunStatus


@pytest.fixture()
def storage() -> SQLiteAIStorage:
    """Base SQLite en mémoire, isolée par test."""
    return SQLiteAIStorage(":memory:")


def _make_provider(**kwargs) -> LLMProviderConfig:
    return LLMProviderConfig(
        name=kwargs.get("name", "Test Provider"),
        provider_type=kwargs.get("provider_type", ProviderType.OPENAI),
        default_model=kwargs.get("default_model", "gpt-4o"),
    )


def _make_agent(provider_id: str, **kwargs) -> Agent:
    return Agent(
        name=kwargs.get("name", "Test Agent"),
        slug=kwargs.get("slug", "test-agent"),
        provider_id=provider_id,
        role=kwargs.get("role", AgentRole.ASSISTANT),
        owner_id=kwargs.get("owner_id", None),
        is_active=kwargs.get("is_active", True),
    )


def _make_skill(**kwargs) -> Skill:
    return Skill(
        key=kwargs.get("key", "research"),
        name=kwargs.get("name", "Research Skill"),
        category=kwargs.get("category", SkillCategory.RESEARCH),
        is_active=kwargs.get("is_active", True),
    )


def _make_execution(agent_id: str, **kwargs) -> Execution:
    return Execution(
        agent_id=agent_id,
        status=kwargs.get("status", ExecutionStatus.PENDING),
    )


# ── Providers ─────────────────────────────────────────────────────────────────


class TestProviders:
    def test_save_and_get(self, storage):
        p = _make_provider()
        saved = storage.save_provider(p)
        assert saved.id == p.id
        loaded = storage.get_provider(p.id)
        assert loaded is not None
        assert loaded.name == p.name

    def test_get_missing(self, storage):
        assert storage.get_provider("nonexistent") is None

    def test_get_by_name(self, storage):
        p = _make_provider(name="MyProvider")
        storage.save_provider(p)
        found = storage.get_provider_by_name("MyProvider")
        assert found is not None
        assert found.id == p.id

    def test_list_providers(self, storage):
        storage.save_provider(_make_provider(name="P1"))
        storage.save_provider(_make_provider(name="P2"))
        all_p = storage.list_providers()
        assert len(all_p) == 2

    def test_list_filter_is_active(self, storage):
        p_active = LLMProviderConfig(
            name="Active",
            provider_type=ProviderType.OPENAI,
            default_model="gpt-4o",
            is_active=True,
        )
        p_inactive = LLMProviderConfig(
            name="Inactive",
            provider_type=ProviderType.ANTHROPIC,
            default_model="claude-3",
            is_active=False,
        )
        storage.save_provider(p_active)
        storage.save_provider(p_inactive)
        assert len(storage.list_providers(is_active=True)) == 1
        assert len(storage.list_providers(is_active=False)) == 1

    def test_delete_provider(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        assert storage.delete_provider(p.id) is True
        assert storage.get_provider(p.id) is None

    def test_delete_missing(self, storage):
        assert storage.delete_provider("ghost") is False

    def test_upsert(self, storage):
        p = _make_provider(name="Original")
        storage.save_provider(p)
        p.name = "Updated"
        storage.save_provider(p)
        loaded = storage.get_provider(p.id)
        assert loaded.name == "Updated"


# ── Agents ────────────────────────────────────────────────────────────────────


class TestAgents:
    def test_save_and_get(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        a = _make_agent(p.id)
        storage.save_agent(a)
        loaded = storage.get_agent(a.id)
        assert loaded is not None
        assert loaded.name == a.name

    def test_get_by_slug(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        a = _make_agent(p.id, slug="my-slug")
        storage.save_agent(a)
        found = storage.get_agent_by_slug("my-slug")
        assert found is not None
        assert found.id == a.id

    def test_list_with_filters(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        a1 = _make_agent(p.id, role=AgentRole.RESEARCHER, owner_id="user-1")
        a2 = _make_agent(p.id, role=AgentRole.CODER, owner_id="user-2")
        a3 = _make_agent(
            p.id, role=AgentRole.RESEARCHER, owner_id="user-1", is_active=False
        )
        for a in [a1, a2, a3]:
            storage.save_agent(a)

        assert len(storage.list_agents()) == 3
        assert len(storage.list_agents(owner_id="user-1")) == 2
        assert len(storage.list_agents(role=AgentRole.RESEARCHER)) == 2
        assert len(storage.list_agents(is_active=True)) == 2

    def test_delete_agent(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        a = _make_agent(p.id)
        storage.save_agent(a)
        assert storage.delete_agent(a.id) is True
        assert storage.get_agent(a.id) is None


# ── Conversations & Messages ──────────────────────────────────────────────────


class TestConversationsAndMessages:
    def test_save_and_get_conversation(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        a = _make_agent(p.id)
        storage.save_agent(a)
        conv = Conversation(agent_id=a.id, title="Test chat")
        storage.save_conversation(conv)
        loaded = storage.get_conversation(conv.id)
        assert loaded is not None
        assert loaded.title == "Test chat"

    def test_list_conversations_by_agent(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        a1 = _make_agent(p.id, slug="a1")
        a2 = _make_agent(p.id, slug="a2")
        storage.save_agent(a1)
        storage.save_agent(a2)
        storage.save_conversation(Conversation(agent_id=a1.id))
        storage.save_conversation(Conversation(agent_id=a1.id))
        storage.save_conversation(Conversation(agent_id=a2.id))
        assert len(storage.list_conversations(agent_id=a1.id)) == 2
        assert len(storage.list_conversations(agent_id=a2.id)) == 1

    def test_save_and_get_messages(self, storage):
        conv = Conversation(agent_id="agent-x")
        storage.save_conversation(conv)
        m1 = Message(conversation_id=conv.id, role=MessageRole.USER, content="Hello")
        m2 = Message(
            conversation_id=conv.id, role=MessageRole.ASSISTANT, content="Hi there"
        )
        storage.save_message(m1)
        storage.save_message(m2)
        msgs = storage.get_messages(conv.id)
        assert len(msgs) == 2
        assert msgs[0].content == "Hello"

    def test_message_pagination(self, storage):
        conv = Conversation(agent_id="agent-x")
        storage.save_conversation(conv)
        for i in range(5):
            storage.save_message(
                Message(
                    conversation_id=conv.id, role=MessageRole.USER, content=f"msg {i}"
                )
            )
        assert len(storage.get_messages(conv.id, limit=2)) == 2
        assert len(storage.get_messages(conv.id, offset=3)) == 2

    def test_count_messages(self, storage):
        conv = Conversation(agent_id="agent-x")
        storage.save_conversation(conv)
        for _ in range(3):
            storage.save_message(
                Message(conversation_id=conv.id, role=MessageRole.USER, content="x")
            )
        assert storage.count_messages(conv.id) == 3
        assert storage.count_messages("nonexistent") == 0

    def test_delete_conversation(self, storage):
        conv = Conversation(agent_id="a")
        storage.save_conversation(conv)
        assert storage.delete_conversation(conv.id) is True
        assert storage.get_conversation(conv.id) is None


# ── Memory ────────────────────────────────────────────────────────────────────


class TestMemory:
    def test_save_and_get(self, storage):
        mem = AgentMemory(
            agent_id="agent-1",
            key="user_language",
            content="French",
            memory_type=MemoryType.LONG_TERM,
        )
        storage.save_memory(mem)
        loaded = storage.get_memory("agent-1", "user_language")
        assert loaded is not None
        assert loaded.content == "French"

    def test_get_memory_missing(self, storage):
        assert storage.get_memory("agent-x", "no-key") is None

    def test_list_memories(self, storage):
        storage.save_memory(
            AgentMemory(
                agent_id="a1", key="k1", content="c1", memory_type=MemoryType.LONG_TERM
            )
        )
        storage.save_memory(
            AgentMemory(
                agent_id="a1", key="k2", content="c2", memory_type=MemoryType.SHORT_TERM
            )
        )
        storage.save_memory(
            AgentMemory(
                agent_id="a2", key="k3", content="c3", memory_type=MemoryType.LONG_TERM
            )
        )

        all_a1 = storage.list_memories("a1")
        assert len(all_a1) == 2

        lt_a1 = storage.list_memories("a1", memory_type=MemoryType.LONG_TERM)
        assert len(lt_a1) == 1 and lt_a1[0].key == "k1"

    def test_upsert_memory(self, storage):
        mem = AgentMemory(
            agent_id="a1", key="pref", content="old", memory_type=MemoryType.LONG_TERM
        )
        storage.save_memory(mem)
        mem.content = "new"
        storage.save_memory(mem)
        loaded = storage.get_memory("a1", "pref")
        assert loaded.content == "new"

    def test_delete_memory(self, storage):
        mem = AgentMemory(
            agent_id="a1", key="k", content="v", memory_type=MemoryType.LONG_TERM
        )
        storage.save_memory(mem)
        assert storage.delete_memory(mem.id) is True
        assert storage.get_memory("a1", "k") is None

    def test_delete_expired_memories(self, storage):
        past = datetime.now(UTC) - timedelta(hours=1)
        future = datetime.now(UTC) + timedelta(hours=1)

        expired = AgentMemory(
            agent_id="a1",
            key="old",
            content="x",
            memory_type=MemoryType.SHORT_TERM,
            expires_at=past,
        )
        valid = AgentMemory(
            agent_id="a1",
            key="new",
            content="y",
            memory_type=MemoryType.LONG_TERM,
            expires_at=future,
        )
        no_exp = AgentMemory(
            agent_id="a1", key="forever", content="z", memory_type=MemoryType.LONG_TERM
        )

        storage.save_memory(expired)
        storage.save_memory(valid)
        storage.save_memory(no_exp)

        deleted = storage.delete_expired_memories()
        assert deleted == 1
        assert storage.get_memory("a1", "old") is None
        assert storage.get_memory("a1", "new") is not None
        assert storage.get_memory("a1", "forever") is not None


# ── Tools ─────────────────────────────────────────────────────────────────────


class TestTools:
    def test_save_get_delete(self, storage):
        tool = ToolDefinition(
            key="web_search",
            name="Web Search",
            tool_type=ToolType.API,
        )
        storage.save_tool(tool)
        assert storage.get_tool(tool.id) is not None
        assert storage.get_tool_by_key("web_search") is not None
        assert storage.delete_tool(tool.id) is True
        assert storage.get_tool(tool.id) is None

    def test_list_tools_active_filter(self, storage):
        t1 = ToolDefinition(
            key="t1", name="T1", tool_type=ToolType.FUNCTION, is_active=True
        )
        t2 = ToolDefinition(
            key="t2", name="T2", tool_type=ToolType.FUNCTION, is_active=False
        )
        storage.save_tool(t1)
        storage.save_tool(t2)
        assert len(storage.list_tools(is_active=True)) == 1
        assert len(storage.list_tools(is_active=False)) == 1
        assert len(storage.list_tools()) == 2

    def test_list_tools_for_agent(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        t = ToolDefinition(key="tool-x", name="Tool X", tool_type=ToolType.FUNCTION)
        storage.save_tool(t)
        a = Agent(name="A", slug="a", provider_id=p.id, tool_ids=[t.id])
        storage.save_agent(a)
        tools = storage.list_tools_for_agent(a.id)
        assert len(tools) == 1 and tools[0].key == "tool-x"


# ── Graphs ────────────────────────────────────────────────────────────────────


class TestGraphs:
    def test_save_get_by_slug(self, storage):
        g = Graph(
            name="Test Graph",
            slug="test-graph",
            agent_id="agent-x",
            nodes=[GraphNode(node_id="n1", node_type=NodeType.AGENT)],
            edges=[],
        )
        storage.save_graph(g)
        found = storage.get_graph_by_slug("test-graph")
        assert found is not None
        assert len(found.nodes) == 1

    def test_list_graphs_by_agent(self, storage):
        storage.save_graph(Graph(name="G1", slug="g1", agent_id="a1"))
        storage.save_graph(Graph(name="G2", slug="g2", agent_id="a1"))
        storage.save_graph(Graph(name="G3", slug="g3", agent_id="a2"))
        assert len(storage.list_graphs(agent_id="a1")) == 2

    def test_delete_graph(self, storage):
        g = Graph(name="G", slug="g", agent_id="a")
        storage.save_graph(g)
        assert storage.delete_graph(g.id) is True
        assert storage.get_graph(g.id) is None


# ── Knowledge Sources ─────────────────────────────────────────────────────────


class TestKnowledgeSources:
    def test_save_get_delete(self, storage):
        source = KnowledgeSource(
            name="Test Docs",
            source_type=SourceType.DOCUMENT,
            index_status=IndexStatus.PENDING,
        )
        storage.save_knowledge_source(source)
        loaded = storage.get_knowledge_source(source.id)
        assert loaded is not None
        assert loaded.name == "Test Docs"
        assert storage.delete_knowledge_source(source.id) is True
        assert storage.get_knowledge_source(source.id) is None

    def test_list_knowledge_sources(self, storage):
        for i in range(3):
            storage.save_knowledge_source(
                KnowledgeSource(
                    name=f"Source {i}",
                    source_type=SourceType.TEXT,
                    index_status=IndexStatus.PENDING,
                )
            )
        assert len(storage.list_knowledge_sources()) == 3


# ── Transaction context manager ───────────────────────────────────────────────


class TestTransaction:
    def test_transaction_commit(self, storage):
        mem = AgentMemory(
            agent_id="a", key="k", content="v", memory_type=MemoryType.LONG_TERM
        )
        with storage.transaction():
            storage.save_memory(mem)
        assert storage.get_memory("a", "k") is not None

    def test_transaction_rollback_on_error(self, storage):
        mem = AgentMemory(
            agent_id="a",
            key="rollback-key",
            content="v",
            memory_type=MemoryType.LONG_TERM,
        )
        with pytest.raises(RuntimeError):
            with storage.transaction():
                storage.save_memory(mem)
                raise RuntimeError("forced rollback")
        # After rollback, memory should not be found
        assert storage.get_memory("a", "rollback-key") is None


# ── Context manager (close) ───────────────────────────────────────────────────


class TestContextManager:
    def test_with_statement(self):
        with SQLiteAIStorage(":memory:") as s:
            p = _make_provider()
            s.save_provider(p)
            assert s.get_provider(p.id) is not None
        # After close, the connection is gone — no assertion needed

    def test_close_idempotent(self):
        s = SQLiteAIStorage(":memory:")
        s.close()
        s.close()  # Should not raise


# ── Skills ────────────────────────────────────────────────────────────────────


class TestSkills:
    def test_save_and_get(self, storage):
        skill = _make_skill()
        storage.save_skill(skill)
        loaded = storage.get_skill(skill.id)
        assert loaded is not None
        assert loaded.key == "research"

    def test_get_missing(self, storage):
        assert storage.get_skill("no-such-id") is None

    def test_list_skills(self, storage):
        storage.save_skill(_make_skill(key="s1", name="S1"))
        storage.save_skill(_make_skill(key="s2", name="S2"))
        assert len(storage.list_skills()) == 2

    def test_list_skills_active_filter(self, storage):
        storage.save_skill(_make_skill(key="active", name="A", is_active=True))
        storage.save_skill(_make_skill(key="inactive", name="I", is_active=False))
        assert len(storage.list_skills(is_active=True)) == 1
        assert len(storage.list_skills(is_active=False)) == 1

    def test_upsert_skill(self, storage):
        skill = _make_skill(name="Original")
        storage.save_skill(skill)
        skill.name = "Updated"
        storage.save_skill(skill)
        assert storage.get_skill(skill.id).name == "Updated"

    def test_delete_skill(self, storage):
        skill = _make_skill()
        storage.save_skill(skill)
        assert storage.delete_skill(skill.id) is True
        assert storage.get_skill(skill.id) is None

    def test_delete_missing_skill(self, storage):
        assert storage.delete_skill("ghost") is False

    def test_skill_assignment_save_and_list(self, storage):
        skill = _make_skill()
        storage.save_skill(skill)
        assignment = AgentSkillAssignment(
            agent_id="agent-1",
            skill_id=skill.id,
            proficiency=Proficiency.ADVANCED,
        )
        storage.save_skill_assignment(assignment)
        assignments = storage.list_skill_assignments_for_agent("agent-1")
        assert len(assignments) == 1
        assert assignments[0].skill_id == skill.id
        assert assignments[0].proficiency == Proficiency.ADVANCED

    def test_list_assignments_empty_for_unknown_agent(self, storage):
        assert storage.list_skill_assignments_for_agent("ghost") == []

    def test_multiple_assignments_for_agent(self, storage):
        s1 = _make_skill(key="sk1", name="Skill 1")
        s2 = _make_skill(key="sk2", name="Skill 2")
        storage.save_skill(s1)
        storage.save_skill(s2)
        storage.save_skill_assignment(
            AgentSkillAssignment(agent_id="a1", skill_id=s1.id)
        )
        storage.save_skill_assignment(
            AgentSkillAssignment(agent_id="a1", skill_id=s2.id)
        )
        storage.save_skill_assignment(
            AgentSkillAssignment(agent_id="a2", skill_id=s1.id)
        )
        assert len(storage.list_skill_assignments_for_agent("a1")) == 2
        assert len(storage.list_skill_assignments_for_agent("a2")) == 1

    def test_upsert_assignment(self, storage):
        skill = _make_skill()
        storage.save_skill(skill)
        assignment = AgentSkillAssignment(
            agent_id="a1", skill_id=skill.id, proficiency=Proficiency.BASIC
        )
        storage.save_skill_assignment(assignment)
        assignment.proficiency = Proficiency.EXPERT
        storage.save_skill_assignment(assignment)
        loaded = storage.list_skill_assignments_for_agent("a1")
        assert loaded[0].proficiency == Proficiency.EXPERT


# ── Executions ────────────────────────────────────────────────────────────────


class TestExecutions:
    def test_save_and_get(self, storage):
        ex = _make_execution("agent-1")
        storage.save_execution(ex)
        loaded = storage.get_execution(ex.id)
        assert loaded is not None
        assert loaded.agent_id == "agent-1"
        assert loaded.status == ExecutionStatus.PENDING

    def test_get_missing(self, storage):
        assert storage.get_execution("no-such-id") is None

    def test_upsert_updates_status(self, storage):
        ex = _make_execution("agent-1")
        storage.save_execution(ex)
        ex.status = ExecutionStatus.SUCCESS
        storage.save_execution(ex)
        assert storage.get_execution(ex.id).status == ExecutionStatus.SUCCESS

    def test_list_all(self, storage):
        storage.save_execution(_make_execution("a1"))
        storage.save_execution(_make_execution("a1"))
        storage.save_execution(_make_execution("a2"))
        assert len(storage.list_executions()) == 3

    def test_list_filter_agent(self, storage):
        storage.save_execution(_make_execution("a1"))
        storage.save_execution(_make_execution("a1"))
        storage.save_execution(_make_execution("a2"))
        assert len(storage.list_executions(agent_id="a1")) == 2
        assert len(storage.list_executions(agent_id="a2")) == 1

    def test_list_filter_status(self, storage):
        storage.save_execution(_make_execution("a1", status=ExecutionStatus.PENDING))
        storage.save_execution(_make_execution("a1", status=ExecutionStatus.SUCCESS))
        storage.save_execution(_make_execution("a1", status=ExecutionStatus.FAILED))
        assert len(storage.list_executions(status=ExecutionStatus.PENDING)) == 1
        assert len(storage.list_executions(status=ExecutionStatus.SUCCESS)) == 1
        assert len(storage.list_executions(status=ExecutionStatus.FAILED)) == 1

    def test_execution_steps_saved_and_ordered(self, storage):
        ex = _make_execution("agent-1")
        storage.save_execution(ex)
        step3 = ExecutionStep(
            execution_id=ex.id, step_type=AIStepType.LLM_CALL, order=3
        )
        step1 = ExecutionStep(
            execution_id=ex.id, step_type=AIStepType.TOOL_CALL, order=1
        )
        step2 = ExecutionStep(
            execution_id=ex.id, step_type=AIStepType.LLM_CALL, order=2
        )
        for s in [step3, step1, step2]:
            storage.save_execution_step(s)
        steps = storage.get_execution_steps(ex.id)
        assert len(steps) == 3
        assert [s.order for s in steps] == [1, 2, 3]

    def test_get_steps_empty(self, storage):
        assert storage.get_execution_steps("no-execution") == []

    def test_upsert_step(self, storage):
        ex = _make_execution("agent-1")
        storage.save_execution(ex)
        step = ExecutionStep(execution_id=ex.id, step_type=AIStepType.LLM_CALL, order=1)
        storage.save_execution_step(step)
        step.order = 99
        storage.save_execution_step(step)
        steps = storage.get_execution_steps(ex.id)
        assert steps[0].order == 99


# ── Tools — edge cases ────────────────────────────────────────────────────────


class TestToolsEdgeCases:
    def test_list_tools_for_agent_no_tool_ids(self, storage):
        p = _make_provider()
        storage.save_provider(p)
        a = Agent(name="A", slug="a-no-tools", provider_id=p.id)
        storage.save_agent(a)
        assert storage.list_tools_for_agent(a.id) == []

    def test_list_tools_for_missing_agent(self, storage):
        assert storage.list_tools_for_agent("ghost") == []
