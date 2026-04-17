"""
pyworkflow_engine.models.ai.conversation — Session de chat entre utilisateur et agent.

Adapté de ai_engine/models/conversation.py (ADR-013).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import ConversationStatus
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


@ModelRegistry.register
class Conversation(PersistableModel):
    """Session de conversation entre un utilisateur et un Agent.

    Usage:
        conversation = Conversation(
            title="Research on quantum computing",
            agent_id="agent-uuid",
            owner_id="user-123",
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_conversations",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("title", ColumnType.TEXT),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="ai_agents.id"),
            ColumnDef("owner_id", ColumnType.TEXT),
            ColumnDef("status", ColumnType.TEXT, nullable=False),
            ColumnDef("summary", ColumnType.TEXT),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("message_count", ColumnType.INTEGER),
            ColumnDef("total_tokens", ColumnType.INTEGER),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
            ColumnDef("last_message_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("agent_id",), ("owner_id",), ("status",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(default="", description="Titre de la conversation")

    agent_id: str = Field(
        ..., description="ID de l'Agent participant à la conversation"
    )
    owner_id: str | None = Field(default=None, description="ID du propriétaire")

    status: ConversationStatus = ConversationStatus.ACTIVE

    summary: str = Field(
        default="",
        description="Résumé courant de la conversation (contexte long-terme)",
    )

    metadata: dict[str, Any] = Field(default_factory=dict)

    message_count: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_message_at: datetime | None = None
