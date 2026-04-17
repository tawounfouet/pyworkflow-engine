"""
Adapter NumpyVectorStore pour BaseVectorStore (ADR-023).

Implémentation in-memory utilisant numpy pour le dot product.
Destiné aux tests unitaires et aux POC < 10K documents.

Pattern récupéré de _archives/generate_embeddings.py :
  - Normalisation L2 pour cosine similarity via dot product
  - Tri par score descendant (np.argsort(scores)[::-1][:limit])

Aucune dépendance externe au-delà de numpy.
"""
from __future__ import annotations

from typing import Any

from pyworkflow_engine.ports.ai.vector_store import BaseVectorStore, SearchResult


class NumpyVectorStore(BaseVectorStore):
    """Stockage vectoriel in-memory via numpy — pour tests et POC.

    Utilise la normalisation L2 + dot product pour la cosine similarity,
    identique au script _archives/generate_embeddings.py.
    """

    def __init__(self) -> None:
        # {collection: {"ids": [...], "embeddings": [...], "documents": [...], "metadatas": [...]}}
        self._store: dict[str, dict[str, list[Any]]] = {}

    def _get_collection(self, collection: str) -> dict[str, list[Any]]:
        if collection not in self._store:
            self._store[collection] = {
                "ids": [],
                "embeddings": [],
                "documents": [],
                "metadatas": [],
            }
        return self._store[collection]

    async def upsert(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        col = self._get_collection(collection)
        _metadatas = metadatas or [{} for _ in ids]
        for i, doc_id in enumerate(ids):
            if doc_id in col["ids"]:
                idx = col["ids"].index(doc_id)
                col["embeddings"][idx] = embeddings[i]
                col["documents"][idx] = documents[i]
                col["metadatas"][idx] = _metadatas[i]
            else:
                col["ids"].append(doc_id)
                col["embeddings"].append(embeddings[i])
                col["documents"].append(documents[i])
                col["metadatas"].append(_metadatas[i])

    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        limit: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        try:
            import numpy as np
        except ImportError as exc:
            raise ImportError(
                "numpy est requis pour NumpyVectorStore.\n"
                "Installez-le avec : pip install numpy"
            ) from exc

        col = self._get_collection(collection)
        if not col["ids"]:
            return []

        # Filtrage par métadonnées (where)
        indices = list(range(len(col["ids"])))
        if where:
            indices = [
                i for i in indices
                if all(
                    col["metadatas"][i].get(k) == v
                    for k, v in where.items()
                )
            ]
        if not indices:
            return []

        embeddings = np.array([col["embeddings"][i] for i in indices], dtype=np.float32)
        query = np.array(query_embedding, dtype=np.float32)

        # Normalisation L2 pour cosine similarity via dot product
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        embeddings_norm = embeddings / norms

        query_norm = query / (np.linalg.norm(query) or 1)
        scores = embeddings_norm @ query_norm

        top_k = min(limit, len(indices))
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [
            SearchResult(
                chunk_id=col["ids"][indices[j]],
                document_id=col["metadatas"][indices[j]].get("document_id", ""),
                content=col["documents"][indices[j]],
                score=float(scores[j]),
                metadata=col["metadatas"][indices[j]],
            )
            for j in top_indices
        ]

    async def delete(self, collection: str, ids: list[str]) -> None:
        col = self._get_collection(collection)
        ids_set = set(ids)
        keep = [i for i, doc_id in enumerate(col["ids"]) if doc_id not in ids_set]
        col["ids"] = [col["ids"][i] for i in keep]
        col["embeddings"] = [col["embeddings"][i] for i in keep]
        col["documents"] = [col["documents"][i] for i in keep]
        col["metadatas"] = [col["metadatas"][i] for i in keep]

    async def delete_collection(self, collection: str) -> None:
        self._store.pop(collection, None)

    async def count(self, collection: str) -> int:
        return len(self._get_collection(collection)["ids"])
