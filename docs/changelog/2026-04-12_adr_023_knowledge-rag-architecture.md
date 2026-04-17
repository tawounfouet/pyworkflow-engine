# ADR-023 — Architecture Knowledge & RAG : ports, adapters et stratégie d'embeddings

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-023                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (hexagonal), ADR-013 (AI engine integration), ADR-018 (models reorg), ADR-020 (framework strategy), ADR-022 (adapter patterns) |
| **Version cible** | v0.12.0                        |

---

## Contexte

### L'existant : modèles Pydantic matures, zéro implémentation

L'ADR-013 a intégré les modèles Knowledge dans pyworkflow-engine. L'ADR-018 les a réorganisés et namespaced. Le résultat actuel :

```
src/pyworkflow_engine/
├── models/ai/
│   ├── knowledge.py          # Chunk, Document, KnowledgeSource (Pydantic)
│   └── types.py              # SourceType, IndexStatus (StrEnum)
├── ports/ai/
│   ├── storage.py            # BaseAIStorage (CRUD KnowledgeSource)
│   └── llm.py                # BaseLLMClient (pas d'embed() encore)
└── adapters/ai/
    ├── llm/                  # 5 providers (OpenAI, Anthropic, Groq, Ollama, Gemini)
    └── storage/memory.py     # InMemoryAIStorage
```

**Trois modèles Pydantic sont en place :**

| Modèle | Table | Champs clés | État |
|--------|-------|-------------|------|
| `KnowledgeSource` | `ai_knowledge_sources` | `name`, `source_type`, `file_path`, `url`, `index_status`, `agent_ids` | ✅ Schéma complet |
| `Document` | `ai_documents` | `source_id` (FK), `title`, `content`, `chunk_count` | ✅ Schéma complet |
| `Chunk` | `ai_chunks` | `document_id` (FK), `content`, `embedding` (JSON), `chunk_index` | ✅ Schéma complet |

**Ce qui manque :** les ports et adapters pour les opérations vectorielles (embeddings, recherche sémantique, ingestion).

### Les archives : deux prototypes incompatibles

L'analyse détaillée de `_archives/` révèle deux systèmes RAG prototypés indépendamment :

#### 1. `_archives/knowledge/` — App Django complète

Un système RAG Django/LangChain/ChromaDB avec services de chunking, ingestion, cache, métriques et web scraping.

**Diagnostic :**
- 🔴 **Couplage Django** — `models.Model`, `FileField`, `Company` FK, Celery tasks
- 🔴 **Lock-in LangChain** — `langchain_openai`, `langchain_chroma`, `langchain_text_splitters` comme dépendances hard (~200+ dépendances transitives)
- 🔴 **Lock-in OpenAI** — `OpenAIEmbeddings(model=..., api_key=...)` en dur
- 🔴 **Modèle de données divergent** — `KnowledgeBase` + `FileSource` (2 niveaux) vs `KnowledgeSource` actuel (1 niveau)
- ✅ **Bonnes idées récupérables** — stratégies de chunking par type de doc, pipeline d'ingestion, convention de nommage multi-tenant, métriques RAG

#### 2. `_archives/generate_embeddings.py` — Script one-shot

Un script CLI générant une matrice numpy `embeddings_openai.npy` (shape 2422×3072) pour les articles du CGI.

**Diagnostic :**
- ✅ Code script propre : batching, normalisation L2, cache `.npy`, argparse
- 🔴 **Hard-lock OpenAI** — `from openai import OpenAI` direct
- 🔴 **Couplé au dataset CGI** — `cgi_database.json`, structure spécifique
- 🔴 **Pas de chunking** — 1 article = 1 embedding (troncature à 1500 chars)
- 🔴 **Matrice monolithique** — pas de lien chunk→document, pas de métadonnées, pas incrémental

### La question posée

> **Comment implémenter la couche Knowledge/RAG (embeddings, stockage vectoriel, chunking, ingestion) dans l'architecture hexagonale existante, en récupérant les bonnes idées des archives sans reprendre leurs défauts ?**

---

## Décision

### Principe directeur

Appliquer le même pattern « Adapter Sandwich » (ADR-022) au domaine Knowledge/RAG :

