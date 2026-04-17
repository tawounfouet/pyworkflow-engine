"""
Adapter ChromaDB pour BaseVectorStore (ADR-023) — sans LangChain.

Utilise chromadb directement (API native) avec index HNSW cosine.
Dépendance optionnelle : pip install pyworkflow-engine[knowledge]
"""
from __future__ import annotations

from typing import Any

from pyworkflow_engine.ports.ai.vector_store import BaseVectorStore, SearchResult


class ChromaVectorStore(BaseVectorStore):
    """Stockage vectoriel persistant via ChromaDB (embedded, HNSW cosine).

    Args:
        persist_directory: Répertoire de persistance ChromaDB.
    """

    def __init__(self, persist_directory: str = "./data/chroma") -> None:
        # Lazy import — chromadb est optionnel
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise ImportError(
                "chromadb est requis pour ChromaVectorStore.\n"
                "Installez-le avec : pip install pyworkflow-engine[knowledge]"
            ) from exc

        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

    def _get_or_create(self, collection: str) -> Any:
        return self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        col = self._get_or_create(collection)
        col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        limit: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        col = self._get_or_create(collection)
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return [
            SearchResult(
                chunk_id=results["ids"][0][i],
                document_id=(results["metadatas"][0][i] or {}).get("document_id", ""),
                content=results["documents"][0][i] or "",
                score=1.0 - results["distances"][0][i],
                metadata=results["metadatas"][0][i] or {},
            )
            for i in range(len(results["ids"][0]))
        ]

    async def delete(self, collection: str, ids: list[str]) -> None:
        col = self._get_or_create(collection)
        col.delete(ids=ids)

    async def delete_collection(self, collection: str) -> None:
        self._client.delete_collection(collection)

    async def count(self, collection: str) -> int:
        return self._get_or_create(collection).count()
