"""
Port IA — interface abstraite pour la persistence du sous-système IA.

Définit le contrat CRUD complet pour les entités IA : providers, agents,
tools, skills, conversations, messages, executions, graphs, mémoires et
sources de connaissance.

Règle hexagonale :
    Ce module ne contient aucune implémentation concrète.
    Les adapters (InMemoryAIStorage, SQLiteAIStorage, …) implementent
    cette interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

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


class BaseAIStorage(ABC):
    """Contrat de persistence pour le sous-système IA.

    Toute implémentation concrète doit hériter de cette classe et implémenter
    toutes les méthodes abstraites.
    """

    # ──────────────────────────────────────────────────────────────────
    # Providers
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_provider(self, provider: LLMProviderConfig) -> LLMProviderConfig:
        """Sauvegarde (create/update) un provider LLM."""

    @abstractmethod
    def get_provider(self, provider_id: str) -> LLMProviderConfig | None:
        """Récupère un provider par son ID."""

    @abstractmethod
    def get_provider_by_name(self, name: str) -> LLMProviderConfig | None:
        """Récupère un provider par son nom."""

    @abstractmethod
    def list_providers(
        self, *, is_active: bool | None = None
    ) -> list[LLMProviderConfig]:
        """Liste les providers avec filtre optionnel."""

    @abstractmethod
    def delete_provider(self, provider_id: str) -> bool:
        """Supprime un provider. Retourne True si trouvé et supprimé."""

    # ──────────────────────────────────────────────────────────────────
    # Agents
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_agent(self, agent: Agent) -> Agent:
        """Sauvegarde (create/update) un agent."""

    @abstractmethod
    def get_agent(self, agent_id: str) -> Agent | None:
        """Récupère un agent par son ID."""

    @abstractmethod
    def get_agent_by_slug(self, slug: str) -> Agent | None:
        """Récupère un agent par son slug."""

    @abstractmethod
    def list_agents(
        self,
        *,
        owner_id: str | None = None,
        role: AgentRole | None = None,
        is_active: bool | None = None,
    ) -> list[Agent]:
        """Liste les agents avec filtres optionnels."""

    @abstractmethod
    def delete_agent(self, agent_id: str) -> bool:
        """Supprime un agent par son ID."""

    # ──────────────────────────────────────────────────────────────────
    # Tools
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_tool(self, tool: ToolDefinition) -> ToolDefinition:
        """Sauvegarde (create/update) un outil."""

    @abstractmethod
    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        """Récupère un outil par son ID."""

    @abstractmethod
    def get_tool_by_key(self, key: str) -> ToolDefinition | None:
        """Récupère un outil par sa clé unique."""

    @abstractmethod
    def list_tools(self, *, is_active: bool | None = None) -> list[ToolDefinition]:
        """Liste les outils avec filtre optionnel."""

    @abstractmethod
    def list_tools_for_agent(self, agent_id: str) -> list[ToolDefinition]:
        """Liste les outils accessibles par un agent."""

    @abstractmethod
    def delete_tool(self, tool_id: str) -> bool:
        """Supprime un outil par son ID."""

    # ──────────────────────────────────────────────────────────────────
    # Skills
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_skill(self, skill: Skill) -> Skill:
        """Sauvegarde (create/update) un skill."""

    @abstractmethod
    def get_skill(self, skill_id: str) -> Skill | None:
        """Récupère un skill par son ID."""

    @abstractmethod
    def list_skills(self, *, is_active: bool | None = None) -> list[Skill]:
        """Liste les skills avec filtre optionnel."""

    @abstractmethod
    def save_skill_assignment(
        self, assignment: AgentSkillAssignment
    ) -> AgentSkillAssignment:
        """Sauvegarde une association agent-skill."""

    @abstractmethod
    def list_skill_assignments_for_agent(
        self, agent_id: str
    ) -> list[AgentSkillAssignment]:
        """Liste les assignments de skills pour un agent."""

    @abstractmethod
    def delete_skill(self, skill_id: str) -> bool:
        """Supprime un skill par son ID."""

    # ──────────────────────────────────────────────────────────────────
    # Conversations
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_conversation(self, conversation: Conversation) -> Conversation:
        """Sauvegarde (create/update) une conversation."""

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Récupère une conversation par son ID."""

    @abstractmethod
    def list_conversations(
        self,
        *,
        agent_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[Conversation]:
        """Liste les conversations avec filtres optionnels."""

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool:
        """Supprime une conversation par son ID."""

    # ──────────────────────────────────────────────────────────────────
    # Messages
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_message(self, message: Message) -> Message:
        """Sauvegarde un message."""

    @abstractmethod
    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Message]:
        """Récupère les messages d'une conversation (paginé, trié par created_at)."""

    @abstractmethod
    def count_messages(self, conversation_id: str) -> int:
        """Compte les messages d'une conversation."""

    # ──────────────────────────────────────────────────────────────────
    # Executions
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_execution(self, execution: Execution) -> Execution:
        """Sauvegarde (create/update) une exécution IA."""

    @abstractmethod
    def get_execution(self, execution_id: str) -> Execution | None:
        """Récupère une exécution par son ID."""

    @abstractmethod
    def list_executions(
        self,
        *,
        agent_id: str | None = None,
        status: ExecutionStatus | None = None,
    ) -> list[Execution]:
        """Liste les exécutions avec filtres optionnels."""

    @abstractmethod
    def save_execution_step(self, step: ExecutionStep) -> ExecutionStep:
        """Sauvegarde une étape d'exécution IA."""

    @abstractmethod
    def get_execution_steps(self, execution_id: str) -> list[ExecutionStep]:
        """Récupère les étapes d'une exécution IA (triées par order)."""

    # ──────────────────────────────────────────────────────────────────
    # Graphs
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_graph(self, graph: Graph) -> Graph:
        """Sauvegarde (create/update) un graph d'agent."""

    @abstractmethod
    def get_graph(self, graph_id: str) -> Graph | None:
        """Récupère un graph par son ID."""

    @abstractmethod
    def get_graph_by_slug(self, slug: str) -> Graph | None:
        """Récupère un graph par son slug."""

    @abstractmethod
    def list_graphs(
        self,
        *,
        agent_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[Graph]:
        """Liste les graphs avec filtres optionnels."""

    @abstractmethod
    def delete_graph(self, graph_id: str) -> bool:
        """Supprime un graph par son ID."""

    # ──────────────────────────────────────────────────────────────────
    # Memory
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_memory(self, memory: AgentMemory) -> AgentMemory:
        """Sauvegarde (create/update) une entrée de mémoire."""

    @abstractmethod
    def get_memory(self, agent_id: str, key: str) -> AgentMemory | None:
        """Récupère une mémoire par agent_id + clé unique."""

    @abstractmethod
    def list_memories(
        self,
        agent_id: str,
        *,
        memory_type: MemoryType | None = None,
    ) -> list[AgentMemory]:
        """Liste les mémoires d'un agent avec filtre optionnel."""

    @abstractmethod
    def delete_memory(self, memory_id: str) -> bool:
        """Supprime une entrée de mémoire par son ID."""

    @abstractmethod
    def delete_expired_memories(self) -> int:
        """Supprime les mémoires expirées. Retourne le nombre supprimé."""

    # ──────────────────────────────────────────────────────────────────
    # Knowledge
    # ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_knowledge_source(self, source: KnowledgeSource) -> KnowledgeSource:
        """Sauvegarde (create/update) une source de connaissance."""

    @abstractmethod
    def get_knowledge_source(self, source_id: str) -> KnowledgeSource | None:
        """Récupère une source de connaissance par son ID."""

    @abstractmethod
    def list_knowledge_sources(
        self,
        *,
        agent_id: str | None = None,
    ) -> list[KnowledgeSource]:
        """Liste les sources de connaissance avec filtre optionnel."""

    @abstractmethod
    def delete_knowledge_source(self, source_id: str) -> bool:
        """Supprime une source de connaissance par son ID."""

    # ──────────────────────────────────────────────────────────────────
    # Transactions & lifecycle
    # ──────────────────────────────────────────────────────────────────

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Context manager pour les opérations transactionnelles.

        L'implémentation par défaut est un no-op.
        Les backends SQLite/SQLAlchemy doivent surcharger cette méthode.
        """
        yield

    def close(self) -> None:  # noqa: B027
        """Ferme les connexions et libère les ressources (no-op par défaut)."""

    def __enter__(self) -> BaseAIStorage:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