```
                    Code métier (CLI, Pipeline, Agent)
                                │
                                ▼
                    Ports (ABC purs, 0 dépendance)
                    ├── BaseVectorStore    (NOUVEAU)
                    ├── BaseChunker        (NOUVEAU)
                    ├── BaseEmbedder       (NOUVEAU)
                    └── BaseDocumentParser (NOUVEAU)
                                │
                                ▼
                    Adapters (opt-in, lazy-imported)
                    ├── ChromaVectorStore   (default)
                    ├── NumpyVectorStore    (tests)
                    ├── SmartChunker        (default)
                    └── OpenAIEmbedder / OllamaEmbedder / ...
```

**Zéro import d'un SDK tiers en dehors de son adapter.**

---

## Architecture détaillée

### 1. Nouveaux ports

#### 1.1 `BaseVectorStore` — Stockage et recherche vectorielle

**Fichier :** `src/pyworkflow_engine/ports/ai/vector_store.py`

```python
"""
Port IA — interface abstraite pour le stockage vectoriel.

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

    # ── Sync wrappers (pour CLI et scripts) ───────────────────────

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
```

#### 1.2 `BaseEmbedder` — Génération d'embeddings

**Fichier :** `src/pyworkflow_engine/ports/ai/embedder.py`

```python
"""
Port IA — interface abstraite pour la génération d'embeddings.

Sépare l'embedding du LLM chat : un embedder est un service spécialisé
qui transforme du texte en vecteurs numériques.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    """Résultat d'un appel d'embedding."""

    embeddings: list[list[float]]
    model: str
    total_tokens: int = 0
    dimensions: int = 0


class BaseEmbedder(ABC):
    """Interface pour tout provider d'embeddings.

    Implémentations prévues :
      - OpenAIEmbedder      (text-embedding-3-large/small)
      - OllamaEmbedder      (nomic-embed-text, mxbai-embed-large)
      - SentenceTransformer  (local, GGUF)
    """

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Génère des embeddings pour une liste de textes.

        Args:
            texts: Textes à encoder (déjà chunkés).

        Returns:
            EmbeddingResult avec les vecteurs et métadonnées.
        """

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """Génère l'embedding d'une requête utilisateur (un seul texte).

        Certains providers distinguent l'embedding de documents vs queries.
        """

    def get_dimensions(self) -> int:
        """Retourne la dimensionnalité des vecteurs (ex: 3072, 1536, 768)."""
        return 0  # Override par chaque adapter
```

> **Note de design :** On crée `BaseEmbedder` séparé de `BaseLLMClient` car :
> - Les embeddings ont une interface radicalement différente (batch in → vecteurs out)
> - Certains providers d'embeddings ne font pas de chat (Sentence Transformers, Cohere Embed)
> - Le batching et la normalisation sont spécifiques aux embeddings
> - Cela respecte le SRP : un port = une responsabilité

#### 1.3 `BaseChunker` — Découpage intelligent de texte

**Fichier :** `src/pyworkflow_engine/ports/ai/chunker.py`

```python
"""
Port IA — interface abstraite pour le chunking de documents.

Découpe un texte brut en fragments optimisés pour l'indexation vectorielle.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkResult:
    """Fragment de texte produit par le chunker."""

    content: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseChunker(ABC):
    """Interface pour toute stratégie de chunking.

    Implémentations prévues :
      - RecursiveChunker     (défaut, par taille + overlap)
      - SemanticChunker      (par frontières sémantiques)
      - QAChunker            (préservation Q&A pairs)
      - MarkdownChunker      (header-aware)
    """

    @abstractmethod
    def chunk(
        self,
        text: str,
        *,
        doc_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Découpe un texte en chunks.

        Args:
            text: Texte brut à découper.
            doc_type: Type de document (text, pdf, html, markdown, qa).
            metadata: Métadonnées à propager dans chaque chunk.

        Returns:
            Liste ordonnée de ChunkResult.
        """
```

#### 1.4 `BaseDocumentParser` — Extraction de texte

**Fichier :** `src/pyworkflow_engine/ports/ai/parser.py`

