"""
Tests unitaires — models/ai/__init__.py (ADR-013, Phase 3.6).

Vérifie que tous les symboles publics sont importables depuis le point d'entrée
``pyworkflow_engine.models.ai``.
"""

from __future__ import annotations


class TestModelsAIPublicAPI:
    """Tous les symboles de __all__ doivent être importables."""

    def test_import_provider(self):
        from pyworkflow_engine.models.ai import (
            LLMProviderConfig,
            PricingConfig,
            ProviderCapabilities,
            ProviderSettings,
        )

        assert LLMProviderConfig is not None

    def test_import_agent(self):
        from pyworkflow_engine.models.ai import Agent, AgentConfig

        assert Agent is not None
        assert AgentConfig is not None

    def test_import_tool(self):
        from pyworkflow_engine.models.ai import ToolDefinition

        assert ToolDefinition is not None

    def test_import_skill(self):
        from pyworkflow_engine.models.ai import AgentSkillAssignment, Skill

        assert Skill is not None
        assert AgentSkillAssignment is not None

    def test_import_conversation(self):
        from pyworkflow_engine.models.ai import Conversation

        assert Conversation is not None

    def test_import_message(self):
        from pyworkflow_engine.models.ai import (
            Message,
            TokenUsage,
            ToolCall,
            ToolResult,
        )

        assert Message is not None

    def test_import_graph(self):
        from pyworkflow_engine.models.ai import Graph, GraphEdge, GraphNode

        assert Graph is not None

    def test_import_execution(self):
        from pyworkflow_engine.models.ai import Execution, ExecutionStep

        assert Execution is not None
        assert ExecutionStep is not None

    def test_import_memory(self):
        from pyworkflow_engine.models.ai import AgentMemory

        assert AgentMemory is not None

    def test_import_knowledge(self):
        from pyworkflow_engine.models.ai import Chunk, Document, KnowledgeSource

        assert KnowledgeSource is not None

    def test_import_all_enums(self):
        from pyworkflow_engine.models.ai import (
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

        assert ProviderType is not None
        assert ExecutionStatus is not None

    def test_execution_status_is_run_status(self):
        from pyworkflow_engine.models.ai import ExecutionStatus
        from pyworkflow_engine.models.enums import RunStatus

        assert ExecutionStatus is RunStatus

    def test_all_list_completeness(self):
        import pyworkflow_engine.models.ai as ai_module

        for name in ai_module.__all__:
            assert hasattr(ai_module, name), f"'{name}' listed in __all__ but not found"
