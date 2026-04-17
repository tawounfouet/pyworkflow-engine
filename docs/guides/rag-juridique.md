# Guide RAG juridique — Interroger les codes de droit avec `SemanticSearch`

> **Date :** 16 avril 2026  
> **Prérequis :** Pipeline `weekly-codes-droit-to-rag` exécuté au moins une fois  
> **Dépendances :** `openai`, `numpy`

---

## 🎯 Vue d'ensemble

Après l'exécution du pipeline `weekly-codes-droit-to-rag`, les articles juridiques
sont disponibles dans `workflow.db` sous forme de `Chunk` vectorisés (3 072 dimensions,
normalisés L2). Ce guide explique comment les interroger en langage naturel.

```
Votre question
      │  embed via OpenAIEmbedder
      ▼
Vecteur requête (3 072 dims, L2-normalisé)
      │  dot product contre tous les chunks
      ▼
Top-K chunks triés par score (cosine similarity)
      │
      ▼
Articles juridiques pertinents + métadonnées (slug, legiarti_id, number)
```

---

## 📦 Imports nécessaires

```python
import asyncio
import os

from pyworkflow_engine.adapters.ai.knowledge.numpy_store import NumpyVectorStore
from pyworkflow_engine.adapters.ai.knowledge.openai_embedder import OpenAIEmbedder
from pyworkflow_engine.adapters.storage.unified import UnifiedStorage
from pyworkflow_engine.models.ai.knowledge import Chunk
from pyworkflow_engine.services.ai.knowledge_search import KnowledgeSearchService
```

---

## 🔧 Étape 1 — Charger les chunks depuis SQLite

Les chunks sont stockés dans `ai_chunks` de `workflow.db`.
Il faut les charger et les injecter dans un `NumpyVectorStore` (in-memory).

```python
def load_chunks_into_store(
    store: NumpyVectorStore,
    collection: str = "codes_droit",
    source_name: str | None = None,
    db_path: str = "workflow.db",
) -> int:
    """Charge les chunks depuis SQLite dans le NumpyVectorStore.

    Args:
        store:       Instance NumpyVectorStore à alimenter.
        collection:  Nom de la collection (arbitraire, sert d'espace de noms).
        source_name: Filtrer sur une KnowledgeSource spécifique
                     (ex: "codes_droit_2026-04-13"). None = toutes les sources.
        db_path:     Chemin vers workflow.db.

    Returns:
        Nombre de chunks chargés.
    """
    storage = UnifiedStorage(database_path=db_path)

    # Résolution des source_ids à inclure
    if source_name:
        sources = storage.knowledge_sources.filter(name=source_name)
    else:
        sources = storage.knowledge_sources.all()

    source_ids = {s.id for s in sources}
    if not source_ids:
        print(f"Aucune KnowledgeSource trouvée (filtre: {source_name!r})")
        return 0

    # Chargement des documents pour résoudre le source_id des chunks
    # (les chunks référencent document_id, pas source_id directement)
    docs = storage.documents.all()
    doc_ids = {d.id for d in docs if d.source_id in source_ids}

    if not doc_ids:
        print("Aucun document trouvé pour ces sources")
        return 0

    # Chargement et injection des chunks dans le store
    chunks: list[Chunk] = storage.chunks.all()
    relevant = [c for c in chunks if c.document_id in doc_ids and c.embedding]

    if not relevant:
        print("Aucun chunk avec embedding trouvé")
        return 0

    asyncio.run(store.upsert(
        collection=collection,
        ids=[c.id for c in relevant],
        embeddings=[c.embedding for c in relevant],
        documents=[c.content for c in relevant],
        metadatas=[
            {**c.metadata, "document_id": c.document_id}
            for c in relevant
        ],
    ))

    print(f"✅ {len(relevant)} chunks chargés dans la collection '{collection}'")
    return len(relevant)
```

---

## 🔍 Étape 2 — Recherche sémantique

