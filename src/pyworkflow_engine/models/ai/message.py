"""
pyworkflow_engine.models.ai.message — Messages de conversation IA.

Adapté de ai_engine/models/message.py (ADR-013).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import MessageRole
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


class ToolCall(BaseModel):
    """Représentation d'un appel de fonction (function calling).

    Compatible avec le format OpenAI tool_calls.
    """

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="ID unique de l'appel de tool (ex: call_abc123)",
    )
    name: str = Field(
        ...,
        description="Nom de la fonction appelée (ex: web_search)",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passés à la fonction (parsed JSON)",
    )


class ToolResult(BaseModel):
    """Résultat d'un appel de fonction.

    Associé à un ToolCall via ``tool_call_id``.
    """

    tool_call_id: str = Field(
        ...,
        description="ID du ToolCall auquel ce résultat répond",
    )
    output: str = Field(default="", description="Résultat de l'appel (texte sérialisé)")
    is_error: bool = Field(default=False, description="True si l'appel a échoué")


class TokenUsage(BaseModel):
    """Métriques d'utilisation de tokens pour un message ou une exécution."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Coût estimé en USD",
    )

    @classmethod
    def from_total(cls, total: int, cost: float = 0.0) -> TokenUsage:
        """Crée un TokenUsage à partir du total uniquement."""
        return cls(total_tokens=total, estimated_cost_usd=cost)


@ModelRegistry.register
class Message(PersistableModel):
    """Message dans une conversation avec un Agent.

    Le champ ``metadata`` opaque est éclaté en sous-modèles typés :
      - ``tool_calls`` — appels de fonction
      - ``tool_result`` — résultat d'un appel de fonction
      - ``token_usage`` — métriques de tokens

    Usage:
        msg = Message(
            conversation_id="conv-uuid",
            role=MessageRole.USER,
            content="What is quantum computing?",
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_messages",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef(
                "conversation_id", ColumnType.TEXT, foreign_key="ai_conversations.id"
            ),
            ColumnDef("role", ColumnType.TEXT, nullable=False),
            ColumnDef("content", ColumnType.TEXT),
            ColumnDef("tool_calls", ColumnType.JSON),
            ColumnDef("tool_result", ColumnType.JSON),
            ColumnDef("token_usage", ColumnType.JSON),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("conversation_id",), ("role",), ("created_at",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str = Field(
        ...,
        description="ID de la Conversation à laquelle appartient ce message",
    )
    role: MessageRole
    content: str = Field(default="", description="Contenu textuel du message")

    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Appels de fonction (si role=assistant)",
    )
    tool_result: ToolResult | None = Field(
        default=None,
        description="Résultat d'un appel de fonction (si role=tool)",
    )
    token_usage: TokenUsage | None = Field(
        default=None,
        description="Métriques de tokens pour ce message",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
