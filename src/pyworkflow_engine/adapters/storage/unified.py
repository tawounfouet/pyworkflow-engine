"""
Adapter persistence — UnifiedStorage façade (ADR-017).

Point d'entrée unique pour la persistence des modèles IA Pydantic.
Combine ``SchemaGenerator`` (DDL auto) + ``Repository[T]`` (CRUD générique)
et implémente le port ``BaseAIStorage``.

Usage::

    storage = UnifiedStorage("./workflow.db")
    storage.migrate()  # crée toutes les tables

    # Via raccourcis nommés (IDE-friendly)
    agent = storage.agents.create(Agent(name="bot", provider_id="p1", ...))
    found = storage.agents.get(agent.id)

    # Via accès générique
    repo = storage.repository(Agent)
    repo.filter(role="researcher")

    storage.close()

Règle hexagonale :
    Ce module est un **adapter** qui implémente ``BaseAIStorage``
    et compose ``SchemaGenerator`` + ``Repository``.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from pyworkflow_engine.adapters.storage.repository import Repository
from pyworkflow_engine.adapters.storage.schema_generator import SchemaGenerator, _q
from pyworkflow_engine.ports.ai.storage import BaseAIStorage
from pyworkflow_engine.ports.persistable import ModelRegistry, PersistableModel

# ── Ensure all AI models are registered ──────────────────────────────────────
# Importing models/ai triggers @ModelRegistry.register decorators.
import pyworkflow_engine.models.ai  # noqa: F401

# ── Ensure logging models are registered (ADR-018 D4) ────────────────────────
import pyworkflow_engine.models.logging  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pyworkflow_engine.models.ai.agent import Agent
    from pyworkflow_engine.models.ai.conversation import Conversation
    from pyworkflow_engine.models.ai.execution import Execution, ExecutionStep
    from pyworkflow_engine.models.ai.graph import Graph
    from pyworkflow_engine.models.ai.knowledge import Chunk, Document, KnowledgeSource
    from pyworkflow_engine.models.ai.memory import AgentMemory
    from pyworkflow_engine.models.ai.message import Message
    from pyworkflow_engine.models.ai.provider import LLMProviderConfig
    from pyworkflow_engine.models.ai.skill import AgentSkillAssignment, Skill
    from pyworkflow_engine.models.ai.tool import ToolDefinition
    from pyworkflow_engine.models.ai.types import (
        AgentRole,
        ExecutionStatus,
        MemoryType,
    )
    from pyworkflow_engine.models.logging.log_entry import WorkflowLog

T = TypeVar("T", bound=PersistableModel)


class UnifiedStorage(BaseAIStorage):
    """Backend de persistence unifié avec auto-discovery des modèles (ADR-017).

    Implémente ``BaseAIStorage`` via les ``Repository`` génériques —
    chaque méthode abstraite est un one-liner qui délègue.

    Features:
        - Auto-migration DDL (``migrate()``)
        - Repositories typés par modèle
        - Raccourcis nommés (``.agents``, ``.providers``, etc.)
        - Thread-safe (connexions thread-local)
        - FK constraints + WAL mode
    """

    def __init__(self, database_path: str = "./workflow.db") -> None:
        self._database_path = str(Path(database_path).resolve())
        self._local = threading.local()
        self._repo_cache: dict[str, Repository[Any]] = {}
        self._in_transaction: bool = False

    # ── Connection management ────────────────────────────────────────

    @property
    def connection(self) -> sqlite3.Connection:
        """Connexion SQLite thread-local, lazy-initialisée."""
        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(self._database_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.connection = conn
        return conn

    # ── Migration ────────────────────────────────────────────────────

    def migrate(self) -> list[str]:
        """Crée toutes les tables pour les modèles enregistrés.

        Utilise ``CREATE TABLE IF NOT EXISTS`` — idempotent.

        Returns:
            Liste des instructions DDL exécutées.
        """
        statements: list[str] = []

        for model_cls in ModelRegistry.get_ordered():
            meta = model_cls.__table_meta__
            create_sql = SchemaGenerator.generate_create_table(meta)
            statements.append(create_sql)
            self.connection.execute(create_sql)

            for idx_sql in SchemaGenerator.generate_indexes(meta):
                statements.append(idx_sql)
                self.connection.execute(idx_sql)

        self.connection.commit()
        return statements

    # ── Generic repository access ────────────────────────────────────

    def repository(self, model_class: type[T]) -> Repository[T]:
        """Retourne un ``Repository[T]`` pour le modèle donné.

        Les repositories sont mis en cache par nom de table.

        Args:
            model_class: Classe ``PersistableModel``.

        Returns:
            Repository typé.
        """
        table_name = model_class.__table_meta__.table_name
        if table_name not in self._repo_cache:
            self._repo_cache[table_name] = Repository(
                self.connection,
                model_class,
                autocommit=not self._in_transaction,
            )
        return self._repo_cache[table_name]

    # ── Named repository shortcuts (IDE-friendly) ────────────────────

    @property
    def agents(self) -> Repository[Agent]:
        """Repository des Agents."""
        from pyworkflow_engine.models.ai.agent import Agent

        return self.repository(Agent)

    @property
    def providers(self) -> Repository[LLMProviderConfig]:
        """Repository des LLM Providers."""
        from pyworkflow_engine.models.ai.provider import LLMProviderConfig

        return self.repository(LLMProviderConfig)

    @property
    def conversations(self) -> Repository[Conversation]:
        """Repository des Conversations."""
        from pyworkflow_engine.models.ai.conversation import Conversation

        return self.repository(Conversation)

    @property
    def messages(self) -> Repository[Message]:
        """Repository des Messages."""
        from pyworkflow_engine.models.ai.message import Message

        return self.repository(Message)

    @property
    def tools(self) -> Repository[ToolDefinition]:
        """Repository des ToolDefinitions."""
        from pyworkflow_engine.models.ai.tool import ToolDefinition

        return self.repository(ToolDefinition)

    @property
    def skills(self) -> Repository[Skill]:
        """Repository des Skills."""
        from pyworkflow_engine.models.ai.skill import Skill

        return self.repository(Skill)

    @property
    def skill_assignments(self) -> Repository[AgentSkillAssignment]:
        """Repository des AgentSkillAssignments."""
        from pyworkflow_engine.models.ai.skill import AgentSkillAssignment

        return self.repository(AgentSkillAssignment)

    @property
    def graphs(self) -> Repository[Graph]:
        """Repository des Graphs."""
        from pyworkflow_engine.models.ai.graph import Graph

        return self.repository(Graph)

    @property
    def executions(self) -> Repository[Execution]:
        """Repository des Executions."""
        from pyworkflow_engine.models.ai.execution import Execution

        return self.repository(Execution)

    @property
    def execution_steps(self) -> Repository[ExecutionStep]:
        """Repository des ExecutionSteps."""
        from pyworkflow_engine.models.ai.execution import ExecutionStep

        return self.repository(ExecutionStep)

    @property
    def memories(self) -> Repository[AgentMemory]:
        """Repository des AgentMemories."""
        from pyworkflow_engine.models.ai.memory import AgentMemory

        return self.repository(AgentMemory)

    @property
    def knowledge_sources(self) -> Repository[KnowledgeSource]:
        """Repository des KnowledgeSources."""
        from pyworkflow_engine.models.ai.knowledge import KnowledgeSource

        return self.repository(KnowledgeSource)

    @property
    def documents(self) -> Repository[Document]:
        """Repository des Documents."""
        from pyworkflow_engine.models.ai.knowledge import Document

        return self.repository(Document)

    @property
    def chunks(self) -> Repository[Chunk]:
        """Repository des Chunks."""
        from pyworkflow_engine.models.ai.knowledge import Chunk

        return self.repository(Chunk)

    # ── Logging (ADR-018 D4) ─────────────────────────────────────────

    @property
    def logs(self) -> Repository[WorkflowLog]:
        """Repository des WorkflowLogs (ADR-018, décision 4)."""
        from pyworkflow_engine.models.logging.log_entry import WorkflowLog

        return self.repository(WorkflowLog)

    # ══════════════════════════════════════════════════════════════════
    # BaseAIStorage implementation
    # ══════════════════════════════════════════════════════════════════

    # ── Providers ────────────────────────────────────────────────────

    def save_provider(self, provider: LLMProviderConfig) -> LLMProviderConfig:
        return self.providers.create_or_update(provider)

    def get_provider(self, provider_id: str) -> LLMProviderConfig | None:
        return self.providers.get(provider_id)

    def get_provider_by_name(self, name: str) -> LLMProviderConfig | None:
        results = self.providers.filter(name=name, limit=1)
        return results[0] if results else None

    def list_providers(
        self, *, is_active: bool | None = None
    ) -> list[LLMProviderConfig]:
        conditions: dict[str, Any] = {}
        if is_active is not None:
            conditions["is_active"] = is_active
        return self.providers.filter(**conditions)

    def delete_provider(self, provider_id: str) -> bool:
        return self.providers.delete(provider_id)

    # ── Agents ───────────────────────────────────────────────────────

    def save_agent(self, agent: Agent) -> Agent:
        return self.agents.create_or_update(agent)

    def get_agent(self, agent_id: str) -> Agent | None:
        return self.agents.get(agent_id)

    def get_agent_by_slug(self, slug: str) -> Agent | None:
        results = self.agents.filter(slug=slug, limit=1)
        return results[0] if results else None

    def list_agents(
        self,
        *,
        owner_id: str | None = None,
        role: AgentRole | None = None,
        is_active: bool | None = None,
    ) -> list[Agent]:
        conditions: dict[str, Any] = {}
        if owner_id is not None:
            conditions["owner_id"] = owner_id
        if role is not None:
            conditions["role"] = role
        if is_active is not None:
            conditions["is_active"] = is_active
        return self.agents.filter(**conditions)

    def delete_agent(self, agent_id: str) -> bool:
        return self.agents.delete(agent_id)

    # ── Tools ────────────────────────────────────────────────────────

    def save_tool(self, tool: ToolDefinition) -> ToolDefinition:
        return self.tools.create_or_update(tool)

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        return self.tools.get(tool_id)

    def get_tool_by_key(self, key: str) -> ToolDefinition | None:
        results = self.tools.filter(key=key, limit=1)
        return results[0] if results else None

    def list_tools(self, *, is_active: bool | None = None) -> list[ToolDefinition]:
        conditions: dict[str, Any] = {}
        if is_active is not None:
            conditions["is_active"] = is_active
        return self.tools.filter(**conditions)

    def list_tools_for_agent(self, agent_id: str) -> list[ToolDefinition]:
        agent = self.get_agent(agent_id)
        if agent is None or not agent.tool_ids:
            return []
        return self.tools.filter(id__in=agent.tool_ids)

    def delete_tool(self, tool_id: str) -> bool:
        return self.tools.delete(tool_id)

    # ── Skills ───────────────────────────────────────────────────────

    def save_skill(self, skill: Skill) -> Skill:
        return self.skills.create_or_update(skill)

    def get_skill(self, skill_id: str) -> Skill | None:
        return self.skills.get(skill_id)

    def list_skills(self, *, is_active: bool | None = None) -> list[Skill]:
        conditions: dict[str, Any] = {}
        if is_active is not None:
            conditions["is_active"] = is_active
        return self.skills.filter(**conditions)

    def save_skill_assignment(
        self, assignment: AgentSkillAssignment
    ) -> AgentSkillAssignment:
        return self.skill_assignments.create_or_update(assignment)

    def list_skill_assignments_for_agent(
        self, agent_id: str
    ) -> list[AgentSkillAssignment]:
        return self.skill_assignments.filter(agent_id=agent_id)

    def delete_skill(self, skill_id: str) -> bool:
        return self.skills.delete(skill_id)

    # ── Conversations ────────────────────────────────────────────────

    def save_conversation(self, conversation: Conversation) -> Conversation:
        return self.conversations.create_or_update(conversation)

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self.conversations.get(conversation_id)

    def list_conversations(
        self,
        *,
        agent_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[Conversation]:
        conditions: dict[str, Any] = {}
        if agent_id is not None:
            conditions["agent_id"] = agent_id
        if owner_id is not None:
            conditions["owner_id"] = owner_id
        return self.conversations.filter(**conditions)

    def delete_conversation(self, conversation_id: str) -> bool:
        return self.conversations.delete(conversation_id)

    # ── Messages ─────────────────────────────────────────────────────

    def save_message(self, message: Message) -> Message:
        return self.messages.create_or_update(message)

    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Message]:
        return self.messages.filter(
            conversation_id=conversation_id,
            order_by="created_at",
            limit=limit,
            offset=offset,
        )

    def count_messages(self, conversation_id: str) -> int:
        return self.messages.count(conversation_id=conversation_id)

    # ── Executions ───────────────────────────────────────────────────

    def save_execution(self, execution: Execution) -> Execution:
        return self.executions.create_or_update(execution)

    def get_execution(self, execution_id: str) -> Execution | None:
        return self.executions.get(execution_id)

    def list_executions(
        self,
        *,
        agent_id: str | None = None,
        status: ExecutionStatus | None = None,
    ) -> list[Execution]:
        conditions: dict[str, Any] = {}
        if agent_id is not None:
            conditions["agent_id"] = agent_id
        if status is not None:
            conditions["status"] = status
        return self.executions.filter(**conditions)

    def save_execution_step(self, step: ExecutionStep) -> ExecutionStep:
        return self.execution_steps.create_or_update(step)

    def get_execution_steps(self, execution_id: str) -> list[ExecutionStep]:
        return self.execution_steps.filter(execution_id=execution_id, order_by="order")

    # ── Graphs ───────────────────────────────────────────────────────

    def save_graph(self, graph: Graph) -> Graph:
        return self.graphs.create_or_update(graph)

    def get_graph(self, graph_id: str) -> Graph | None:
        return self.graphs.get(graph_id)

    def get_graph_by_slug(self, slug: str) -> Graph | None:
        results = self.graphs.filter(slug=slug, limit=1)
        return results[0] if results else None

    def list_graphs(
        self,
        *,
        agent_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[Graph]:
        conditions: dict[str, Any] = {}
        if agent_id is not None:
            conditions["agent_id"] = agent_id
        if owner_id is not None:
            conditions["owner_id"] = owner_id
        return self.graphs.filter(**conditions)

    def delete_graph(self, graph_id: str) -> bool:
        return self.graphs.delete(graph_id)

    # ── Memory ───────────────────────────────────────────────────────

    def save_memory(self, memory: AgentMemory) -> AgentMemory:
        return self.memories.create_or_update(memory)

    def get_memory(self, agent_id: str, key: str) -> AgentMemory | None:
        results = self.memories.filter(agent_id=agent_id, key=key, limit=1)
        return results[0] if results else None

    def list_memories(
        self,
        agent_id: str,
        *,
        memory_type: MemoryType | None = None,
    ) -> list[AgentMemory]:
        conditions: dict[str, Any] = {"agent_id": agent_id}
        if memory_type is not None:
            conditions["memory_type"] = memory_type
        return self.memories.filter(**conditions)

    def delete_memory(self, memory_id: str) -> bool:
        return self.memories.delete(memory_id)

    def delete_expired_memories(self) -> int:
        now = datetime.now(UTC).isoformat()
        return self.memories.delete_where(expires_at__lte=now)

    # ── Knowledge ────────────────────────────────────────────────────

    def save_knowledge_source(self, source: KnowledgeSource) -> KnowledgeSource:
        return self.knowledge_sources.create_or_update(source)

    def get_knowledge_source(self, source_id: str) -> KnowledgeSource | None:
        return self.knowledge_sources.get(source_id)

    def list_knowledge_sources(
        self,
        *,
        agent_id: str | None = None,
    ) -> list[KnowledgeSource]:
        if agent_id is not None:
            # agent_ids is stored as JSON array — use LIKE for simple membership check
            return self.knowledge_sources.filter(agent_ids__like=f'%"{agent_id}"%')
        return self.knowledge_sources.all()

    def delete_knowledge_source(self, source_id: str) -> bool:
        return self.knowledge_sources.delete(source_id)

    # ── Transactions & lifecycle ─────────────────────────────────────

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Context manager transactionnel SQLite.

        Pendant la transaction, les repositories ne font pas d'auto-commit.
        Le commit/rollback est géré ici.
        """
        # Disable autocommit on all cached repos
        self._in_transaction = True
        for repo in self._repo_cache.values():
            repo._autocommit = False
        conn = self.connection
        conn.execute("BEGIN")
        try:
            yield
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            # Re-enable autocommit
            self._in_transaction = False
            for repo in self._repo_cache.values():
                repo._autocommit = True

    # ── Observability ────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Retourne des informations de santé sur la base de données."""
        tables = self.get_table_names()
        counts: dict[str, int] = {}
        for table in tables:
            cursor = self.connection.execute(
                f"SELECT COUNT(*) FROM {_q(table)}"
            )  # noqa: S608
            row = cursor.fetchone()
            counts[table] = row[0] if row else 0

        return {
            "database_path": self._database_path,
            "tables": tables,
            "row_counts": counts,
            "registered_models": list(ModelRegistry.get_all().keys()),
        }

    def get_table_names(self) -> list[str]:
        """Retourne la liste des tables existantes dans la base."""
        cursor = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        """Ferme la connexion thread-local."""
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            conn.close()
            self._local.connection = None
        self._repo_cache.clear()


__all__ = [
    "UnifiedStorage",
]