```python
"""
Port IA — interface abstraite pour l'extraction de texte depuis des fichiers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO


@dataclass
class ParseResult:
    """Résultat de l'extraction de texte."""

    content: str
    title: str = ""
    doc_type: str = "text"            # pdf, docx, html, text, markdown
    page_count: int = 0
    char_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseDocumentParser(ABC):
    """Interface pour l'extraction de texte depuis des fichiers.

    Implémentations prévues :
      - LocalDocumentParser   (PyPDF2 + python-docx + BeautifulSoup)
      - WebScraperParser      (HTTP + BS4, pour les sources URL)
    """

    @abstractmethod
    def parse(
        self,
        source: str | Path | BinaryIO,
        *,
        doc_type: str | None = None,
    ) -> ParseResult:
        """Extrait le texte d'un fichier ou d'une URL.

        Args:
            source: Chemin fichier, URL, ou buffer binaire.
            doc_type: Type forcé (auto-détecté si None).

        Returns:
            ParseResult avec le contenu et les métadonnées.
        """

    @abstractmethod
    def supported_types(self) -> list[str]:
        """Liste des types de documents supportés par ce parser."""
```

### 2. Adapters concrets

#### 2.1 `ChromaVectorStore` — Adapter par défaut

**Fichier :** `src/pyworkflow_engine/adapters/ai/knowledge/chroma_store.py`

```python
"""
Adapter ChromaDB pour BaseVectorStore — sans LangChain.

Utilise chromadb directement (API native) avec index HNSW cosine.
Dépendance optionnelle : pip install pyworkflow-engine[knowledge]
"""
import chromadb
from chromadb.config import Settings

from pyworkflow_engine.ports.ai.vector_store import BaseVectorStore, SearchResult


class ChromaVectorStore(BaseVectorStore):

    def __init__(self, persist_directory: str = "./data/chroma") -> None:
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

    def _get_or_create(self, collection: str) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert(self, collection, ids, embeddings, documents, metadatas=None):
        col = self._get_or_create(collection)
        col.upsert(
            ids=ids, embeddings=embeddings,
            documents=documents, metadatas=metadatas,
        )

    async def search(self, collection, query_embedding, limit=5, where=None):
        col = self._get_or_create(collection)
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=limit, where=where,
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

    async def delete(self, collection, ids):
        col = self._get_or_create(collection)
        col.delete(ids=ids)

    async def delete_collection(self, collection):
        self._client.delete_collection(collection)

    async def count(self, collection):
        return self._get_or_create(collection).count()
```

**Choix ChromaDB plutôt que le fichier `.npy` :**

| Critère | Fichier `.npy` | ChromaDB |
|---------|---------------|----------|
| Métadonnées par vecteur | ❌ index entier seulement | ✅ dict par document |
| Mise à jour incrémentale | ❌ rebuild total | ✅ upsert unitaire |
| Filtrage par métadonnées | ❌ chargement complet | ✅ `where={"source_type": "pdf"}` |
| Recherche > 10K vecteurs | ⚠️ O(n) dot product | ✅ O(log n) HNSW |
| Multi-collection (multi-tenant) | ❌ 1 fichier = 1 dataset | ✅ collections isolées |
| Zéro serveur requis | ✅ | ✅ (mode embedded) |
| Taille installée | ~0 Mo (numpy seul) | ~50 Mo |
| Tests unitaires | ✅ rapide | ⚠️ besoin d'un répertoire |

**Décision : ChromaDB pour la production, NumpyVectorStore pour les tests.**

#### 2.2 `NumpyVectorStore` — Adapter pour les tests

**Fichier :** `src/pyworkflow_engine/adapters/ai/knowledge/numpy_store.py`

Implémentation in-memory utilisant `numpy` pour le dot product — aucune dépendance externe au-delà de numpy. Destiné aux tests unitaires et aux POC < 10K documents.

Pattern récupéré du script `_archives/generate_embeddings.py` :
- Normalisation L2 pour cosine similarity via dot product
- Tri par score descendant (`np.argsort(scores)[::-1][:limit]`)

#### 2.3 `OpenAIEmbedder` — Adapter embeddings OpenAI