```python
async def search_juridique(
    query: str,
    top_k: int = 5,
    slug_filter: str | None = None,
    db_path: str = "workflow.db",
) -> None:
    """Recherche sémantique dans les codes juridiques.

    Args:
        query:        Question en langage naturel.
        top_k:        Nombre de résultats à retourner.
        slug_filter:  Restreindre à un code spécifique (ex: "cgi", "code_civil").
        db_path:      Chemin vers workflow.db.
    """
    api_key = os.environ["OPENAI_API_KEY"]

    # Initialisation
    embedder = OpenAIEmbedder(api_key=api_key, model="text-embedding-3-large")
    store = NumpyVectorStore()
    service = KnowledgeSearchService(embedder=embedder, vector_store=store)

    # Chargement des chunks
    n = load_chunks_into_store(store, db_path=db_path)
    if n == 0:
        print("Aucun chunk disponible. Exécutez d'abord le pipeline codes-droit-to-rag.")
        return

    # Filtre optionnel par code (slug)
    where = {"slug": slug_filter} if slug_filter else None

    # Recherche
    results = await service.search(
        query=query,
        collection="codes_droit",
        limit=top_k,
        where=where,
    )

    # Affichage
    print(f"\n🔍 Requête : « {query} »")
    print(f"   Filtre slug : {slug_filter or 'tous les codes'}")
    print(f"   {len(results)} résultat(s)\n")
    print("─" * 70)

    for i, result in enumerate(results, 1):
        slug = result.metadata.get("slug", "?")
        number = result.metadata.get("number", "?")
        legiarti_id = result.metadata.get("legiarti_id", "?")
        score_pct = result.score * 100

        print(f"\n#{i}  [{slug}] Article {number}  (score: {score_pct:.1f}%)")
        print(f"     Légifrance : {legiarti_id}")
        print(f"     URL        : https://legifrance.gouv.fr/codes/article_lc/{legiarti_id}")
        print()
        # Afficher les 400 premiers caractères du contenu
        preview = result.content[:400].replace("\n", " ")
        print(f"     {preview}{'...' if len(result.content) > 400 else ''}")
        print("─" * 70)
```

---

## 💡 Exemples d'utilisation

### Recherche générale

```python
asyncio.run(search_juridique(
    query="Quelles sont les conditions pour bénéficier d'une réduction d'impôt ?",
    top_k=5,
))
```

**Résultat attendu :**
```
🔍 Requête : « Quelles sont les conditions pour bénéficier d'une réduction d'impôt ? »
   Filtre slug : tous les codes
   5 résultat(s)

──────────────────────────────────────────────────────────────────────
#1  [cgi] Article 199 terdecies-0 A  (score: 87.3%)
     Légifrance : LEGIARTI000038836947
     URL        : https://legifrance.gouv.fr/codes/article_lc/LEGIARTI000038836947

     Les contribuables domiciliés fiscalement en France peuvent bénéficier
     d'une réduction d'impôt sur le revenu égale à 18 % des versements
     effectués au titre de souscriptions en numéraire au capital initial...
──────────────────────────────────────────────────────────────────────
```

### Recherche dans un code spécifique

```python
# Restreindre au Code civil uniquement
asyncio.run(search_juridique(
    query="responsabilité du fait des choses",
    top_k=3,
    slug_filter="code_civil",
))

# Restreindre au CGI uniquement
asyncio.run(search_juridique(
    query="taux d'imposition des plus-values immobilières",
    top_k=5,
    slug_filter="cgi",
))

# Code du travail : préavis de licenciement
asyncio.run(search_juridique(
    query="durée du préavis de licenciement selon l'ancienneté",
    top_k=3,
    slug_filter="code_du_travail",
))
```

### Recherche sur une session spécifique

```python
# Charger uniquement les chunks de la session du 13 avril
store = NumpyVectorStore()
load_chunks_into_store(
    store,
    source_name="codes_droit_2026-04-13",
    db_path="workflow.db",
)
```

---

## 🔁 Utilisation synchrone (sans asyncio)

Pour les scripts hors boucle d'événements :

```python
from pyworkflow_engine.ports.ai.vector_store import BaseVectorStore

# Appel synchrone via search_sync (wrapper disponible sur BaseVectorStore)
results = store.search_sync(
    collection="codes_droit",
    query_embedding=query_embedding,
    limit=5,
)
```

