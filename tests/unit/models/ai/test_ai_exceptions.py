"""
Tests unitaires — exceptions IA fusionnées dans exceptions.py (ADR-013, Phase 3.5).

Vérifie :
  - Hiérarchie : toutes les exceptions IA héritent de AIError → WorkflowError
  - Messages bien formés
  - Attributs spécifiques présents
"""

from __future__ import annotations

import pytest

from pyworkflow_engine.exceptions import (
    AIError,
    AgentDisabledError,
    AgentError,
    AgentNotFoundError,
    AIExecutionError,
    AIExecutionNotFoundError,
    AIGraphError,
    AIGraphNotFoundError,
    AIToolError,
    AIToolExecutionError,
    AIToolNotFoundError,
    APIKeyMissingError,
    ConversationError,
    ConversationNotFoundError,
    KnowledgeError,
    KnowledgeSourceNotFoundError,
    LLMError,
    MissingAIDependencyError,
    ProviderError,
    ProviderNotFoundError,
    SkillConfigurationError,
    SkillError,
    SkillExecutionError,
    SkillNotFoundError,
    UnsupportedProviderError,
    WorkflowError,
)


class TestAIErrorHierarchy:
    """Toutes les exceptions IA doivent remonter jusqu'à WorkflowError."""

    def _assert_chain(self, exc_class, *ancestors):
        for ancestor in ancestors:
            assert issubclass(
                exc_class, ancestor
            ), f"{exc_class.__name__} should be a subclass of {ancestor.__name__}"

    def test_ai_error_base(self):
        self._assert_chain(AIError, WorkflowError, Exception)

    def test_provider_chain(self):
        self._assert_chain(ProviderError, AIError, WorkflowError)
        self._assert_chain(LLMError, ProviderError, AIError)
        self._assert_chain(ProviderNotFoundError, ProviderError)
        self._assert_chain(UnsupportedProviderError, ProviderError)
        self._assert_chain(APIKeyMissingError, ProviderError)

    def test_agent_chain(self):
        self._assert_chain(AgentError, AIError, WorkflowError)
        self._assert_chain(AgentNotFoundError, AgentError)
        self._assert_chain(AgentDisabledError, AgentError)

    def test_conversation_chain(self):
        self._assert_chain(ConversationError, AIError)
        self._assert_chain(ConversationNotFoundError, ConversationError)

    def test_graph_chain(self):
        self._assert_chain(AIGraphError, AIError)
        self._assert_chain(AIGraphNotFoundError, AIGraphError)

    def test_execution_chain(self):
        self._assert_chain(AIExecutionError, AIError)
        self._assert_chain(AIExecutionNotFoundError, AIExecutionError)

    def test_tool_chain(self):
        self._assert_chain(AIToolError, AIError)
        self._assert_chain(AIToolNotFoundError, AIToolError)
        self._assert_chain(AIToolExecutionError, AIToolError)

    def test_skill_chain(self):
        self._assert_chain(SkillError, AIError)
        self._assert_chain(SkillNotFoundError, SkillError)
        self._assert_chain(SkillExecutionError, SkillError)
        self._assert_chain(SkillConfigurationError, SkillError)

    def test_knowledge_chain(self):
        self._assert_chain(KnowledgeError, AIError)
        self._assert_chain(KnowledgeSourceNotFoundError, KnowledgeError)

    def test_dependency_chain(self):
        self._assert_chain(MissingAIDependencyError, AIError)


class TestProviderNotFoundError:
    def test_message(self):
        err = ProviderNotFoundError("my-provider")
        assert "my-provider" in str(err)
        assert err.provider_id == "my-provider"

    def test_catchable_as_workflow_error(self):
        with pytest.raises(WorkflowError):
            raise ProviderNotFoundError("x")


class TestUnsupportedProviderError:
    def test_message_without_available(self):
        err = UnsupportedProviderError("unknown_llm")
        assert "unknown_llm" in str(err)

    def test_message_with_available(self):
        err = UnsupportedProviderError("bad", available=["openai", "anthropic"])
        assert "openai" in str(err)
        assert "anthropic" in str(err)


class TestAPIKeyMissingError:
    def test_message_without_env_var(self):
        err = APIKeyMissingError("OpenAI")
        assert "OpenAI" in str(err)
        assert err.env_var is None

    def test_message_with_env_var(self):
        err = APIKeyMissingError("OpenAI", env_var="OPENAI_API_KEY")
        assert "OPENAI_API_KEY" in str(err)


class TestAgentErrors:
    def test_not_found_message(self):
        err = AgentNotFoundError("agent-123")
        assert "agent-123" in str(err)
        assert err.agent_id == "agent-123"

    def test_disabled_message(self):
        err = AgentDisabledError("my-agent")
        assert "my-agent" in str(err)


class TestConversationNotFoundError:
    def test_message(self):
        err = ConversationNotFoundError("conv-456")
        assert "conv-456" in str(err)
        assert err.conversation_id == "conv-456"


class TestAIToolExecutionError:
    def test_message(self):
        err = AIToolExecutionError("web_search", "timeout")
        assert "web_search" in str(err)
        assert "timeout" in str(err)
        assert err.tool_name == "web_search"
        assert err.detail == "timeout"


class TestSkillErrors:
    def test_not_found_message(self):
        err = SkillNotFoundError("research")
        assert "research" in str(err)

    def test_execution_error(self):
        err = SkillExecutionError("coding", "syntax error")
        assert "coding" in str(err)
        assert "syntax error" in str(err)


class TestMissingAIDependencyError:
    def test_message(self):
        err = MissingAIDependencyError("openai", "openai")
        assert "openai" in str(err)
        assert "pip install" in str(err)
        assert err.package == "openai"
        assert err.extra == "openai"