**Fichier :** `src/pyworkflow_engine/adapters/ai/knowledge/openai_embedder.py`

```python
"""
Adapter OpenAI pour BaseEmbedder.

Gère le batching (récupéré de _archives/generate_embeddings.py),
la normalisation L2, et le retry exponentiel.
"""
from pyworkflow_engine.ports.ai.embedder import BaseEmbedder, EmbeddingResult


class OpenAIEmbedder(BaseEmbedder):

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-large",
        batch_size: int = 100,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._batch_size = batch_size
        # Lazy import — openai est optionnel
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        all_embeddings: list[list[float]] = []
        total_tokens = 0

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            response = self._client.embeddings.create(
                model=self._model, input=batch,
            )
            all_embeddings.extend(e.embedding for e in response.data)
            total_tokens += response.usage.total_tokens

        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self._model,
            total_tokens=total_tokens,
            dimensions=len(all_embeddings[0]) if all_embeddings else 0,
        )

    async def embed_query(self, query: str) -> list[float]:
        result = await self.embed([query])
        return result.embeddings[0]

    def get_dimensions(self) -> int:
        return {"text-embedding-3-large": 3072, "text-embedding-3-small": 1536}.get(
            self._model, 0
        )
```

#### 2.4 `RecursiveChunker` — Adapter chunking par défaut

**Fichier :** `src/pyworkflow_engine/adapters/ai/knowledge/recursive_chunker.py`

Implémentation par défaut utilisant le pattern taille + overlap avec détection de frontières sémantiques (paragraphes, phrases). Récupère les idées du `SmartChunker` de l'archive Django :
- Chunking par type de document (PDF → paragraphes, HTML → sections, Q&A → paires)
- Préservation du contexte via overlap configurable
- Minimum chunk size pour éviter les fragments inutiles

**Sans dépendance LangChain** — utilise uniquement les séparateurs regex natifs Python.

### 3. Pipeline d'ingestion

Le flow d'ingestion (récupéré de `_archives/knowledge/services/ingestion.py`) est réimplémenté comme un **service métier pur** utilisant les ports :

```
KnowledgeSource
       │
       ▼
BaseDocumentParser.parse()           → ParseResult
       │
       ▼
BaseChunker.chunk()                  → list[ChunkResult]
       │
       ▼
BaseEmbedder.embed()                 → EmbeddingResult
       │
       ▼
BaseVectorStore.upsert()             → Chunks indexés
       │
       ▼
BaseAIStorage.save_knowledge_source() → IndexStatus.INDEXED
```

**Fichier :** `src/pyworkflow_engine/services/ai/knowledge_ingestion.py`

```python
"""
Service d'ingestion Knowledge — orchestre le pipeline RAG.

Coordonne les ports (parser, chunker, embedder, vector store, storage)
sans dépendre d'aucune implémentation concrète.
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
    """Pipeline d'ingestion : parse → chunk → embed → store."""

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

        Returns:
            Statistiques d'ingestion (chunks_count, total_tokens, etc.)
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
```

### 4. Service de recherche RAG

```python
"""
Service de recherche sémantique — requête → résultats pertinents.
"""
from __future__ import annotations

from typing import Any

from pyworkflow_engine.ports.ai.embedder import BaseEmbedder
from pyworkflow_engine.ports.ai.vector_store import BaseVectorStore, SearchResult


class KnowledgeSearchService:
    """Recherche sémantique dans le vector store."""

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
        """Recherche sémantique : query → embedding → vector search."""
        query_embedding = await self._embedder.embed_query(query)
        return await self._vector_store.search(
            collection=collection,
            query_embedding=query_embedding,
            limit=limit,
            where=where,
        )
```

### 5. Dépendances optionnelles

**Modification de `pyproject.toml` :**

```toml
[project.optional-dependencies]
# Knowledge / RAG
knowledge = ["chromadb>=0.5"]
knowledge-openai = ["openai>=1.0"]
knowledge-parsers = ["PyPDF2>=3.0", "python-docx>=1.0", "beautifulsoup4>=4.12"]
knowledge-ollama = ["ollama>=0.3"]
```

