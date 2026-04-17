"""
Adapters Knowledge/RAG — implémentations concrètes des ports AI (ADR-023).

Toutes les dépendances sont lazy-importées : chromadb, openai, numpy, etc.
Installer les extras nécessaires :
  pip install pyworkflow-engine[knowledge]           # ChromaDB
  pip install pyworkflow-engine[knowledge-openai]    # OpenAI embeddings
  pip install pyworkflow-engine[knowledge-parsers]   # PDF, DOCX, HTML
"""
from __future__ import annotations

from pyworkflow_engine.adapters.ai.knowledge.chroma_store import ChromaVectorStore
from pyworkflow_engine.adapters.ai.knowledge.numpy_store import NumpyVectorStore
from pyworkflow_engine.adapters.ai.knowledge.openai_embedder import OpenAIEmbedder
from pyworkflow_engine.adapters.ai.knowledge.recursive_chunker import RecursiveChunker
from pyworkflow_engine.adapters.ai.knowledge.document_parser import LocalDocumentParser

__all__ = [
    "ChromaVectorStore",
    "NumpyVectorStore",
    "OpenAIEmbedder",
    "RecursiveChunker",
    "LocalDocumentParser",
]
