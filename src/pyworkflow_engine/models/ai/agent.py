"""
pyworkflow_engine.models.ai.agent — Agent AI (configuration comportementale).

Adapté de ai_engine/models/agent.py (ADR-013).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import AgentRole
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


class AgentConfig(BaseModel):
    """Configuration comportementale d'un agent."""

    max_iterations: int = Field(default=10, ge=1)
    max_tokens_per_run: int = Field(default=8000, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens_per_response: int | None = None
    enable_memory: bool = True
    enable_tools: bool = True
    enable_rag: bool = False
    retry_on_failure: bool = True
    max_retries: int = 3
    extra: dict[str, object] = Field(default_factory=dict)


@ModelRegistry.register
class Agent(PersistableModel):
    """Agent AI — acteur intelligent qui utilise un Provider LLM.

    Usage:
        agent = Agent(
            name="Research Assistant",
            slug="research-assistant",
            role=AgentRole.RESEARCHER,
            provider_id="provider-uuid",
            system_prompt="Tu es un chercheur expert...",
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_agents",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("slug", ColumnType.TEXT),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("role", ColumnType.TEXT, nullable=False),
            ColumnDef("provider_id", ColumnType.TEXT, foreign_key="ai_providers.id"),
            ColumnDef("model", ColumnType.TEXT),
            ColumnDef("system_prompt", ColumnType.TEXT),
            ColumnDef("welcome_message", ColumnType.TEXT),
            ColumnDef("config", ColumnType.JSON),
            ColumnDef("tool_ids", ColumnType.JSON),
            ColumnDef("skill_ids", ColumnType.JSON),
            ColumnDef("knowledge_base_ids", ColumnType.JSON),
            ColumnDef("owner_id", ColumnType.TEXT),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("slug",), ("role",), ("provider_id",), ("owner_id",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str = ""
    description: str = ""
    role: AgentRole = AgentRole.ASSISTANT

    provider_id: str = Field(
        ...,
        description="ID du LLMProviderConfig utilisé par cet agent",
    )
    model: str | None = Field(
        default=None,
        description="Override du modèle LLM (None = utiliser le default_model du provider)",
    )

    system_prompt: str = Field(default="", description="Prompt système de l'agent")
    welcome_message: str = Field(
        default="", description="Message d'accueil (optionnel)"
    )

    config: AgentConfig = Field(default_factory=AgentConfig)

    tool_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    knowledge_base_ids: list[str] = Field(default_factory=list)

    owner_id: str | None = None

    is_active: bool = True
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_effective_temperature(self) -> float | None:
        """Retourne la temperature effective (agent override ou None pour provider default)."""
        return self.config.temperature