**Règle : zéro dépendance knowledge dans le core.** Tout est opt-in.

### 6. Structure de fichiers cible

```
src/pyworkflow_engine/
├── ports/ai/
│   ├── __init__.py             # + exports des nouveaux ports
│   ├── vector_store.py         # NOUVEAU — BaseVectorStore, SearchResult
│   ├── embedder.py             # NOUVEAU — BaseEmbedder, EmbeddingResult
│   ├── chunker.py              # NOUVEAU — BaseChunker, ChunkResult
│   ├── parser.py               # NOUVEAU — BaseDocumentParser, ParseResult
│   ├── llm.py                  # (inchangé)
│   ├── storage.py              # (inchangé, déjà les méthodes Knowledge)
│   ├── runtime.py              # (inchangé)
│   ├── tool.py                 # (inchangé)
│   └── skill.py                # (inchangé)
├── adapters/ai/knowledge/
│   ├── __init__.py
│   ├── chroma_store.py         # NOUVEAU — ChromaVectorStore
│   ├── numpy_store.py          # NOUVEAU — NumpyVectorStore (tests)
│   ├── openai_embedder.py      # NOUVEAU — OpenAIEmbedder
│   ├── ollama_embedder.py      # NOUVEAU — OllamaEmbedder
│   ├── recursive_chunker.py    # NOUVEAU — RecursiveChunker
│   ├── document_parser.py      # NOUVEAU — LocalDocumentParser
│   └── web_scraper.py          # NOUVEAU — WebScraperParser
├── services/ai/
│   ├── __init__.py
│   ├── knowledge_ingestion.py  # NOUVEAU — KnowledgeIngestionService
│   └── knowledge_search.py     # NOUVEAU — KnowledgeSearchService
└── models/ai/
    └── knowledge.py            # (inchangé — Chunk, Document, KnowledgeSource)
```

---

## Éléments récupérés des archives

### Ce qui est réutilisé (les idées, réimplémentées from scratch)

| Source archive | Idée récupérée | Destination |
|---|---|---|
| `knowledge/services/chunking.py` | Stratégies par type (Q&A, headers, web) | `adapters/ai/knowledge/recursive_chunker.py` |
| `knowledge/services/ingestion.py` | Flow parse → chunk → embed → store | `services/ai/knowledge_ingestion.py` |
| `knowledge/services/vector_store.py` | Convention nommage `{namespace}_kb_{id}` | `ports/ai/vector_store.py` (docstring) |
| `knowledge/services/cache.py` | Pattern cache + invalidation | Phase 2 (optionnel) |
| `knowledge/services/metrics.py` | Métriques RAG (satisfaction, hit rate) | Phase 2 (optionnel) |
| `generate_embeddings.py` | Batching API, normalisation L2 | `adapters/ai/knowledge/openai_embedder.py` |
| `generate_embeddings.py` | Dot product in-memory | `adapters/ai/knowledge/numpy_store.py` |

### Ce qui est définitivement jeté

| Élément | Raison |
|---|---|
| Modèles Django (`KnowledgeBase`, `FileSource`, `File`, `EmbeddingStatus`) | Remplacés par modèles Pydantic existants |
| Wrapper LangChain-Chroma | ChromaDB natif (sans intermédiaire) |
| `langchain_text_splitters` | Chunking natif Python |
| `langchain_openai.OpenAIEmbeddings` | `OpenAIEmbedder` adapter direct |
| Celery tasks | Pipeline natif pyworkflow ou asyncio |
| Fichier `embeddings_openai.npy` | ChromaDB incrémental remplace le cache monolithique |
| Couplage `Company` FK multi-tenant | Multi-tenant via collection naming |

---

## Comparaison : `.npy` vs ChromaDB