Ou wrapper manuel :

```python
def search_sync(query: str, top_k: int = 5) -> list:
    return asyncio.run(search_juridique_async(query, top_k))
```

---

## 📊 Interpréter les scores

| Score | Interprétation |
|---|---|
| > 0.85 | Très pertinent — l'article traite directement du sujet |
| 0.70 – 0.85 | Pertinent — l'article aborde le thème, peut nécessiter lecture |
| 0.55 – 0.70 | Partiellement pertinent — thème adjacent |
| < 0.55 | Peu pertinent — bruit sémantique |

> **Note :** Les seuils varient selon la requête. Une requête très précise
> (terme juridique exact) obtient des scores plus élevés qu'une formulation
> en langage courant.

---

## 🗄️ Requêtes SQL directes sur `workflow.db`

Pour des analyses ou diagnostics sans passer par le service :

```sql
-- Nombre de chunks par code juridique
SELECT
    json_extract(metadata, '$.slug') AS slug,
    COUNT(*) AS chunks
FROM ai_chunks
GROUP BY slug
ORDER BY chunks DESC;

-- Sessions disponibles
SELECT name, index_status, chunks_count, last_indexed_at
FROM ai_knowledge_sources
WHERE name LIKE 'codes_droit_%'
ORDER BY created_at DESC;

-- Rechercher un article par son identifiant Légifrance
SELECT d.title, d.content
FROM ai_documents d
WHERE json_extract(d.metadata, '$.legiarti_id') = 'LEGIARTI000006302570';

-- Articles d'un code spécifique
SELECT d.title, d.content
FROM ai_documents d
WHERE json_extract(d.metadata, '$.slug') = 'code_civil'
ORDER BY d.title;
```

---

## ❓ FAQ

**Q : Le pipeline doit-il être re-exécuté à chaque recherche ?**  
Non. Les chunks sont persistés dans `workflow.db`. Seul `load_chunks_into_store()`
doit être appelé en début de session pour peupler le `NumpyVectorStore` in-memory.

**Q : Peut-on utiliser un modèle d'embedding différent pour la recherche ?**  
Non. Le modèle de recherche doit être le même que celui utilisé pour l'indexation
(`text-embedding-3-large` par défaut). Un modèle différent produirait des vecteurs
incompatibles (espaces vectoriels distincts).

**Q : Pourquoi `NumpyVectorStore` et pas ChromaDB ?**  
`NumpyVectorStore` est suffisant pour ~30 000 chunks (chargement mémoire ≈ 350 Mo,
recherche < 100 ms). Pour un usage en production avec des milliers de requêtes
concurrentes, envisager [`ChromaVectorStore`](../../src/pyworkflow_engine/adapters/ai/knowledge/chroma_store.py).

**Q : Comment ajouter un nouveau code juridique au pipeline ?**  
Ajouter le slug dans `CODES_DROIT_SLUGS` (ou laisser vide pour télécharger tous les codes
disponibles sur `codes.droit.org`). Le pipeline suivant l'inclura automatiquement.

**Q : Comment forcer une réindexation complète ?**  
```bash
python -m jobs.transformation.codes_droit.index.index_codes --date 2026-04-13 --force
```

---

## Voir aussi

- [Architecture pipeline codes-droit-to-rag](../data-plateforme/pipeline-codes-droit.md)
- [ADR-025 — Pipeline juridique bout-en-bout](../changelog/2026-04-16_adr_025_data-pipeline-codes-droit.md)
- [ADR-023 — Architecture Knowledge & RAG](../changelog/2026-04-12_adr_023_knowledge-rag-architecture.md)
- [`NumpyVectorStore`](../../src/pyworkflow_engine/adapters/ai/knowledge/numpy_store.py)
- [`OpenAIEmbedder`](../../src/pyworkflow_engine/adapters/ai/knowledge/openai_embedder.py)
- [`KnowledgeSearchService`](../../src/pyworkflow_engine/services/ai/knowledge_search.py)
