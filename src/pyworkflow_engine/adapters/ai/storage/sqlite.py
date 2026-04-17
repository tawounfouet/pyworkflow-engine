"""
adapters/ai/storage/sqlite — Backend SQLite durable pour le sous-système IA.

Implémentation de ``BaseAIStorage`` sur SQLite via stdlib ``sqlite3``.
Thread-safe (connexion thread-locale, WAL mode).

Toutes les entités Pydantic sont sérialisées en JSON pour les colonnes
TEXT / JSON et désérialisées à la lecture via ``model_validate_json``.

Usage::

    storage = SQLiteAIStorage("workflow.db")
    storage.save_provider(provider)
    agent = storage.get_agent("agent-uuid")

Architecture : ADR-020 (Phase 1a)
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

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
from pyworkflow_engine.ports.ai.storage import BaseAIStorage

if TYPE_CHECKING:
    from collections.abc import Iterator


# ── DDL (tables Rich API) ────────────────────────────────────────────────────

_AI_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ai_providers (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,   -- JSON (LLMProviderConfig)
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_agents (
    id TEXT PRIMARY KEY,
    slug TEXT,
    role TEXT,
    owner_id TEXT,
    is_active INTEGER DEFAULT 1,
    data TEXT NOT NULL,   -- JSON (Agent)
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_agents_slug ON ai_agents(slug);
CREATE INDEX IF NOT EXISTS idx_ai_agents_role ON ai_agents(role);
CREATE INDEX IF NOT EXISTS idx_ai_agents_owner_id ON ai_agents(owner_id);

CREATE TABLE IF NOT EXISTS ai_tools (
    id TEXT PRIMARY KEY,
    key TEXT,
    is_active INTEGER DEFAULT 1,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_tools_key ON ai_tools(key);

CREATE TABLE IF NOT EXISTS ai_skills (
    id TEXT PRIMARY KEY,
    is_active INTEGER DEFAULT 1,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_skill_assignments (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_skill_assignments_agent_id ON ai_skill_assignments(agent_id);

CREATE TABLE IF NOT EXISTS ai_conversations (
    id TEXT PRIMARY KEY,
    agent_id TEXT,
    owner_id TEXT,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_conversations_agent_id ON ai_conversations(agent_id);
CREATE INDEX IF NOT EXISTS idx_ai_conversations_owner_id ON ai_conversations(owner_id);

CREATE TABLE IF NOT EXISTS ai_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation_id ON ai_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_ai_messages_created_at ON ai_messages(created_at);

CREATE TABLE IF NOT EXISTS ai_executions (
    id TEXT PRIMARY KEY,
    agent_id TEXT,
    status TEXT,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_executions_agent_id ON ai_executions(agent_id);
CREATE INDEX IF NOT EXISTS idx_ai_executions_status ON ai_executions(status);

CREATE TABLE IF NOT EXISTS ai_execution_steps (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    step_order INTEGER DEFAULT 0,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_execution_steps_execution_id ON ai_execution_steps(execution_id);

CREATE TABLE IF NOT EXISTS ai_graphs (
    id TEXT PRIMARY KEY,
    slug TEXT,
    agent_id TEXT,
    owner_id TEXT,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_graphs_slug ON ai_graphs(slug);
CREATE INDEX IF NOT EXISTS idx_ai_graphs_agent_id ON ai_graphs(agent_id);

CREATE TABLE IF NOT EXISTS ai_memories (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    memory_type TEXT,
    key_name TEXT NOT NULL,
    expires_at TIMESTAMP,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_memories_agent_id ON ai_memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_ai_memories_agent_key ON ai_memories(agent_id, key_name);

CREATE TABLE IF NOT EXISTS ai_knowledge_sources (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _serialize(obj: Any) -> str:
    """Sérialise un modèle Pydantic ou un dict en JSON."""
    if hasattr(obj, "model_dump_json"):
        return obj.model_dump_json()
    return json.dumps(obj)


def _deserialize(cls: type, data: str) -> Any:
    """Désérialise du JSON en modèle Pydantic."""
    return cls.model_validate_json(data)


# ── SQLiteAIStorage ──────────────────────────────────────────────────────────


class SQLiteAIStorage(BaseAIStorage):
    """Backend SQLite durable pour le sous-système IA.

    Thread-safe : connexion thread-locale (clé = thread-id + instance-id pour
    isoler les bases ``:memory:`` entre instances distinctes).
    WAL mode pour les lectures concurrentes.

    Args:
        database_path: Chemin du fichier SQLite. Peut être ``:memory:``
            pour les tests.

    Usage::

        storage = SQLiteAIStorage("workflow.db")
        with storage:
            storage.save_provider(provider)
            agent = storage.get_agent("uuid")
    """

    def __init__(self, database_path: str | Path = "workflow.db") -> None:
        self._db_path = str(database_path)  # keep ":memory:" as-is
        if self._db_path != ":memory:":
            self._db_path = str(Path(self._db_path).expanduser().resolve())
        # Unique key per instance so :memory: DBs are never shared across
        # different SQLiteAIStorage objects even within the same thread.
        self._conn_key = f"_ai_conn_{id(self)}"
        self._local = threading.local()
        self._lock = threading.RLock()
        self._in_transaction = False
        self._init_schema()

    # ── Connexion ────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Connexion thread-locale avec WAL + foreign_keys.

        La clé inclut ``id(self)`` de sorte que chaque instance dispose de sa
        propre connexion, même en mémoire (:memory:).
        """
        if not hasattr(self._local, self._conn_key):
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            setattr(self._local, self._conn_key, conn)
        return getattr(self._local, self._conn_key)

    def _init_schema(self) -> None:
        """Crée les tables IA si elles n'existent pas encore."""
        with self._lock:
            conn = self._get_conn()
            conn.executescript(_AI_SCHEMA_SQL)
            conn.commit()

    def _commit(self) -> None:
        """Commit uniquement si aucune transaction englobante n'est active."""
        if not self._in_transaction:
            self._get_conn().commit()

    def close(self) -> None:
        """Ferme la connexion du thread courant."""
        if hasattr(self._local, self._conn_key):
            try:
                getattr(self._local, self._conn_key).close()
            except Exception:  # noqa: BLE001
                pass
            try:
                delattr(self._local, self._conn_key)
            except AttributeError:
                pass

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Context manager pour les opérations transactionnelles.

        Toutes les opérations de lecture/écriture effectuées à l'intérieur
        du bloc partagent la même transaction SQLite.  En cas d'exception la
        transaction est annulée (rollback).
        """
        conn = self._get_conn()
        with self._lock:
            self._in_transaction = True
            try:
                yield
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._in_transaction = False

    # ── Providers ────────────────────────────────────────────────────

    def save_provider(self, provider: LLMProviderConfig) -> LLMProviderConfig:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_providers (id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (provider.id, _serialize(provider), now, now),
            )
            self._commit()
        return provider

    def get_provider(self, provider_id: str) -> LLMProviderConfig | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_providers WHERE id = ?", (provider_id,)
        ).fetchone()
        return _deserialize(LLMProviderConfig, row["data"]) if row else None

    def get_provider_by_name(self, name: str) -> LLMProviderConfig | None:
        conn = self._get_conn()
        rows = conn.execute("SELECT data FROM ai_providers").fetchall()
        for row in rows:
            p = _deserialize(LLMProviderConfig, row["data"])
            if p.name == name:
                return p
        return None

    def list_providers(
        self, *, is_active: bool | None = None
    ) -> list[LLMProviderConfig]:
        conn = self._get_conn()
        rows = conn.execute("SELECT data FROM ai_providers").fetchall()
        providers = [_deserialize(LLMProviderConfig, r["data"]) for r in rows]
        if is_active is not None:
            providers = [p for p in providers if p.is_active == is_active]
        return providers

    def delete_provider(self, provider_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM ai_providers WHERE id = ?", (provider_id,)
            )
            self._commit()
        return cursor.rowcount > 0

    # ── Agents ───────────────────────────────────────────────────────

    def save_agent(self, agent: Agent) -> Agent:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_agents
                    (id, slug, role, owner_id, is_active, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    slug=excluded.slug, role=excluded.role,
                    owner_id=excluded.owner_id, is_active=excluded.is_active,
                    data=excluded.data, updated_at=excluded.updated_at
                """,
                (
                    agent.id,
                    agent.slug,
                    agent.role.value,
                    agent.owner_id,
                    int(agent.is_active),
                    _serialize(agent),
                    now,
                    now,
                ),
            )
            self._commit()
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_agents WHERE id = ?", (agent_id,)
        ).fetchone()
        return _deserialize(Agent, row["data"]) if row else None

    def get_agent_by_slug(self, slug: str) -> Agent | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_agents WHERE slug = ?", (slug,)
        ).fetchone()
        return _deserialize(Agent, row["data"]) if row else None

    def list_agents(
        self,
        *,
        owner_id: str | None = None,
        role: AgentRole | None = None,
        is_active: bool | None = None,
    ) -> list[Agent]:
        sql = "SELECT data FROM ai_agents WHERE 1=1"
        params: list[Any] = []
        if owner_id is not None:
            sql += " AND owner_id = ?"
            params.append(owner_id)
        if role is not None:
            sql += " AND role = ?"
            params.append(role.value)
        if is_active is not None:
            sql += " AND is_active = ?"
            params.append(int(is_active))
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [_deserialize(Agent, r["data"]) for r in rows]

    def delete_agent(self, agent_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM ai_agents WHERE id = ?", (agent_id,))
            self._commit()
        return cursor.rowcount > 0

    # ── Tools ────────────────────────────────────────────────────────

    def save_tool(self, tool: ToolDefinition) -> ToolDefinition:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_tools (id, key, is_active, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    key=excluded.key, is_active=excluded.is_active,
                    data=excluded.data, updated_at=excluded.updated_at
                """,
                (
                    tool.id,
                    tool.key,
                    int(tool.is_active),
                    _serialize(tool),
                    now,
                    now,
                ),
            )
            self._commit()
        return tool

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_tools WHERE id = ?", (tool_id,)
        ).fetchone()
        return _deserialize(ToolDefinition, row["data"]) if row else None

    def get_tool_by_key(self, key: str) -> ToolDefinition | None:
        conn = self._get_conn()
        row = conn.execute("SELECT data FROM ai_tools WHERE key = ?", (key,)).fetchone()
        return _deserialize(ToolDefinition, row["data"]) if row else None

    def list_tools(self, *, is_active: bool | None = None) -> list[ToolDefinition]:
        sql = "SELECT data FROM ai_tools WHERE 1=1"
        params: list[Any] = []
        if is_active is not None:
            sql += " AND is_active = ?"
            params.append(int(is_active))
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [_deserialize(ToolDefinition, r["data"]) for r in rows]

    def list_tools_for_agent(self, agent_id: str) -> list[ToolDefinition]:
        agent = self.get_agent(agent_id)
        if not agent or not agent.tool_ids:
            return []
        placeholders = ",".join("?" * len(agent.tool_ids))
        conn = self._get_conn()
        rows = conn.execute(
            f"SELECT data FROM ai_tools WHERE id IN ({placeholders})",
            agent.tool_ids,
        ).fetchall()
        return [_deserialize(ToolDefinition, r["data"]) for r in rows]

    def delete_tool(self, tool_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM ai_tools WHERE id = ?", (tool_id,))
            self._commit()
        return cursor.rowcount > 0

    # ── Skills ───────────────────────────────────────────────────────

    def save_skill(self, skill: Skill) -> Skill:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_skills (id, is_active, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    is_active=excluded.is_active, data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (skill.id, int(skill.is_active), _serialize(skill), now, now),
            )
            self._commit()
        return skill

    def get_skill(self, skill_id: str) -> Skill | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_skills WHERE id = ?", (skill_id,)
        ).fetchone()
        return _deserialize(Skill, row["data"]) if row else None

    def list_skills(self, *, is_active: bool | None = None) -> list[Skill]:
        sql = "SELECT data FROM ai_skills WHERE 1=1"
        params: list[Any] = []
        if is_active is not None:
            sql += " AND is_active = ?"
            params.append(int(is_active))
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [_deserialize(Skill, r["data"]) for r in rows]

    def save_skill_assignment(
        self, assignment: AgentSkillAssignment
    ) -> AgentSkillAssignment:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_skill_assignments (id, agent_id, data, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data
                """,
                (assignment.id, assignment.agent_id, _serialize(assignment), now),
            )
            self._commit()
        return assignment

    def list_skill_assignments_for_agent(
        self, agent_id: str
    ) -> list[AgentSkillAssignment]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT data FROM ai_skill_assignments WHERE agent_id = ?", (agent_id,)
        ).fetchall()
        return [_deserialize(AgentSkillAssignment, r["data"]) for r in rows]

    def delete_skill(self, skill_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM ai_skills WHERE id = ?", (skill_id,))
            self._commit()
        return cursor.rowcount > 0

    # ── Conversations ────────────────────────────────────────────────

    def save_conversation(self, conversation: Conversation) -> Conversation:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_conversations
                    (id, agent_id, owner_id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    agent_id=excluded.agent_id, owner_id=excluded.owner_id,
                    data=excluded.data, updated_at=excluded.updated_at
                """,
                (
                    conversation.id,
                    conversation.agent_id,
                    conversation.owner_id,
                    _serialize(conversation),
                    now,
                    now,
                ),
            )
            self._commit()
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return _deserialize(Conversation, row["data"]) if row else None

    def list_conversations(
        self,
        *,
        agent_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[Conversation]:
        sql = "SELECT data FROM ai_conversations WHERE 1=1"
        params: list[Any] = []
        if agent_id is not None:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if owner_id is not None:
            sql += " AND owner_id = ?"
            params.append(owner_id)
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [_deserialize(Conversation, r["data"]) for r in rows]

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM ai_conversations WHERE id = ?", (conversation_id,)
            )
            self._commit()
        return cursor.rowcount > 0

    # ── Messages ─────────────────────────────────────────────────────

    def save_message(self, message: Message) -> Message:
        now = message.created_at.isoformat() if message.created_at else _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_messages
                    (id, conversation_id, role, created_at, data)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data
                """,
                (
                    message.id,
                    message.conversation_id,
                    message.role.value,
                    now,
                    _serialize(message),
                ),
            )
            self._commit()
        return message

    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Message]:
        sql = (
            "SELECT data FROM ai_messages WHERE conversation_id = ? "
            "ORDER BY created_at ASC"
        )
        params: list[Any] = [conversation_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [_deserialize(Message, r["data"]) for r in rows]

    def count_messages(self, conversation_id: str) -> int:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM ai_messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    # ── Executions ───────────────────────────────────────────────────

    def save_execution(self, execution: Execution) -> Execution:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_executions
                    (id, agent_id, status, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status, data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (
                    execution.id,
                    execution.agent_id,
                    (
                        execution.status.value
                        if hasattr(execution.status, "value")
                        else str(execution.status)
                    ),
                    _serialize(execution),
                    now,
                    now,
                ),
            )
            self._commit()
        return execution

    def get_execution(self, execution_id: str) -> Execution | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_executions WHERE id = ?", (execution_id,)
        ).fetchone()
        return _deserialize(Execution, row["data"]) if row else None

    def list_executions(
        self,
        *,
        agent_id: str | None = None,
        status: ExecutionStatus | None = None,
    ) -> list[Execution]:
        sql = "SELECT data FROM ai_executions WHERE 1=1"
        params: list[Any] = []
        if agent_id is not None:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value if hasattr(status, "value") else str(status))
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [_deserialize(Execution, r["data"]) for r in rows]

    def save_execution_step(self, step: ExecutionStep) -> ExecutionStep:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_execution_steps
                    (id, execution_id, step_order, data, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    step_order=excluded.step_order, data=excluded.data
                """,
                (step.id, step.execution_id, step.order, _serialize(step), now),
            )
            self._commit()
        return step

    def get_execution_steps(self, execution_id: str) -> list[ExecutionStep]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT data FROM ai_execution_steps WHERE execution_id = ? "
            "ORDER BY step_order ASC",
            (execution_id,),
        ).fetchall()
        return [_deserialize(ExecutionStep, r["data"]) for r in rows]

    # ── Graphs ───────────────────────────────────────────────────────

    def save_graph(self, graph: Graph) -> Graph:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_graphs
                    (id, slug, agent_id, owner_id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    slug=excluded.slug, agent_id=excluded.agent_id,
                    owner_id=excluded.owner_id, data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (
                    graph.id,
                    graph.slug,
                    graph.agent_id,
                    graph.owner_id,
                    _serialize(graph),
                    now,
                    now,
                ),
            )
            self._commit()
        return graph

    def get_graph(self, graph_id: str) -> Graph | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_graphs WHERE id = ?", (graph_id,)
        ).fetchone()
        return _deserialize(Graph, row["data"]) if row else None

    def get_graph_by_slug(self, slug: str) -> Graph | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_graphs WHERE slug = ?", (slug,)
        ).fetchone()
        return _deserialize(Graph, row["data"]) if row else None

    def list_graphs(
        self,
        *,
        agent_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[Graph]:
        sql = "SELECT data FROM ai_graphs WHERE 1=1"
        params: list[Any] = []
        if agent_id is not None:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if owner_id is not None:
            sql += " AND owner_id = ?"
            params.append(owner_id)
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [_deserialize(Graph, r["data"]) for r in rows]

    def delete_graph(self, graph_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM ai_graphs WHERE id = ?", (graph_id,))
            self._commit()
        return cursor.rowcount > 0

    # ── Memory ───────────────────────────────────────────────────────

    def save_memory(self, memory: AgentMemory) -> AgentMemory:
        now = _now_iso()
        expires = memory.expires_at.isoformat() if memory.expires_at else None
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_memories
                    (id, agent_id, memory_type, key_name, expires_at,
                     data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    memory_type=excluded.memory_type, key_name=excluded.key_name,
                    expires_at=excluded.expires_at, data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (
                    memory.id,
                    memory.agent_id,
                    memory.memory_type.value,
                    memory.key,
                    expires,
                    _serialize(memory),
                    now,
                    now,
                ),
            )
            self._commit()
        return memory

    def get_memory(self, agent_id: str, key: str) -> AgentMemory | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_memories WHERE agent_id = ? AND key_name = ?",
            (agent_id, key),
        ).fetchone()
        return _deserialize(AgentMemory, row["data"]) if row else None

    def list_memories(
        self,
        agent_id: str,
        *,
        memory_type: MemoryType | None = None,
    ) -> list[AgentMemory]:
        sql = "SELECT data FROM ai_memories WHERE agent_id = ?"
        params: list[Any] = [agent_id]
        if memory_type is not None:
            sql += " AND memory_type = ?"
            params.append(memory_type.value)
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [_deserialize(AgentMemory, r["data"]) for r in rows]

    def delete_memory(self, memory_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM ai_memories WHERE id = ?", (memory_id,))
            self._commit()
        return cursor.rowcount > 0

    def delete_expired_memories(self) -> int:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM ai_memories WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            self._commit()
        return cursor.rowcount

    # ── Knowledge ────────────────────────────────────────────────────

    def save_knowledge_source(self, source: KnowledgeSource) -> KnowledgeSource:
        now = _now_iso()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO ai_knowledge_sources (id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (source.id, _serialize(source), now, now),
            )
            self._commit()
        return source

    def get_knowledge_source(self, source_id: str) -> KnowledgeSource | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data FROM ai_knowledge_sources WHERE id = ?", (source_id,)
        ).fetchone()
        return _deserialize(KnowledgeSource, row["data"]) if row else None

    def list_knowledge_sources(
        self, *, agent_id: str | None = None
    ) -> list[KnowledgeSource]:
        conn = self._get_conn()
        rows = conn.execute("SELECT data FROM ai_knowledge_sources").fetchall()
        sources = [_deserialize(KnowledgeSource, r["data"]) for r in rows]
        if agent_id is not None:
            sources = [
                s
                for s in sources
                if hasattr(s, "agent_ids") and agent_id in s.agent_ids
            ]
        return sources

    def delete_knowledge_source(self, source_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM ai_knowledge_sources WHERE id = ?", (source_id,)
            )
            self._commit()
        return cursor.rowcount > 0
