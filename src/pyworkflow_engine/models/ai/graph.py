"""
pyworkflow_engine.models.ai.graph — Graphe de workflow AI (LangGraph-style).

Adapté de ai_engine/models/graph.py (ADR-013).
Le JSONField ``definition`` est éclaté en types forts :
  - ``nodes: list[GraphNode]``
  - ``edges: list[GraphEdge]``
  - ``entry_node_id: str | None``
  - ``state_schema: dict``
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import GraphStatus, NodeType
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


class GraphNode(BaseModel):
    """Nœud dans un graph de workflow AI.

    Usage:
        node = GraphNode(
            node_id="researcher",
            name="Research Agent",
            node_type=NodeType.AGENT,
            config={"agent_id": "agent-uuid"},
        )
    """

    node_id: str = Field(..., description="Identifiant unique du nœud dans le graphe")
    name: str = ""
    node_type: NodeType = NodeType.AGENT
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    position_x: float = 0.0
    position_y: float = 0.0


class GraphEdge(BaseModel):
    """Arête (connexion) entre deux nœuds d'un graph.

    Usage:
        edge = GraphEdge(
            source_node_id="researcher",
            target_node_id="writer",
        )
    """

    source_node_id: str = Field(..., description="ID du nœud source")
    target_node_id: str = Field(..., description="ID du nœud cible")
    condition: str = Field(
        default="", description="Condition pour emprunter cette arête"
    )
    label: str = ""


@ModelRegistry.register
class Graph(PersistableModel):
    """Graphe de workflow AI (LangGraph-style).

    Usage:
        graph = Graph(
            name="Research Pipeline",
            agent_id="agent-uuid",
            entry_node_id="start",
            nodes=[...],
            edges=[...],
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_graphs",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("slug", ColumnType.TEXT),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="ai_agents.id"),
            ColumnDef("owner_id", ColumnType.TEXT),
            ColumnDef("nodes", ColumnType.JSON),
            ColumnDef("edges", ColumnType.JSON),
            ColumnDef("entry_node_id", ColumnType.TEXT),
            ColumnDef("state_schema", ColumnType.JSON),
            ColumnDef("status", ColumnType.TEXT),
            ColumnDef("version", ColumnType.INTEGER),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("slug",), ("agent_id",), ("status",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str = ""
    description: str = ""

    agent_id: str = Field(..., description="ID de l'Agent qui exécute ce graph")
    owner_id: str | None = None

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    entry_node_id: str | None = None
    state_schema: dict[str, Any] = Field(default_factory=dict)

    status: GraphStatus = GraphStatus.DRAFT
    version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_node(self, node_id: str) -> GraphNode | None:
        """Retourne un nœud par son ID."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_successors(self, node_id: str) -> list[GraphEdge]:
        """Retourne les arêtes sortantes d'un nœud."""
        return [e for e in self.edges if e.source_node_id == node_id]

    def get_predecessors(self, node_id: str) -> list[GraphEdge]:
        """Retourne les arêtes entrantes d'un nœud."""
        return [e for e in self.edges if e.target_node_id == node_id]
