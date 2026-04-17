"""
pyworkflow_engine.models.ai — Modèles Pydantic du sous-système IA (ADR-013).

Import unique::

    from pyworkflow_engine.models.ai import (
        Agent, AgentConfig,
        LLMProviderConfig, ProviderType,
        ToolDefinition, ToolType,
        Skill, AgentSkillAssignment,
        Conversation, ConversationStatus,
        Message, ToolCall, ToolResult, TokenUsage, MessageRole,
        Graph, GraphNode, GraphEdge, GraphStatus, NodeType,
        Execution, ExecutionStep, ExecutionStatus,
        AgentMemory, MemoryType,
        KnowledgeSource, Document, Chunk,
    )
"""

from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.conversation import Conversation
from pyworkflow_engine.models.ai.execution import Execution, ExecutionStep
from pyworkflow_engine.models.ai.graph import Graph, GraphEdge, GraphNode
from pyworkflow_engine.models.ai.knowledge import Chunk, Document, KnowledgeSource
from pyworkflow_engine.models.ai.memory import AgentMemory
from pyworkflow_engine.models.ai.message import (
    Message,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from pyworkflow_engine.models.ai.provider import (
    LLMProviderConfig,
    PricingConfig,
    ProviderCapabilities,
    ProviderSettings,
)
from pyworkflow_engine.models.ai.skill import AgentSkillAssignment, Skill
from pyworkflow_engine.models.ai.tool import ToolDefinition
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

__all__ = [
    # ── Provider ──────────────────────────────────────────────────────────────
    "LLMProviderConfig",
    "ProviderCapabilities",
    "PricingConfig",
    "ProviderSettings",
    # ── Agent ─────────────────────────────────────────────────────────────────
    "Agent",
    "AgentConfig",
    # ── Tool ──────────────────────────────────────────────────────────────────
    "ToolDefinition",
    # ── Skill ─────────────────────────────────────────────────────────────────
    "Skill",
    "AgentSkillAssignment",
    # ── Conversation ──────────────────────────────────────────────────────────
    "Conversation",
    # ── Message ───────────────────────────────────────────────────────────────
    "Message",
    "ToolCall",
    "ToolResult",
    "TokenUsage",
    # ── Graph ─────────────────────────────────────────────────────────────────
    "Graph",
    "GraphNode",
    "GraphEdge",
    # ── Execution IA ──────────────────────────────────────────────────────────
    "Execution",
    "ExecutionStep",
    # ── Memory ────────────────────────────────────────────────────────────────
    "AgentMemory",
    # ── Knowledge ─────────────────────────────────────────────────────────────
    "KnowledgeSource",
    "Document",
    "Chunk",
    # ── Enums / Types ─────────────────────────────────────────────────────────
    "ProviderType",
    "AgentRole",
    "ToolType",
    "SkillCategory",
    "Proficiency",
    "MessageRole",
    "ConversationStatus",
    "GraphStatus",
    "NodeType",
    "AIStepType",
    "ExecutionStatus",
    "MemoryType",
    "SourceType",
    "IndexStatus",
    "AIEventType",
]
