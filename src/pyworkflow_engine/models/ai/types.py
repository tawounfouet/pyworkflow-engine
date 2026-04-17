"""
pyworkflow_engine.models.ai.types — Enums IA et alias de types.

Centralise tous les types énumérés propres au domaine IA (ADR-013).
Zéro dépendance externe — stdlib ``enum`` uniquement.

Alias :
    ExecutionStatus = RunStatus  (pont IA → workflow core, ADR-013)
"""

from __future__ import annotations

from enum import StrEnum

from pyworkflow_engine.models.enums import RunStatus

# ── Alias bridge ──────────────────────────────────────────────────────────────
# Les modèles IA utilisent « ExecutionStatus » (terminologie ai_engine),
# mais le core workflow expose « RunStatus ».
# L'alias évite de dupliquer les valeurs tout en gardant la lisibilité IA.
ExecutionStatus = RunStatus


# ── Provider ──────────────────────────────────────────────────────────────────


class ProviderType(StrEnum):
    """Types de fournisseurs LLM supportés."""

    # OpenAI Family
    OPENAI = "openai"
    OPENAI_AZURE = "openai_azure"
    CODEX = "codex"

    # Anthropic Family
    ANTHROPIC = "anthropic"
    CLAUDE_CODE = "claude_code"

    # Chinese LLMs
    QWEN = "qwen"
    MOONSHOT = "moonshot"
    KIMI_CODING = "kimi_coding"
    GLM = "glm"
    MINIMAX = "minimax"
    XIAOMI = "xiaomi"

    # Gateways
    OPENROUTER = "openrouter"
    VERCEL_AI = "vercel_ai"

    # Cloud Providers
    BEDROCK = "bedrock"
    VERTEX_AI = "vertex_ai"

    # Fast inference
    GROQ = "groq"

    # Google
    GEMINI = "gemini"

    # Specialized
    VENICE = "venice"
    ZAI = "zai"
    OPENCODE_ZEN = "opencode_zen"

    # Local
    OLLAMA = "ollama"
    LLAMACPP = "llamacpp"
    VLLM = "vllm"

    # Generic
    CUSTOM = "custom"


# ── Agent ─────────────────────────────────────────────────────────────────────


class AgentRole(StrEnum):
    """Rôles possibles pour un agent AI."""

    ASSISTANT = "assistant"
    RESEARCHER = "researcher"
    CODER = "coder"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ORCHESTRATOR = "orchestrator"
    CUSTOM = "custom"


# ── Tool ──────────────────────────────────────────────────────────────────────


class ToolType(StrEnum):
    """Types d'outils disponibles."""

    FUNCTION = "function"
    API = "api"
    DATABASE = "database"
    FILE = "file"
    CONNECTOR = "connector"
    WORKFLOW = "workflow"
    CUSTOM = "custom"


# ── Skill ─────────────────────────────────────────────────────────────────────


class SkillCategory(StrEnum):
    """Catégories de compétences."""

    RESEARCH = "research"
    CODING = "coding"
    COMMUNICATION = "communication"
    DATA = "data"
    CREATIVE = "creative"
    AUTOMATION = "automation"
    CUSTOM = "custom"


class Proficiency(StrEnum):
    """Niveau de maîtrise d'un skill par un agent."""

    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


# ── Message ───────────────────────────────────────────────────────────────────


class MessageRole(StrEnum):
    """Rôles de messages dans une conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# ── Conversation ──────────────────────────────────────────────────────────────


class ConversationStatus(StrEnum):
    """Statuts d'une conversation."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


# ── Graph ─────────────────────────────────────────────────────────────────────


class GraphStatus(StrEnum):
    """Statuts d'un graph."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class NodeType(StrEnum):
    """Types de nœuds dans un graph."""

    AGENT = "agent"
    CONDITION = "condition"
    TOOL = "tool"
    INPUT = "input"
    OUTPUT = "output"
    PARALLEL = "parallel"
    LOOP = "loop"


# ── AI Step ───────────────────────────────────────────────────────────────────


class AIStepType(StrEnum):
    """Types d'étapes spécifiques aux exécutions IA.

    Complément de ``pyworkflow_engine.models.enums.StepType`` pour la
    terminologie propre aux agents.
    """

    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DECISION = "decision"
    ERROR = "error"


# ── Memory ────────────────────────────────────────────────────────────────────


class MemoryType(StrEnum):
    """Types de mémoire pour un agent."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"


# ── Knowledge ─────────────────────────────────────────────────────────────────


class SourceType(StrEnum):
    """Types de sources de connaissance."""

    DOCUMENT = "document"
    URL = "url"
    TEXT = "text"
    DATABASE = "database"
    API = "api"


class IndexStatus(StrEnum):
    """Statuts d'indexation d'une source de connaissance."""

    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


# ── Event ─────────────────────────────────────────────────────────────────────


class AIEventType(StrEnum):
    """Types d'événements émis par le sous-système IA."""

    # Agent lifecycle
    AGENT_CREATED = "agent.created"
    AGENT_UPDATED = "agent.updated"
    AGENT_DELETED = "agent.deleted"

    # Conversation lifecycle
    CONVERSATION_STARTED = "conversation.started"
    CONVERSATION_ENDED = "conversation.ended"

    # Message lifecycle
    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"

    # Tool lifecycle
    TOOL_CALLED = "tool.called"
    TOOL_SUCCEEDED = "tool.succeeded"
    TOOL_FAILED = "tool.failed"

    # LLM lifecycle
    LLM_REQUEST_STARTED = "llm.request.started"
    LLM_REQUEST_COMPLETED = "llm.request.completed"
    LLM_REQUEST_FAILED = "llm.request.failed"

    # Skill lifecycle
    SKILL_STARTED = "skill.started"
    SKILL_COMPLETED = "skill.completed"
    SKILL_FAILED = "skill.failed"

    # Execution lifecycle
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"

    # Custom / user-defined
    CUSTOM = "custom"
