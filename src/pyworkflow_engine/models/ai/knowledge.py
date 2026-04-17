"""
pyworkflow_engine.models.ai.knowledge — Sources de connaissance pour le RAG.

Adapté de ai_engine/models/knowledge.py (ADR-013).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import IndexStatus, SourceType
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


@ModelRegistry.register
class Chunk(PersistableModel):
    """Fragment de document indexé pour le RAG.

    Usage:
        chunk = Chunk(
            document_id="doc-uuid",
            content="Quantum computing uses qubits...",
            chunk_index=0,
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_chunks",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("document_id", ColumnType.TEXT, foreign_key="ai_documents.id"),
            ColumnDef("content", ColumnType.TEXT, nullable=False),
            ColumnDef("embedding", ColumnType.JSON),
            ColumnDef("chunk_index", ColumnType.INTEGER),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("document_id",), ("chunk_index",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str = Field(..., description="ID du Document parent")
    content: str = Field(..., description="Texte du fragment")
    embedding: list[float] | None = None
    chunk_index: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@ModelRegistry.register
class Document(PersistableModel):
    """Document parsé à partir d'une KnowledgeSource.

    Usage:
        doc = Document(
            source_id="source-uuid",
            title="Quantum Computing 101",
            content="Full document content...",
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_documents",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef(
                "source_id", ColumnType.TEXT, foreign_key="ai_knowledge_sources.id"
            ),
            ColumnDef("title", ColumnType.TEXT),
            ColumnDef("content", ColumnType.TEXT),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("chunk_count", ColumnType.INTEGER),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("source_id",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str = Field(..., description="ID de la KnowledgeSource parente")
    title: str = ""
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@ModelRegistry.register
class KnowledgeSource(PersistableModel):
    """Source de connaissance pour le RAG.

    Usage:
        source = KnowledgeSource(
            name="Company Docs",
            source_type=SourceType.DOCUMENT,
            file_path="/data/company_docs.pdf",
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_knowledge_sources",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("source_type", ColumnType.TEXT, nullable=False),
            ColumnDef("content", ColumnType.TEXT),
            ColumnDef("file_path", ColumnType.TEXT),
            ColumnDef("url", ColumnType.TEXT),
            ColumnDef("index_status", ColumnType.TEXT),
            ColumnDef("chunks_count", ColumnType.INTEGER),
            ColumnDef("last_indexed_at", ColumnType.TIMESTAMP),
            ColumnDef("agent_ids", ColumnType.JSON),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("source_type",), ("index_status",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str = ""
    source_type: SourceType

    content: str = Field(default="", description="Contenu brut (si source_type=text)")
    file_path: str | None = Field(
        default=None,
        description="Chemin vers le fichier (si source_type=document)",
    )
    url: str | None = Field(
        default=None,
        description="URL de la source (si source_type=url)",
    )

    index_status: IndexStatus = IndexStatus.PENDING
    chunks_count: int = Field(default=0, ge=0)
    last_indexed_at: datetime | None = None

    agent_ids: list[str] = Field(
        default_factory=list,
        description="IDs des Agents ayant accès à cette source",
    )

    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
