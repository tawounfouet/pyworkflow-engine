"""
Tests d'intégration — UnifiedStorage façade (ADR-017).

Teste le cycle complet : migration DDL → CRUD via les raccourcis nommés
→ sérialisation/désérialisation des modèles IA réels.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from pyworkflow_engine.adapters.storage.unified import UnifiedStorage
from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.conversation import Conversation
from pyworkflow_engine.models.ai.execution import Execution, ExecutionStep
from pyworkflow_engine.models.ai.graph import Graph, GraphEdge, GraphNode
from pyworkflow_engine.models.ai.knowledge import Chunk, Document, KnowledgeSource
from pyworkflow_engine.models.ai.memory import AgentMemory
from pyworkflow_engine.models.ai.message import Message, TokenUsage, ToolCall
from pyworkflow_engine.models.ai.provider import LLMProviderConfig
from pyworkflow_engine.models.ai.skill import AgentSkillAssignment, Skill
from pyworkflow_engine.models.ai.tool import ToolDefinition
from pyworkflow_engine.models.ai.types import (
    AgentRole,
    ConversationStatus,
    GraphStatus,
    IndexStatus,
    MemoryType,
    MessageRole,
    ProviderType,
    SkillCategory,
    SourceType,
    ToolType,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def storage() -> UnifiedStorage:
    """UnifiedStorage avec base SQLite temporaire, tables migrées."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        s = UnifiedStorage(db_path)
        s.migrate()
        yield s
        s.close()


@pytest.fixture()
def provider(storage: UnifiedStorage) -> LLMProviderConfig:
    """Provider de référence (nécessaire pour les FK agents)."""
    p = LLMProviderConfig(
        id="prov-1",
        name="Test OpenAI",
        provider_type=ProviderType.OPENAI,
        default_model="gpt-4o",
    )
    return storage.save_provider(p)


@pytest.fixture()
def agent(storage: UnifiedStorage, provider: LLMProviderConfig) -> Agent:
    """Agent de référence."""
    a = Agent(
        id="agent-1",
        name="Test Bot",
        slug="test-bot",
        role=AgentRole.ASSISTANT,
        provider_id=provider.id,
        system_prompt="You are a test assistant.",
        config=AgentConfig(max_iterations=5),
        tool_ids=["tool-1"],
    )
    return storage.save_agent(a)


@pytest.fixture()
def conversation(storage: UnifiedStorage, agent: Agent) -> Conversation:
    """Conversation de référence."""
    c = Conversation(
        id="conv-1",
        title="Test Conversation",
        agent_id=agent.id,
        owner_id="user-1",
    )
    return storage.save_conversation(c)


# ── Migration Tests ──────────────────────────────────────────────────────────


class TestMigration:
    """Tests pour migrate() et get_table_names()."""

    def test_migrate_creates_tables(self, storage: UnifiedStorage):
        """migrate() crée toutes les tables attendues."""
        tables = storage.get_table_names()
        expected = {
            "ai_providers",
            "ai_agents",
            "ai_tools",
            "ai_skills",
            "ai_conversations",
            "ai_messages",
            "ai_executions",
            "ai_execution_steps",
            "ai_graphs",
            "ai_memories",
            "ai_agent_skill_assignments",
            "ai_knowledge_sources",
            "ai_documents",
            "ai_chunks",
            "log_entries",
        }
        assert expected.issubset(set(tables))

    def test_migrate_idempotent(self, storage: UnifiedStorage):
        """migrate() est idempotent — appeler deux fois ne casse rien."""
        statements1 = storage.migrate()
        statements2 = storage.migrate()
        # Les deux appels retournent des statements, mais la DB reste cohérente
        assert len(statements1) > 0
        assert len(statements2) > 0

    def test_health_check(self, storage: UnifiedStorage):
        """health_check() retourne des infos structurées."""
        health = storage.health_check()
        assert "database_path" in health
        assert "tables" in health
        assert "row_counts" in health
        assert "registered_models" in health
        assert len(health["tables"]) >= 14


# ── Provider Tests ───────────────────────────────────────────────────────────


