"""
pyworkflow_engine.models.ai.execution — Suivi d'exécution d'un Agent IA.

Adapté de ai_engine/models/execution.py (ADR-013).
Utilise ``ExecutionStatus`` (alias de ``RunStatus``) pour la cohérence avec le core.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.message import TokenUsage
from pyworkflow_engine.models.ai.types import AIStepType, ExecutionStatus
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


@ModelRegistry.register
class ExecutionStep(PersistableModel):
    """Étape individuelle dans une Execution IA.

    Chaque appel LLM, appel de tool, ou décision est tracé ici.

    Usage:
        step = ExecutionStep(
            execution_id="exec-uuid",
            step_type=AIStepType.LLM_CALL,
            order=1,
            input_data={"prompt": "..."},
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_execution_steps",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("execution_id", ColumnType.TEXT, foreign_key="ai_executions.id"),
            ColumnDef("step_type", ColumnType.TEXT, nullable=False),
            ColumnDef("order", ColumnType.INTEGER),
            ColumnDef("input_data", ColumnType.JSON),
            ColumnDef("output_data", ColumnType.JSON),
            ColumnDef("error", ColumnType.TEXT),
            ColumnDef("agent_id", ColumnType.TEXT),
            ColumnDef("tool_id", ColumnType.TEXT),
            ColumnDef("token_usage", ColumnType.JSON),
            ColumnDef("tokens_used", ColumnType.INTEGER),
            ColumnDef("cost", ColumnType.REAL),
            ColumnDef("duration_ms", ColumnType.INTEGER),
            ColumnDef("started_at", ColumnType.TIMESTAMP),
            ColumnDef("completed_at", ColumnType.TIMESTAMP),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("execution_id",), ("step_type",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    execution_id: str = Field(..., description="ID de l'Execution parente")
    step_type: AIStepType
    order: int = Field(default=0, ge=0)

    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""

    # Champs IA optionnels (ADR-013)
    agent_id: str | None = Field(
        default=None,
        description="ID de l'Agent IA exécutant cette étape",
    )
    tool_id: str | None = Field(
        default=None,
        description="ID du ToolDefinition utilisé (si step_type=tool_call)",
    )
    token_usage: TokenUsage | None = Field(
        default=None,
        description="Métriques de tokens pour cette étape",
    )

    tokens_used: int = Field(default=0, ge=0)
    cost: float = Field(default=0.0, ge=0.0, description="Coût de cette étape en USD")
    duration_ms: int = Field(default=0, ge=0)

    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@ModelRegistry.register
class Execution(PersistableModel):
    """Session d'exécution d'un Agent IA.

    Trace une exécution complète : du prompt initial au résultat final.

    Usage:
        execution = Execution(
            agent_id="agent-uuid",
            input_data={"prompt": "Analyse ce document"},
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_executions",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="ai_agents.id"),
            ColumnDef("graph_id", ColumnType.TEXT),
            ColumnDef(
                "conversation_id", ColumnType.TEXT, foreign_key="ai_conversations.id"
            ),
            ColumnDef("status", ColumnType.TEXT, nullable=False),
            ColumnDef("input_data", ColumnType.JSON),
            ColumnDef("output_data", ColumnType.JSON),
            ColumnDef("error", ColumnType.TEXT),
            ColumnDef("token_usage", ColumnType.JSON),
            ColumnDef("total_steps", ColumnType.INTEGER),
            ColumnDef("started_at", ColumnType.TIMESTAMP),
            ColumnDef("completed_at", ColumnType.TIMESTAMP),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
            ColumnDef("metadata", ColumnType.JSON),
        ],
        indexes=[("agent_id",), ("conversation_id",), ("status",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str = Field(..., description="ID de l'Agent qui exécute")
    graph_id: str | None = None
    conversation_id: str | None = None

    status: ExecutionStatus = ExecutionStatus.PENDING

    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""

    token_usage: TokenUsage = Field(
        default_factory=TokenUsage,
        description="Métriques de tokens agrégées pour toute l'exécution",
    )
    total_steps: int = Field(default=0, ge=0)

    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    metadata: dict[str, Any] = Field(default_factory=dict)
