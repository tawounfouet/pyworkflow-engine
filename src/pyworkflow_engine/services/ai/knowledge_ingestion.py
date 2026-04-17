"""
Service d'ingestion Knowledge — orchestre le pipeline RAG (ADR-023).

Coordonne les ports (parser, chunker, embedder, vector store, storage)
sans dépendre d'aucune implémentation concrète.

Pipeline :
    KnowledgeSource
        → BaseDocumentParser.parse()    → ParseResult
        → BaseChunker.chunk()           → list[ChunkResult]
        → BaseEmbedder.embed()          → EmbeddingResult
        → BaseVectorStore.upsert()      → Chunks indexés
        → BaseAIStorage.save_knowledge_source() → IndexStatus.INDEXED
"""
from __future__ import annotations

from typing import Any

from pyworkflow_engine.models.ai.knowledge import Chunk, Document, KnowledgeSource
from pyworkflow_engine.models.ai.types import IndexStatus
from pyworkflow_engine.ports.ai.chunker import BaseChunker
from pyworkflow_engine.ports.ai.embedder import BaseEmbedder
from pyworkflow_engine.ports.ai.parser import BaseDocumentParser
from pyworkflow_engine.ports.ai.storage import BaseAIStorage
from pyworkflow_engine.ports.ai.vector_store import BaseVectorStore


class KnowledgeIngestionService:
    """Pipeline d'ingestion : parse → chunk → embed → store.

    Args:
        parser: Extracteur de texte depuis fichiers/URLs.
        chunker: Découpeur de texte en fragments.
        embedder: Générateur de vecteurs.
        vector_store: Backend de stockage vectoriel.
        storage: Storage AI pour la mise à jour des métadonnées.
    """

    def __init__(
        self,
        parser: BaseDocumentParser,
        chunker: BaseChunker,
        embedder: BaseEmbedder,
        vector_store: BaseVectorStore,
        storage: BaseAIStorage,
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store
        self._storage = storage

    async def ingest(
        self,
        source: KnowledgeSource,
        *,
        collection: str,
    ) -> dict[str, Any]:
        """Ingère une source complète dans le vector store.

        Args:
            source: Source de connaissance à indexer.
            collection: Nom de la collection vectorielle cible.
                        Convention : {namespace}_kb_{source_id}

        Returns:
            Statistiques d'ingestion :
              - source_id: ID de la source
              - chunks_count: Nombre de chunks créés
              - total_tokens: Total de tokens consommés
              - dimensions: Dimensionnalité des vecteurs
        """
        # 1. Parse
        parse_input = source.file_path or source.url or source.content
        parse_result = self._parser.parse(parse_input, doc_type=source.source_type.value)

        # 2. Chunk
        chunks = self._chunker.chunk(
            parse_result.content,
            doc_type=parse_result.doc_type,
            metadata={"source_id": source.id, "title": parse_result.title},
        )

        if not chunks:
            source.index_status = IndexStatus.INDEXED
            source.chunks_count = 0
            self._storage.save_knowledge_source(source)
            return {
                "source_id": source.id,
                "chunks_count": 0,
                "total_tokens": 0,
                "dimensions": 0,
            }

        # 3. Embed
        texts = [c.content for c in chunks]
        embedding_result = await self._embedder.embed(texts)

        # 4. Store in vector DB
        chunk_ids = [f"{source.id}_chunk_{c.index}" for c in chunks]
        metadatas = [
            {"source_id": source.id, "document_id": source.id, **c.metadata}
            for c in chunks
        ]
        await self._vector_store.upsert(
            collection=collection,
            ids=chunk_ids,
            embeddings=embedding_result.embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        # 5. Update source status
        source.index_status = IndexStatus.INDEXED
        source.chunks_count = len(chunks)
        self._storage.save_knowledge_source(source)

        return {
            "source_id": source.id,
            "chunks_count": len(chunks),
            "total_tokens": embedding_result.total_tokens,
            "dimensions": embedding_result.dimensions,
        }

    async def delete(
        self,
        source: KnowledgeSource,
        *,
        collection: str,
    ) -> None:
        """Supprime tous les vecteurs d'une source du vector store.

        Args:
            source: Source dont les vecteurs sont à supprimer.
            collection: Nom de la collection vectorielle.
        """
        count = await self._vector_store.count(collection)
        if count == 0:
            return

        # Reconstruit les IDs (convention stable : source_id_chunk_N)
        chunk_ids = [f"{source.id}_chunk_{i}" for i in range(source.chunks_count)]
        if chunk_ids:
            await self._vector_store.delete(collection=collection, ids=chunk_ids)

        source.index_status = IndexStatus.PENDING
        source.chunks_count = 0
        self._storage.save_knowledge_source(source)
