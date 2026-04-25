"""
Tests unitaires — models/ai/agent.py, message.py, tool.py, skill.py,
                   conversation.py, memory.py (ADR-013, Phase 3.2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.conversation import Conversation
from pyworkflow_engine.models.ai.memory import AgentMemory
from pyworkflow_engine.models.ai.message import (
    Message,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from pyworkflow_engine.models.ai.skill import AgentSkillAssignment, Skill
from pyworkflow_engine.models.ai.tool import ToolDefinition
from pyworkflow_engine.models.ai.types import (
    AgentRole,
    ConversationStatus,
    MemoryType,
    MessageRole,
    Proficiency,
    SkillCategory,
    ToolType,
)


# ── AgentConfig ───────────────────────────────────────────────────────────────


class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig()
        assert cfg.max_iterations == 10
        assert cfg.max_tokens_per_run == 8000
        assert cfg.temperature is None
        assert cfg.enable_memory is True
        assert cfg.enable_tools is True
        assert cfg.enable_rag is False

    def test_max_iterations_ge_1(self):
        with pytest.raises(Exception):
            AgentConfig(max_iterations=0)

    def test_temperature_bounds(self):
        with pytest.raises(Exception):
            AgentConfig(temperature=2.5)


# ── Agent ─────────────────────────────────────────────────────────────────────


class TestAgent:
    def _make(self, **kwargs) -> Agent:
        return Agent(
            name="Test Agent",
            provider_id="provider-uuid",
            **kwargs,
        )

    def test_creation_minimal(self):
        a = self._make()
        assert a.name == "Test Agent"
        assert a.role == AgentRole.ASSISTANT
        assert a.is_active is True
        assert a.tool_ids == []
        assert a.skill_ids == []

    def test_id_auto_generated(self):
        a1 = self._make()
        a2 = self._make()
        assert a1.id != a2.id

    def test_get_effective_temperature_none(self):
        a = self._make()
        assert a.get_effective_temperature() is None

    def test_get_effective_temperature_override(self):
        a = self._make(config=AgentConfig(temperature=0.3))
        assert a.get_effective_temperature() == pytest.approx(0.3)

    def test_role_custom(self):
        a = self._make(role=AgentRole.ORCHESTRATOR)
        assert a.role == AgentRole.ORCHESTRATOR


# ── TokenUsage ────────────────────────────────────────────────────────────────


class TestTokenUsage:
    def test_defaults(self):
        t = TokenUsage()
        assert t.prompt_tokens == 0
        assert t.total_tokens == 0
        assert t.estimated_cost_usd == 0.0

    def test_from_total(self):
        t = TokenUsage.from_total(500, cost=0.01)
        assert t.total_tokens == 500
        assert t.estimated_cost_usd == pytest.approx(0.01)

    def test_negative_tokens_invalid(self):
        with pytest.raises(Exception):
            TokenUsage(prompt_tokens=-1)


# ── ToolCall / ToolResult ─────────────────────────────────────────────────────


class TestToolCall:
    def test_creation(self):
        tc = ToolCall(name="web_search", arguments={"query": "AI"})
        assert tc.name == "web_search"
        assert tc.arguments == {"query": "AI"}
        assert tc.id  # auto-generated

    def test_id_unique(self):
        t1 = ToolCall(name="fn")
        t2 = ToolCall(name="fn")
        assert t1.id != t2.id


class TestToolResult:
    def test_creation(self):
        tr = ToolResult(tool_call_id="call-1", output="result text")
        assert tr.tool_call_id == "call-1"
        assert tr.is_error is False

    def test_error_flag(self):
        tr = ToolResult(tool_call_id="call-1", is_error=True)
        assert tr.is_error is True


# ── Message ───────────────────────────────────────────────────────────────────


class TestMessage:
    def test_user_message(self):
        m = Message(
            conversation_id="conv-1",
            role=MessageRole.USER,
            content="Hello!",
        )
        assert m.role == MessageRole.USER
        assert m.content == "Hello!"
        assert m.tool_calls == []
        assert m.tool_result is None

    def test_assistant_with_tool_calls(self):
        tc = ToolCall(name="search", arguments={"q": "x"})
        m = Message(
            conversation_id="conv-1",
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[tc],
        )
        assert len(m.tool_calls) == 1
        assert m.tool_calls[0].name == "search"

    def test_tool_message(self):
        tr = ToolResult(tool_call_id="call-1", output="42")
        m = Message(
            conversation_id="conv-1",
            role=MessageRole.TOOL,
            content="42",
            tool_result=tr,
        )
        assert m.tool_result is not None
        assert m.tool_result.output == "42"


# ── ToolDefinition ────────────────────────────────────────────────────────────


class TestToolDefinition:
    def test_creation(self):
        t = ToolDefinition(
            key="web_search",
            name="Web Search",
            tool_type=ToolType.API,
            parameters_schema={"type": "object", "properties": {}},
        )
        assert t.key == "web_search"
        assert t.tool_type == ToolType.API
        assert t.requires_approval is False
        assert t.is_dangerous is False

    def test_get_function_schema(self):
        t = ToolDefinition(
            key="calc",
            name="Calculator",
            description="Does math",
            parameters_schema={"type": "object"},
        )
        schema = t.get_function_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "calc"
        assert schema["function"]["description"] == "Does math"


# ── Skill / AgentSkillAssignment ──────────────────────────────────────────────


class TestSkill:
    def test_creation(self):
        s = Skill(
            key="research",
            name="Research",
            category=SkillCategory.RESEARCH,
        )
        assert s.key == "research"
        assert s.is_active is True
        assert s.required_tool_ids == []

    def test_id_auto_generated(self):
        s1 = Skill(key="a", name="A")
        s2 = Skill(key="b", name="B")
        assert s1.id != s2.id


class TestAgentSkillAssignment:
    def test_creation(self):
        a = AgentSkillAssignment(agent_id="ag-1", skill_id="sk-1")
        assert a.proficiency == Proficiency.INTERMEDIATE
        assert a.enabled is True

    def test_advanced_proficiency(self):
        a = AgentSkillAssignment(
            agent_id="ag-1",
            skill_id="sk-1",
            proficiency=Proficiency.ADVANCED,
        )
        assert a.proficiency == Proficiency.ADVANCED


# ── Conversation ──────────────────────────────────────────────────────────────


class TestConversation:
    def test_creation(self):
        c = Conversation(agent_id="agent-1", title="Test Chat")
        assert c.title == "Test Chat"
        assert c.status == ConversationStatus.ACTIVE
        assert c.message_count == 0
        assert c.last_message_at is None

    def test_id_auto_generated(self):
        c1 = Conversation(agent_id="a")
        c2 = Conversation(agent_id="a")
        assert c1.id != c2.id


# ── AgentMemory ───────────────────────────────────────────────────────────────


class TestAgentMemory:
    def test_creation(self):
        m = AgentMemory(
            agent_id="ag-1",
            key="user_prefs",
            content='{"lang": "fr"}',
            memory_type=MemoryType.LONG_TERM,
        )
        assert m.key == "user_prefs"
        assert m.is_expired is False
        assert m.relevance_score == 1.0

    def test_not_expired_when_no_expiry(self):
        m = AgentMemory(agent_id="ag-1", key="k", content="v")
        assert m.is_expired is False

    def test_expired(self):
        past = datetime.now(UTC) - timedelta(hours=1)
        m = AgentMemory(agent_id="ag-1", key="k", content="v", expires_at=past)
        assert m.is_expired is True

    def test_not_expired_future(self):
        future = datetime.now(UTC) + timedelta(hours=1)
        m = AgentMemory(agent_id="ag-1", key="k", content="v", expires_at=future)
        assert m.is_expired is False