| Critère | `.npy` monolithique | ChromaDB derrière port |
|---------|--------------------|-----------------------|
| Métadonnées par vecteur | ❌ index entier seul | ✅ dict libre par chunk |
| Mise à jour incrémentale | ❌ rebuild total (~$2-5 / regen) | ✅ upsert unitaire |
| Filtrage par attribut | ❌ tout charger en mémoire | ✅ `where={"source_type": "pdf"}` |
| Scale > 100K vecteurs | ⚠️ O(n) brute-force | ✅ O(log n) index HNSW |
| Multi-collection | ❌ 1 fichier = 1 dataset | ✅ collections isolées |
| Testabilité | ✅ numpy seul | ✅ swap → NumpyVectorStore |
| Serveur requis | ✅ non | ✅ non (mode embedded) |
| Taille dépendance | ~0 Mo | ~50 Mo |

**Décision :** ChromaDB pour la production et le développement. Le `NumpyVectorStore` récupère le pattern du script `.npy` comme adapter de test in-memory, sans fichier disque.

---

## Justification : pourquoi `BaseEmbedder` séparé de `BaseLLMClient` ?

L'alternative serait d'ajouter une méthode `embed()` dans `BaseLLMClient`. Nous la rejetons pour 4 raisons :

1. **SRP** — `BaseLLMClient` gère chat/completion/streaming. L'embedding est un service distinct avec une interface radicalement différente (batch in → vecteurs out).

2. **Providers non-LLM** — Sentence Transformers, Cohere Embed, SBERT n'ont pas de chat. Ils ne peuvent pas implémenter `BaseLLMClient`.

3. **Batching spécialisé** — Les embeddings nécessitent un batching API spécifique (100 textes/batch pour OpenAI) et une normalisation L2. Ce n'est pas la responsabilité d'un client chat.

4. **Cohérence ADR-022** — Chaque port = un adapter swappable. `BaseEmbedder` ↔ `OpenAIEmbedder` / `OllamaEmbedder` / `SentenceTransformerEmbedder`, indépendamment du `BaseLLMClient` utilisé pour le chat.

---

## Plan d'implémentation

### Phase 1 — Ports et adapters de base (v0.12.0)

| Tâche | Effort estimé | Priorité |
|---|---|---|
| Créer `ports/ai/vector_store.py` (`BaseVectorStore`, `SearchResult`) | ~80 LOC | P0 |
| Créer `ports/ai/embedder.py` (`BaseEmbedder`, `EmbeddingResult`) | ~60 LOC | P0 |
| Créer `ports/ai/chunker.py` (`BaseChunker`, `ChunkResult`) | ~40 LOC | P0 |
| Créer `ports/ai/parser.py` (`BaseDocumentParser`, `ParseResult`) | ~50 LOC | P0 |
| Implémenter `ChromaVectorStore` | ~120 LOC | P0 |
| Implémenter `NumpyVectorStore` | ~100 LOC | P0 |
| Implémenter `OpenAIEmbedder` | ~80 LOC | P0 |
| Implémenter `RecursiveChunker` | ~200 LOC | P1 |
| Implémenter `LocalDocumentParser` | ~150 LOC | P1 |
| Créer `KnowledgeIngestionService` | ~100 LOC | P1 |
| Créer `KnowledgeSearchService` | ~50 LOC | P1 |
| Ajouter `knowledge` dans `pyproject.toml` optional-deps | ~5 LOC | P0 |
| Exporter les nouveaux ports dans `ports/ai/__init__.py` | ~10 LOC | P0 |
| Tests unitaires (NumpyVectorStore + mocks) | ~300 LOC | P0 |

**Total Phase 1 : ~1 345 LOC, 100% testé avec NumpyVectorStore**

### Phase 2 — Enrichissements (v0.13.0+)

| Tâche | Effort estimé |
|---|---|
| `OllamaEmbedder` (embeddings locaux) | ~80 LOC |
| `WebScraperParser` (sources URL) | ~150 LOC |
| `MarkdownChunker` (header-aware) | ~120 LOC |
| Cache service (optionnel, pattern `_archives/knowledge/services/cache.py`) | ~150 LOC |
| Métriques RAG (hit rate, satisfaction) | ~200 LOC |
| CLI `pyworkflow knowledge ingest/search` | ~200 LOC |
| `QdrantVectorStore` (production distribuée) | ~150 LOC |

### Phase 3 — Intégration Agent ↔ Knowledge (v0.14.0+)

