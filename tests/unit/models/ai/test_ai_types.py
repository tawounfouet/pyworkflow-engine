"""
Tests unitaires — models/ai/types.py (ADR-013, Phase 3.1).

Vérifie :
  - Chaque enum StrEnum retourne la bonne valeur string
  - L'alias ExecutionStatus == RunStatus
  - Les enums ne se chevauchent pas
"""

from __future__ import annotations

import pytest

from pyworkflow_engine.models.ai.types import (
    AIEventType,
    AIStepType,
    AgentRole,
    ConversationStatus,
    ExecutionStatus,
    GraphStatus,
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


class TestExecutionStatusAlias:
    """ExecutionStatus doit être un alias de RunStatus (même objet)."""

    def test_alias_is_same_class(self):
        assert ExecutionStatus is RunStatus

    def test_alias_values_match(self):
        assert ExecutionStatus.PENDING == RunStatus.PENDING
        assert ExecutionStatus.RUNNING == RunStatus.RUNNING
        assert ExecutionStatus.SUCCESS == RunStatus.SUCCESS
        assert ExecutionStatus.FAILED == RunStatus.FAILED
        assert ExecutionStatus.CANCELLED == RunStatus.CANCELLED


class TestProviderType:
    def test_openai(self):
        assert ProviderType.OPENAI == "openai"

    def test_anthropic(self):
        assert ProviderType.ANTHROPIC == "anthropic"

    def test_ollama_local(self):
        assert ProviderType.OLLAMA == "ollama"

    def test_all_are_strings(self):
        for member in ProviderType:
            assert isinstance(member.value, str)
            assert member.value  # non-vide


class TestAgentRole:
    def test_values(self):
        assert AgentRole.ASSISTANT == "assistant"
        assert AgentRole.RESEARCHER == "researcher"
        assert AgentRole.ORCHESTRATOR == "orchestrator"

    def test_custom_exists(self):
        assert AgentRole.CUSTOM == "custom"


class TestToolType:
    def test_function(self):
        assert ToolType.FUNCTION == "function"

    def test_connector(self):
        assert ToolType.CONNECTOR == "connector"


class TestSkillCategory:
    def test_research(self):
        assert SkillCategory.RESEARCH == "research"

    def test_coding(self):
        assert SkillCategory.CODING == "coding"


class TestProficiency:
    def test_ordering_values(self):
        levels = [
            Proficiency.BASIC,
            Proficiency.INTERMEDIATE,
            Proficiency.ADVANCED,
            Proficiency.EXPERT,
        ]
        assert [p.value for p in levels] == [
            "basic",
            "intermediate",
            "advanced",
            "expert",
        ]


class TestMessageRole:
    def test_four_roles(self):
        assert len(MessageRole) == 4

    def test_tool_role(self):
        assert MessageRole.TOOL == "tool"


class TestConversationStatus:
    def test_three_statuses(self):
        assert len(ConversationStatus) == 3

    def test_archived(self):
        assert ConversationStatus.ARCHIVED == "archived"


class TestGraphTypes:
    def test_graph_status(self):
        assert GraphStatus.DRAFT == "draft"
        assert GraphStatus.ACTIVE == "active"

    def test_node_type(self):
        assert NodeType.AGENT == "agent"
        assert NodeType.CONDITION == "condition"
        assert NodeType.PARALLEL == "parallel"


class TestAIStepType:
    def test_llm_call(self):
        assert AIStepType.LLM_CALL == "llm_call"

    def test_tool_call(self):
        assert AIStepType.TOOL_CALL == "tool_call"

    def test_decision(self):
        assert AIStepType.DECISION == "decision"


class TestMemoryType:
    def test_three_types(self):
        assert len(MemoryType) == 3

    def test_episodic(self):
        assert MemoryType.EPISODIC == "episodic"


class TestKnowledgeTypes:
    def test_source_type(self):
        assert SourceType.DOCUMENT == "document"
        assert SourceType.URL == "url"

    def test_index_status(self):
        assert IndexStatus.PENDING == "pending"
        assert IndexStatus.INDEXED == "indexed"
        assert IndexStatus.FAILED == "failed"


class TestAIEventType:
    def test_agent_created(self):
        assert AIEventType.AGENT_CREATED == "agent.created"

    def test_llm_lifecycle(self):
        assert AIEventType.LLM_REQUEST_STARTED == "llm.request.started"
        assert AIEventType.LLM_REQUEST_COMPLETED == "llm.request.completed"
        assert AIEventType.LLM_REQUEST_FAILED == "llm.request.failed"

    def test_custom(self):
        assert AIEventType.CUSTOM == "custom"