class TestProviderCRUD:
    """Tests CRUD pour les providers."""

    def test_save_and_get_provider(self, storage: UnifiedStorage):
        p = LLMProviderConfig(
            id="p-test",
            name="Claude Provider",
            provider_type=ProviderType.ANTHROPIC,
            default_model="claude-3-opus",
        )
        storage.save_provider(p)

        found = storage.get_provider("p-test")
        assert found is not None
        assert found.name == "Claude Provider"
        assert found.provider_type == ProviderType.ANTHROPIC
        assert found.default_model == "claude-3-opus"

    def test_get_provider_by_name(
        self, storage: UnifiedStorage, provider: LLMProviderConfig
    ):
        found = storage.get_provider_by_name("Test OpenAI")
        assert found is not None
        assert found.id == provider.id

    def test_list_providers(self, storage: UnifiedStorage):
        storage.save_provider(
            LLMProviderConfig(
                id="lp-1",
                name="A",
                provider_type=ProviderType.OPENAI,
                default_model="gpt-4o",
                is_active=True,
            )
        )
        storage.save_provider(
            LLMProviderConfig(
                id="lp-2",
                name="B",
                provider_type=ProviderType.ANTHROPIC,
                default_model="claude",
                is_active=False,
            )
        )

        all_providers = storage.list_providers()
        assert len(all_providers) == 2

        active = storage.list_providers(is_active=True)
        assert len(active) == 1
        assert active[0].id == "lp-1"

    def test_delete_provider(
        self, storage: UnifiedStorage, provider: LLMProviderConfig
    ):
        assert storage.delete_provider(provider.id) is True
        assert storage.get_provider(provider.id) is None


# ── Agent Tests ──────────────────────────────────────────────────────────────


class TestAgentCRUD:
    """Tests CRUD pour les agents."""

    def test_save_and_get_agent(self, storage: UnifiedStorage, agent: Agent):
        found = storage.get_agent("agent-1")
        assert found is not None
        assert found.name == "Test Bot"
        assert found.slug == "test-bot"
        assert found.role == AgentRole.ASSISTANT
        assert found.config.max_iterations == 5
        assert found.tool_ids == ["tool-1"]

    def test_get_agent_by_slug(self, storage: UnifiedStorage, agent: Agent):
        found = storage.get_agent_by_slug("test-bot")
        assert found is not None
        assert found.id == agent.id

    def test_list_agents_with_filters(
        self, storage: UnifiedStorage, provider: LLMProviderConfig
    ):
        storage.save_agent(
            Agent(
                id="la-1",
                name="A1",
                role=AgentRole.RESEARCHER,
                provider_id=provider.id,
                owner_id="u1",
            )
        )
        storage.save_agent(
            Agent(
                id="la-2",
                name="A2",
                role=AgentRole.CODER,
                provider_id=provider.id,
                owner_id="u2",
            )
        )

        by_role = storage.list_agents(role=AgentRole.RESEARCHER)
        assert len(by_role) == 1

        by_owner = storage.list_agents(owner_id="u1")
        assert len(by_owner) == 1

    def test_delete_agent(self, storage: UnifiedStorage, agent: Agent):
        assert storage.delete_agent(agent.id) is True
        assert storage.get_agent(agent.id) is None


# ── Tool Tests ───────────────────────────────────────────────────────────────


class TestToolCRUD:
    """Tests CRUD pour les outils."""

    def test_save_and_get_tool(self, storage: UnifiedStorage):
        tool = ToolDefinition(
            id="tool-1",
            key="web_search",
            name="Web Search",
            description="Search the web",
            tool_type=ToolType.API,
            parameters_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        )
        storage.save_tool(tool)

        found = storage.get_tool("tool-1")
        assert found is not None
        assert found.key == "web_search"
        assert found.tool_type == ToolType.API
        assert "properties" in found.parameters_schema

    def test_get_tool_by_key(self, storage: UnifiedStorage):
        storage.save_tool(
            ToolDefinition(
                id="tk-1",
                key="calculator",
                name="Calc",
            )
        )
        found = storage.get_tool_by_key("calculator")
        assert found is not None
        assert found.id == "tk-1"

    def test_list_tools_for_agent(self, storage: UnifiedStorage, agent: Agent):
        storage.save_tool(ToolDefinition(id="tool-1", key="t1", name="T1"))
        storage.save_tool(ToolDefinition(id="tool-2", key="t2", name="T2"))

        # agent fixture has tool_ids=["tool-1"]
        tools = storage.list_tools_for_agent(agent.id)
        assert len(tools) == 1
        assert tools[0].id == "tool-1"


# ── Conversation + Message Tests ─────────────────────────────────────────────


