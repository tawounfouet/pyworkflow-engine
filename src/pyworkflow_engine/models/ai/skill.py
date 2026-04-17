"""
pyworkflow_engine.models.ai.skill — Compétences de haut niveau pour les agents.

Adapté de ai_engine/models/skill.py (ADR-013).

Skill vs Tool :
  - Tool = Fonction technique atomique (API call, DB query)
  - Skill = Capacité combinant plusieurs tools + raisonnement
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import Proficiency, SkillCategory
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


@ModelRegistry.register
class Skill(PersistableModel):
    """Capacité de haut niveau pour un Agent.

    Usage:
        skill = Skill(
            key="research",
            name="Research Skill",
            category=SkillCategory.RESEARCH,
            system_prompt="Tu es un chercheur expert...",
            required_tool_ids=["web_search_id", "summarize_id"],
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_skills",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("key", ColumnType.TEXT, nullable=False),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("category", ColumnType.TEXT),
            ColumnDef("system_prompt", ColumnType.TEXT),
            ColumnDef("required_tool_ids", ColumnType.JSON),
            ColumnDef("config", ColumnType.JSON),
            ColumnDef("recommended_provider_id", ColumnType.TEXT),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("key",), ("category",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    key: str = Field(..., description="Identifiant unique du skill (ex: research)")
    name: str
    description: str = ""
    category: SkillCategory = SkillCategory.CUSTOM

    system_prompt: str = Field(
        default="", description="Instructions système pour ce skill"
    )
    required_tool_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    recommended_provider_id: str | None = None

    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@ModelRegistry.register
class AgentSkillAssignment(PersistableModel):
    """Association Agent-Skill avec configuration.

    Usage:
        assignment = AgentSkillAssignment(
            agent_id="agent-uuid",
            skill_id="skill-uuid",
            proficiency=Proficiency.ADVANCED,
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_agent_skill_assignments",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="ai_agents.id"),
            ColumnDef("skill_id", ColumnType.TEXT, foreign_key="ai_skills.id"),
            ColumnDef("provider_override_id", ColumnType.TEXT),
            ColumnDef("proficiency", ColumnType.TEXT),
            ColumnDef("enabled", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("agent_id",), ("skill_id",), ("agent_id", "skill_id")],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str = Field(..., description="ID de l'Agent")
    skill_id: str = Field(..., description="ID du Skill")

    provider_override_id: str | None = Field(
        default=None,
        description="ID du LLMProviderConfig override pour cet agent",
    )
    proficiency: Proficiency = Proficiency.INTERMEDIATE
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
