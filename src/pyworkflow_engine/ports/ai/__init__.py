"""
PyWorkflow Engine — ports/ai : interfaces pures du sous-système IA.

Règle hexagonale :
    Ce package ne contient **aucune implémentation** concrète.
    ``engine/``, ``adapters/ai/``, et les bridges ``adapters/steps/``
    importent depuis ce package.
"""

from __future__ import annotations

from pyworkflow_engine.ports.ai.chunker import BaseChunker, ChunkResult
from pyworkflow_engine.ports.ai.embedder import BaseEmbedder, EmbeddingResult
from pyworkflow_engine.ports.ai.llm import (
    BaseLLMClient,
    LLMRequest,
    LLMResponse,
    StreamChunk,
)
from pyworkflow_engine.ports.ai.parser import BaseDocumentParser, ParseResult
from pyworkflow_engine.ports.ai.runtime import AgentResponse, BaseAgentRuntime
from pyworkflow_engine.ports.ai.skill import BaseSkill
from pyworkflow_engine.ports.ai.storage import BaseAIStorage
from pyworkflow_engine.ports.ai.tool import BaseTool
from pyworkflow_engine.ports.ai.vector_store import BaseVectorStore, SearchResult

__all__ = [
    "AgentResponse",
    "BaseAgentRuntime",
    "BaseLLMClient",
    "LLMRequest",
    "LLMResponse",
    "StreamChunk",
    "BaseTool",
    "BaseSkill",
    "BaseAIStorage",
    # ── Knowledge / RAG (ADR-023) ─────────────────────────────────────
    "BaseVectorStore",
    "SearchResult",
    "BaseEmbedder",
    "EmbeddingResult",
    "BaseChunker",
    "ChunkResult",
    "BaseDocumentParser",
    "ParseResult",
]