class TestConversationAndMessages:
    """Tests CRUD pour les conversations et messages."""

    def test_save_and_get_conversation(
        self, storage: UnifiedStorage, conversation: Conversation
    ):
        found = storage.get_conversation("conv-1")
        assert found is not None
        assert found.title == "Test Conversation"
        assert found.status == ConversationStatus.ACTIVE

    def test_list_conversations(self, storage: UnifiedStorage, agent: Agent):
        storage.save_conversation(
            Conversation(
                id="lc-1",
                agent_id=agent.id,
                owner_id="u1",
            )
        )
        storage.save_conversation(
            Conversation(
                id="lc-2",
                agent_id=agent.id,
                owner_id="u2",
            )
        )

        all_convs = storage.list_conversations(agent_id=agent.id)
        assert len(all_convs) == 2

        by_owner = storage.list_conversations(owner_id="u1")
        assert len(by_owner) == 1

    def test_save_and_get_messages(
        self, storage: UnifiedStorage, conversation: Conversation
    ):
        msg1 = Message(
            id="msg-1",
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="Hello!",
        )
        msg2 = Message(
            id="msg-2",
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="Hi there!",
            token_usage=TokenUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )
        storage.save_message(msg1)
        storage.save_message(msg2)

        messages = storage.get_messages(conversation.id)
        assert len(messages) == 2

    def test_message_with_tool_calls(
        self, storage: UnifiedStorage, conversation: Conversation
    ):
        msg = Message(
            id="msg-tc",
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[
                ToolCall(id="call-1", name="web_search", arguments={"q": "test"}),
            ],
        )
        storage.save_message(msg)

        found = storage.get_messages(conversation.id)
        assert len(found) == 1
        assert len(found[0].tool_calls) == 1
        assert found[0].tool_calls[0].name == "web_search"

    def test_count_messages(self, storage: UnifiedStorage, conversation: Conversation):
        for i in range(3):
            storage.save_message(
                Message(
                    id=f"cm-{i}",
                    conversation_id=conversation.id,
                    role=MessageRole.USER,
                    content=f"Message {i}",
                )
            )
        assert storage.count_messages(conversation.id) == 3


# ── Execution Tests ──────────────────────────────────────────────────────────


class TestExecutionCRUD:
    """Tests CRUD pour les exécutions."""

    def test_save_and_get_execution(self, storage: UnifiedStorage, agent: Agent):
        exc = Execution(
            id="exec-1",
            agent_id=agent.id,
            input_data={"prompt": "Analyze this"},
            token_usage=TokenUsage(total_tokens=100),
        )
        storage.save_execution(exc)

        found = storage.get_execution("exec-1")
        assert found is not None
        assert found.agent_id == agent.id
        assert found.token_usage.total_tokens == 100

    def test_execution_steps(self, storage: UnifiedStorage, agent: Agent):
        from pyworkflow_engine.models.ai.types import AIStepType

        exc = Execution(id="exec-s", agent_id=agent.id)
        storage.save_execution(exc)

        for i in range(3):
            step = ExecutionStep(
                id=f"step-{i}",
                execution_id="exec-s",
                step_type=AIStepType.LLM_CALL,
                order=i,
            )
            storage.save_execution_step(step)

        steps = storage.get_execution_steps("exec-s")
        assert len(steps) == 3
        # Should be ordered by 'order'
        assert [s.order for s in steps] == [0, 1, 2]


# ── Graph Tests ──────────────────────────────────────────────────────────────


class TestGraphCRUD:
    """Tests CRUD pour les graphs."""

    def test_save_and_get_graph(self, storage: UnifiedStorage, agent: Agent):
        graph = Graph(
            id="graph-1",
            name="Test Pipeline",
            slug="test-pipeline",
            agent_id=agent.id,
            nodes=[
                GraphNode(node_id="start", name="Start"),
                GraphNode(node_id="end", name="End"),
            ],
            edges=[
                GraphEdge(source_node_id="start", target_node_id="end"),
            ],
            entry_node_id="start",
            status=GraphStatus.DRAFT,
        )
        storage.save_graph(graph)

        found = storage.get_graph("graph-1")
        assert found is not None
        assert found.name == "Test Pipeline"
        assert len(found.nodes) == 2
        assert len(found.edges) == 1
        assert found.entry_node_id == "start"

    def test_get_graph_by_slug(self, storage: UnifiedStorage, agent: Agent):
        storage.save_graph(
            Graph(
                id="gs-1",
                name="G",
                slug="my-graph",
                agent_id=agent.id,
            )
        )
        found = storage.get_graph_by_slug("my-graph")
        assert found is not None
        assert found.id == "gs-1"


# ── Memory Tests ─────────────────────────────────────────────────────────────


class TestMemoryCRUD:
    """Tests CRUD pour les mémoires d'agents."""

    def test_save_and_get_memory(self, storage: UnifiedStorage, agent: Agent):
        mem = AgentMemory(
            id="mem-1",
            agent_id=agent.id,
            key="user_pref",
            content='{"lang": "fr"}',
            memory_type=MemoryType.LONG_TERM,
            relevance_score=0.9,
        )
        storage.save_memory(mem)

        found = storage.get_memory(agent.id, "user_pref")
        assert found is not None
        assert found.content == '{"lang": "fr"}'
        assert found.relevance_score == 0.9

    def test_list_memories_by_type(self, storage: UnifiedStorage, agent: Agent):
        storage.save_memory(
            AgentMemory(
                id="mt-1",
                agent_id=agent.id,
                key="k1",
                content="c1",
                memory_type=MemoryType.LONG_TERM,
            )
        )
        storage.save_memory(
            AgentMemory(
                id="mt-2",
                agent_id=agent.id,
                key="k2",
                content="c2",
                memory_type=MemoryType.SHORT_TERM,
            )
        )

        lt = storage.list_memories(agent.id, memory_type=MemoryType.LONG_TERM)
        assert len(lt) == 1
        assert lt[0].id == "mt-1"

    def test_delete_memory(self, storage: UnifiedStorage, agent: Agent):
        storage.save_memory(
            AgentMemory(
                id="dm-1",
                agent_id=agent.id,
                key="k",
                content="c",
            )
        )
        assert storage.delete_memory("dm-1") is True
        assert storage.get_memory(agent.id, "k") is None


