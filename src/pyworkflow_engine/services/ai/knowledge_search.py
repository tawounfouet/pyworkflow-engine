"""
Service de recherche sémantique Knowledge (ADR-023).

Orchestre : requête → embedding → vector search → résultats pertinents.
"""
from __future__ import annotations

from typing import Any

from pyworkflow_engine.ports.ai.embedder import BaseEmbedder
from pyworkflow_engine.ports.ai.vector_store import BaseVectorStore, SearchResult


class KnowledgeSearchService:
    """Recherche sémantique dans le vector store.

    Args:
        embedder: Provider d'embeddings pour la requête.
        vector_store: Backend de stockage vectoriel.
    """

    def __init__(
        self,
        embedder: BaseEmbedder,
        vector_store: BaseVectorStore,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store

    async def search(
        self,
        query: str,
        collection: str,
        limit: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Recherche sémantique : query → embedding → vector search.

        Args:
            query: Requête en langage naturel.
            collection: Nom de la collection vectorielle à interroger.
            limit: Nombre maximal de résultats retournés.
            where: Filtre sur les métadonnées (ex: {"source_id": "uuid"}).

        Returns:
            Liste de SearchResult triée par score décroissant.
        """
        query_embedding = await self._embedder.embed_query(query)
        return await self._vector_store.search(
            collection=collection,
            query_embedding=query_embedding,
            limit=limit,
            where=where,
        )
