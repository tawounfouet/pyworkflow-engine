"""
pyworkflow_engine.models.ai.tool — Définition d'outil IA (function calling).

Adapté de ai_engine/models/tool.py (ADR-013).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import ToolType
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


@ModelRegistry.register
class ToolDefinition(PersistableModel):
    """Définition d'un outil technique utilisable par un Agent.

    Usage:
        tool = ToolDefinition(
            key="web_search",
            name="Web Search",
            description="Search the web for information",
            tool_type=ToolType.API,
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_tools",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("key", ColumnType.TEXT, nullable=False),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("tool_type", ColumnType.TEXT),
            ColumnDef("parameters_schema", ColumnType.JSON),
            ColumnDef("function_path", ColumnType.TEXT),
            ColumnDef("connector_id", ColumnType.TEXT),
            ColumnDef("config", ColumnType.JSON),
            ColumnDef("requires_approval", ColumnType.BOOLEAN),
            ColumnDef("is_dangerous", ColumnType.BOOLEAN),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("key",), ("tool_type",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    key: str = Field(..., description="Identifiant unique du tool (ex: web_search)")
    name: str
    description: str = Field(
        default="",
        description="Description pour le LLM (utilisée dans function calling)",
    )

    tool_type: ToolType = ToolType.FUNCTION

    parameters_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema des paramètres (format OpenAI function calling)",
    )

    function_path: str = Field(
        default="",
        description="Chemin Python vers la fonction (ex: mypackage.tools.execute)",
    )

    connector_id: str | None = Field(
        default=None,
        description="ID du Connector lié (si tool_type=connector)",
    )

    config: dict[str, Any] = Field(default_factory=dict)

    requires_approval: bool = False
    is_dangerous: bool = False
    is_active: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_function_schema(self) -> dict[str, Any]:
        """Retourne le schema au format OpenAI function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.key,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