# ── Skill Tests ──────────────────────────────────────────────────────────────


class TestSkillCRUD:
    """Tests CRUD pour les skills."""

    def test_save_and_get_skill(self, storage: UnifiedStorage):
        skill = Skill(
            id="sk-1",
            key="research",
            name="Research",
            category=SkillCategory.RESEARCH,
        )
        storage.save_skill(skill)

        found = storage.get_skill("sk-1")
        assert found is not None
        assert found.key == "research"
        assert found.category == SkillCategory.RESEARCH

    def test_skill_assignment(self, storage: UnifiedStorage, agent: Agent):
        skill = Skill(id="sk-a", key="coding", name="Coding")
        storage.save_skill(skill)

        assignment = AgentSkillAssignment(
            id="asa-1",
            agent_id=agent.id,
            skill_id="sk-a",
        )
        storage.save_skill_assignment(assignment)

        assignments = storage.list_skill_assignments_for_agent(agent.id)
        assert len(assignments) == 1
        assert assignments[0].skill_id == "sk-a"


# ── Knowledge Tests ──────────────────────────────────────────────────────────


class TestKnowledgeCRUD:
    """Tests CRUD pour les sources de connaissance."""

    def test_save_and_get_knowledge_source(self, storage: UnifiedStorage):
        source = KnowledgeSource(
            id="ks-1",
            name="Company Docs",
            source_type=SourceType.DOCUMENT,
            index_status=IndexStatus.PENDING,
        )
        storage.save_knowledge_source(source)

        found = storage.get_knowledge_source("ks-1")
        assert found is not None
        assert found.name == "Company Docs"
        assert found.source_type == SourceType.DOCUMENT

    def test_document_and_chunk(self, storage: UnifiedStorage):
        source = KnowledgeSource(
            id="ks-dc",
            name="Test",
            source_type=SourceType.DOCUMENT,
        )
        storage.save_knowledge_source(source)

        doc = Document(id="doc-1", source_id="ks-dc", title="Doc 1", content="Hello")
        storage.documents.create(doc)

        chunk = Chunk(
            id="ch-1",
            document_id="doc-1",
            content="Hello chunk",
            chunk_index=0,
        )
        storage.chunks.create(chunk)

        # Retrieve
        docs = storage.documents.filter(source_id="ks-dc")
        assert len(docs) == 1
        assert docs[0].title == "Doc 1"

        chunks = storage.chunks.filter(document_id="doc-1")
        assert len(chunks) == 1
        assert chunks[0].content == "Hello chunk"


# ── Transaction Tests ────────────────────────────────────────────────────────


class TestTransactions:
    """Tests pour le context manager transactionnel."""

    def test_transaction_commit(self, storage: UnifiedStorage):
        with storage.transaction():
            storage.save_provider(
                LLMProviderConfig(
                    id="tx-1",
                    name="TX",
                    provider_type=ProviderType.OPENAI,
                    default_model="gpt-4o",
                )
            )
        assert storage.get_provider("tx-1") is not None

    def test_transaction_rollback_on_error(self, storage: UnifiedStorage):
        try:
            with storage.transaction():
                storage.save_provider(
                    LLMProviderConfig(
                        id="tx-fail",
                        name="TX Fail",
                        provider_type=ProviderType.OPENAI,
                        default_model="gpt-4o",
                    )
                )
                raise RuntimeError("Simulated error")
        except RuntimeError:
            pass

        # Should have been rolled back
        assert storage.get_provider("tx-fail") is None


# ── BaseAIStorage Interface Tests ────────────────────────────────────────────


class TestBaseAIStorageInterface:
    """Vérifie que UnifiedStorage implémente bien BaseAIStorage."""

    def test_is_instance(self, storage: UnifiedStorage):
        from pyworkflow_engine.ports.ai.storage import BaseAIStorage

        assert isinstance(storage, BaseAIStorage)

    def test_context_manager(self):
        """Peut être utilisé comme context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "ctx.db")
            with UnifiedStorage(db_path) as s:
                s.migrate()
                tables = s.get_table_names()
                assert len(tables) >= 13