| Tâche | Effort estimé |
|---|---|
| RAG tool pour les agents (`KnowledgeSearchTool` implémentant `BaseTool`) | ~100 LOC |
| Ingestion automatique via `enable_rag=True` dans `AgentConfig` | ~80 LOC |
| Pipeline déclaratif d'ingestion (utilisant `Pipeline` existant) | ~150 LOC |

---

## Diagramme d'architecture final

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Code métier (inchangé)                               │
│  CLI: pyworkflow knowledge ingest/search                                     │
│  Agent: KnowledgeSearchTool (BaseTool)                                       │
│  Pipeline: ingestion déclaratif                                              │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────────┐
         ▼                       ▼                           ▼
┌─────────────────┐  ┌────────────────────┐  ┌──────────────────────────┐
│ KnowledgeSearch │  │ KnowledgeIngestion │  │    BaseAIStorage         │
│    Service      │  │    Service         │  │ (CRUD KnowledgeSource)   │
└────────┬────────┘  └───┬────┬────┬──────┘  └──────────────────────────┘
         │               │    │    │
         ▼               ▼    ▼    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Ports (ABC purs)                                       │
│  BaseVectorStore   BaseEmbedder   BaseChunker   BaseDocumentParser          │
└──────┬──────────────┬─────────────┬──────────────┬──────────────────────────┘
       │              │             │              │
       ▼              ▼             ▼              ▼
┌──────────────┐ ┌──────────┐ ┌───────────┐ ┌────────────────┐
│ ChromaVector │ │ OpenAI   │ │ Recursive │ │ LocalDocument  │
│ Store        │ │ Embedder │ │ Chunker   │ │ Parser         │
├──────────────┤ ├──────────┤ ├───────────┤ ├────────────────┤
│ NumpyVector  │ │ Ollama   │ │ Markdown  │ │ WebScraper     │
│ Store (test) │ │ Embedder │ │ Chunker   │ │ Parser         │
├──────────────┤ ├──────────┤ └───────────┘ └────────────────┘
│ Qdrant (v2)  │ │ Sentence │
│              │ │ Transf.  │
└──────────────┘ └──────────┘
       │              │
       ▼              ▼
┌──────────────┐ ┌──────────┐
│ chromadb     │ │ openai   │     ← Dépendances optionnelles
│ (pip)        │ │ ollama   │       (opt-in via pyproject.toml)
└──────────────┘ └──────────┘
```

---

## Conséquences

### Positif

- **4 nouveaux ports** enrichissent l'architecture hexagonale sans modifier les existants
- **Multi-provider d'embeddings** dès le départ (pas de lock-in OpenAI)
- **Testable à 100%** grâce au `NumpyVectorStore` — aucun ChromaDB requis en CI
- **Incrémental** — chaque port/adapter est livrable indépendamment
- **Rétro-compatible** — zéro breaking change, tout est additionnel

### Négatif

- **4 ports + ~7 adapters** à implémenter (~1 345 LOC phase 1)
- ChromaDB ajoute ~50 Mo en dépendance optionnelle
- Pas de solution distribuée phase 1 (Qdrant en phase 2)

### Risques

- La séparation `BaseEmbedder` / `BaseLLMClient` pourrait être vue comme sur-engineering pour les petits projets — mitigé par la factory pattern
- ChromaDB n'a pas de clustering natif — si le projet dépasse 10M vecteurs, migration vers Qdrant nécessaire (le port abstrait rend cette migration transparente)

---

## Références

- `_archives/knowledge/` — Prototype Django/LangChain (archivé, idées récupérées)
- `_archives/generate_embeddings.py` — Script embeddings numpy (archivé, patterns récupérés)
- ADR-006 — Architecture hexagonale (ports/adapters)
- ADR-013 — Intégration AI engine (modèles Knowledge)
- ADR-018 — Réorganisation modèles et namespacing
- ADR-020 — Stratégie framework (rejet LangChain comme dépendance hard)
- ADR-022 — Patterns d'intégration adapter (Adapter Sandwich)
- [ChromaDB documentation](https://docs.trychroma.com/)
- [OpenAI Embeddings API](https://platform.openai.com/docs/guides/embeddings)
