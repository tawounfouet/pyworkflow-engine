"""
pyworkflow_engine.models.ai.memory — Mémoire persistante d'un Agent.

Adapté de ai_engine/models/memory.py (ADR-013).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import MemoryType
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


@ModelRegistry.register
class AgentMemory(PersistableModel):
    """Mémoire persistante d'un Agent.

    Usage:
        memory = AgentMemory(
            agent_id="agent-uuid",
            key="user_preferences",
            content='{"language": "fr", "tone": "formal"}',
            memory_type=MemoryType.LONG_TERM,
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_memories",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="ai_agents.id"),
            ColumnDef("memory_type", ColumnType.TEXT),
            ColumnDef("key", ColumnType.TEXT, nullable=False),
            ColumnDef("content", ColumnType.TEXT, nullable=False),
            ColumnDef("embedding", ColumnType.JSON),
            ColumnDef("relevance_score", ColumnType.REAL),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("expires_at", ColumnType.TIMESTAMP),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("agent_id",), ("memory_type",), ("agent_id", "key")],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str = Field(
        ..., description="ID de l'Agent propriétaire de cette mémoire"
    )
    memory_type: MemoryType = MemoryType.LONG_TERM
    key: str = Field(..., description="Clé de la mémoire (ex: user_preferences)")
    content: str = Field(
        ..., description="Contenu mémorisé (texte brut ou JSON sérialisé)"
    )

    embedding: list[float] | None = Field(
        default=None,
        description="Vecteur d'embedding pour recherche sémantique",
    )
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_expired(self) -> bool:
        """True si la mémoire a expiré."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) >= self.expires_at
