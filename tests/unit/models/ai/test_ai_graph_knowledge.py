"""
Tests unitaires — models/ai/graph.py + models/ai/knowledge.py (ADR-013, Phase 3.2).
"""

from __future__ import annotations

import pytest

from pyworkflow_engine.models.ai.graph import Graph, GraphEdge, GraphNode
from pyworkflow_engine.models.ai.knowledge import Chunk, Document, KnowledgeSource
from pyworkflow_engine.models.ai.types import (
    GraphStatus,
    IndexStatus,
    NodeType,
    SourceType,
)


# ── GraphNode ─────────────────────────────────────────────────────────────────


class TestGraphNode:
    def test_creation(self):
        n = GraphNode(node_id="start", node_type=NodeType.INPUT)
        assert n.node_id == "start"
        assert n.node_type == NodeType.INPUT
        assert n.config == {}

    def test_position_default(self):
        n = GraphNode(node_id="n1")
        assert n.position_x == 0.0
        assert n.position_y == 0.0


# ── GraphEdge ─────────────────────────────────────────────────────────────────


class TestGraphEdge:
    def test_creation(self):
        e = GraphEdge(source_node_id="a", target_node_id="b")
        assert e.source_node_id == "a"
        assert e.target_node_id == "b"
        assert e.condition == ""
        assert e.label == ""


# ── Graph ─────────────────────────────────────────────────────────────────────


class TestGraph:
    def _make_graph(self) -> Graph:
        nodes = [
            GraphNode(node_id="start", node_type=NodeType.INPUT),
            GraphNode(node_id="worker", node_type=NodeType.AGENT),
            GraphNode(node_id="end", node_type=NodeType.OUTPUT),
        ]
        edges = [
            GraphEdge(source_node_id="start", target_node_id="worker"),
            GraphEdge(source_node_id="worker", target_node_id="end"),
        ]
        return Graph(
            name="Test Pipeline",
            agent_id="agent-uuid",
            entry_node_id="start",
            nodes=nodes,
            edges=edges,
        )

    def test_creation(self):
        g = self._make_graph()
        assert g.name == "Test Pipeline"
        assert g.status == GraphStatus.DRAFT
        assert g.version == 1
        assert g.entry_node_id == "start"

    def test_id_auto_generated(self):
        g1 = Graph(name="G1", agent_id="a")
        g2 = Graph(name="G2", agent_id="a")
        assert g1.id != g2.id

    def test_get_node_found(self):
        g = self._make_graph()
        node = g.get_node("worker")
        assert node is not None
        assert node.node_type == NodeType.AGENT

    def test_get_node_not_found(self):
        g = self._make_graph()
        assert g.get_node("nonexistent") is None

    def test_get_successors(self):
        g = self._make_graph()
        succs = g.get_successors("start")
        assert len(succs) == 1
        assert succs[0].target_node_id == "worker"

    def test_get_predecessors(self):
        g = self._make_graph()
        preds = g.get_predecessors("end")
        assert len(preds) == 1
        assert preds[0].source_node_id == "worker"

    def test_get_successors_empty(self):
        g = self._make_graph()
        assert g.get_successors("end") == []


# ── Chunk ─────────────────────────────────────────────────────────────────────


class TestChunk:
    def test_creation(self):
        c = Chunk(document_id="doc-1", content="Some text", chunk_index=0)
        assert c.content == "Some text"
        assert c.chunk_index == 0
        assert c.embedding is None

    def test_with_embedding(self):
        c = Chunk(document_id="doc-1", content="text", embedding=[0.1, 0.2, 0.3])
        assert len(c.embedding) == 3  # type: ignore[arg-type]

    def test_chunk_index_ge_0(self):
        with pytest.raises(Exception):
            Chunk(document_id="doc-1", content="text", chunk_index=-1)


# ── Document ──────────────────────────────────────────────────────────────────


class TestDocument:
    def test_creation(self):
        d = Document(source_id="src-1", title="My Doc", content="Full text")
        assert d.title == "My Doc"
        assert d.chunk_count == 0


# ── KnowledgeSource ───────────────────────────────────────────────────────────


class TestKnowledgeSource:
    def test_document_source(self):
        ks = KnowledgeSource(
            name="Company Docs",
            source_type=SourceType.DOCUMENT,
            file_path="/data/docs.pdf",
        )
        assert ks.source_type == SourceType.DOCUMENT
        assert ks.file_path == "/data/docs.pdf"
        assert ks.index_status == IndexStatus.PENDING
        assert ks.is_active is True
        assert ks.agent_ids == []

    def test_url_source(self):
        ks = KnowledgeSource(
            name="Web Source",
            source_type=SourceType.URL,
            url="https://example.com/docs",
        )
        assert ks.url == "https://example.com/docs"

    def test_text_source(self):
        ks = KnowledgeSource(
            name="Inline Text",
            source_type=SourceType.TEXT,
            content="Direct text content",
        )
        assert ks.content == "Direct text content"
