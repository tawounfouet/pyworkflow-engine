"""
Port IA — interface abstraite pour le stockage vectoriel (ADR-023).

Gère l'indexation et la recherche sémantique de chunks.
Implémentations : ChromaDB (default), Numpy (tests), Qdrant (scale).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """Résultat d'une recherche sémantique — framework-agnostic."""

    chunk_id: str
    document_id: str
    content: str
    score: float                          # 0.0–1.0, cosine similarity
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseVectorStore(ABC):
    """Interface pour tout backend de stockage vectoriel.

    Convention de nommage des collections : {namespace}_kb_{source_id}
    Exemple : "acme_kb_src-uuid-123"

    Implémentations prévues :
      - ChromaVectorStore   (default, embedded, HNSW index)
      - NumpyVectorStore    (tests unitaires, in-memory)
      - QdrantVectorStore   (production distribuée, optionnel)
    """

    @abstractmethod
    async def upsert(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Insère ou met à jour des vecteurs dans une collection."""

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        limit: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Recherche les chunks les plus proches du vecteur query."""

    @abstractmethod
    async def delete(self, collection: str, ids: list[str]) -> None:
        """Supprime des vecteurs par ID."""

    @abstractmethod
    async def delete_collection(self, collection: str) -> None:
        """Supprime une collection entière."""

    @abstractmethod
    async def count(self, collection: str) -> int:
        """Nombre de vecteurs dans une collection."""

    # ── Sync wrappers (pour CLI et scripts) ───────────────────────────

    def upsert_sync(self, *args: Any, **kwargs: Any) -> None:
        """Wrapper synchrone — délègue à upsert() via asyncio."""
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.upsert(*args, **kwargs))

    def search_sync(self, *args: Any, **kwargs: Any) -> list[SearchResult]:
        """Wrapper synchrone — délègue à search() via asyncio."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self.search(*args, **kwargs)
        )
