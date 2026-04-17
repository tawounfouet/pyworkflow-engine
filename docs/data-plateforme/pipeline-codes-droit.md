# Pipeline codes-droit-to-rag — Architecture bout-en-bout

> **Date :** 16 avril 2026  
> **Statut :** 🚧 En cours (ADR-025)  
> **Fréquence :** Hebdomadaire — dimanche, fenêtre 03h00–05h00 UTC  
> **Owner :** data-team@company.com

---

## Vue d'ensemble

Le pipeline `weekly-codes-droit-to-rag` transforme les codes juridiques français
(XML bruts de `codes.droit.org`) en une base de connaissances RAG interrogeable
via `KnowledgeSearchService`.

```
[codes.droit.org]
      │  GET /payloads/{slug}.xml  (HTTP, retry ×2, fallback SSL)
      ▼
┌─────────────────────────────────┐
│  Job 1 — ingestion-codes-droit  │  03h00 UTC  ≈ 20 min
│  14 codes XML (~50 MB)          │
└──────────────┬──────────────────┘
               │  raw/codes_droit/{slug}/{date}/{slug}.xml
               ▼
┌─────────────────────────────────┐
│  Job 2 — transform-codes-droit  │  03h30 UTC  ≈ 15 min
│  Parsing XML → articles JSON    │
└──────────────┬──────────────────┘
               │  curated/codes_droit/{slug}/{date}/{slug}_articles.json
               ▼
┌─────────────────────────────────┐
│  Job 3 — embed-codes-droit      │  04h00 UTC  ≈ 45 min
│  OpenAI text-embedding-3-large  │
└──────────────┬──────────────────┘
               │  curated/codes_droit/_embeddings/{date}/embeddings.npy
               │                                         embeddings_metadata.json
               ▼
┌─────────────────────────────────┐
│  Job 4 — index-codes-droit      │  04h30 UTC  ≈  5 min
│  KnowledgeSource/Document/Chunk │
└──────────────┬──────────────────┘
               │  workflow.db → ai_knowledge_sources / ai_documents / ai_chunks
               ▼
       [RAG / SemanticSearch]  ✅  05h00 UTC
```

---

## Job 1 — `ingestion-codes-droit`

**Module :** `jobs.ingestion.codes_droit.extract_codes`  
**Schedule :** `0 3 * * 0` (dimanche 03h00 UTC)

### Steps

| Step | Rôle |
|---|---|
| `fetch_codes` | Télécharge les XML via `DroitCodesClient` (stdlib, retry ×2, timeout 600 s) |
| `validate_downloads` | Vérifie qu'au moins 1 code a réussi ; log les échecs partiels sans bloquer |
| `load_to_datalake` | Copie les XML vers `raw/codes_droit/{slug}/{date}/{slug}.xml` |

### Sortie Data Lake

```
data/datalake/raw/codes_droit/
├── cgi/
│   └── 2026-04-13/
│       └── cgi.xml
├── code_civil/
│   └── 2026-04-13/
│       └── code_civil.xml
└── ...  (14 codes)
```

### Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `CODES_DROIT_BASE_URL` | `https://codes.droit.org/payloads` | URL de base |
| `CODES_DROIT_SLUGS` | tous | Codes à télécharger (virgule-séparés) |
| `CODES_DROIT_TIMEOUT` | `60` | Timeout HTTP en secondes |
| `DATALAKE_PATH` | `./data/datalake` | Racine du Data Lake |

---

## Job 2 — `transform-codes-droit`

**Module :** `jobs.transformation.codes_droit.transform.transform_codes`  
**Schedule :** `30 3 * * 0` (dimanche 03h30 UTC)

### Steps

| Step | Rôle | Sortie |
|---|---|---|
| `load_raw_xml` | Découvre les fichiers XML dans `raw/` ; fallback sur la dernière date si `ingest_date="latest"` | `{"files": [...], "file_count": N}` |
| `parse_articles` | Parse chaque XML via `xml.etree.ElementTree` (stdlib) ; filtre `ETAT=VIGUEUR` + contenu non vide | `{"articles_by_slug": {...}, "total_articles": N}` |
| `save_curated` | Écrit les articles JSON dans `curated/` | `{"files_written": N, "paths": [...]}` |

### Parsing XML Légifrance

Le parser (`parser.py`) navigue dans la structure XML suivante :

```xml
<ARTICLE id="LEGIARTI000006302570">
  <META>
    <META_SPEC>
      <META_ARTICLE ETAT="VIGUEUR" NUM="1" DATE_DEBUT="1970-09-14"/>
    </META_SPEC>
  </META>
  <BLOC_TEXTUEL>
    <CONTENU>Texte de l'article...</CONTENU>
  </BLOC_TEXTUEL>
</ARTICLE>
```

### Schéma article JSON

```json
{
  "legiarti_id": "LEGIARTI000006302570",
  "etat": "VIGUEUR",
  "number": "1",
  "title": "Article 1",
  "content": "Texte de l'article...",
  "effective_date": "1970-09-14",
  "slug": "code_civil"
}
```

### Sortie Data Lake

```
data/datalake/curated/codes_droit/
├── cgi/
│   └── 2026-04-13/
│       └── cgi_articles.json          ← liste d'articles VIGUEUR
├── code_civil/
│   └── 2026-04-13/
│       └── code_civil_articles.json
└── ...
```

---

## Job 3 — `embed-codes-droit`

**Module :** `jobs.transformation.codes_droit.embed.embed_codes`  
**Schedule :** `0 4 * * 0` (dimanche 04h00 UTC)

### Steps

| Step | Rôle | Sortie |
|---|---|---|
| `load_articles` | Charge tous les `*_articles.json` depuis `curated/` et construit les textes d'input `"{title}. {content[:1500]}"` | `{"texts": [...], "metadata": [...], "count": N}` |
| `generate_embeddings` | Appelle l'API OpenAI par batches de 100 ; normalisation L2 de chaque vecteur | `{"embeddings_list": [...], "shape": [N, 3072], "model": "..."}` |
| `save_embeddings` | Sauvegarde la matrice `float32` en `.npy` + index JSON | `{"npy_path": "...", "meta_path": "..."}` |

### Normalisation L2

Les vecteurs sont normalisés avant sauvegarde, ce qui permet d'utiliser
le **dot product** comme approximation de la **cosine similarity** :

```python
norm = math.sqrt(sum(x * x for x in vec))
normalized = [x / norm for x in vec]
# → cosine_similarity(a, b) == dot_product(a, b) si ∥a∥ = ∥b∥ = 1
```

### Sortie Data Lake

```
data/datalake/curated/codes_droit/
└── _embeddings/
    └── 2026-04-13/
        ├── embeddings.npy              ← matrice N × 3072 float32
        └── embeddings_metadata.json    ← [{legiarti_id, slug, number, title, ...}]
```

### Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | **Obligatoire** |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | Modèle OpenAI |
| `EMBEDDING_BATCH_SIZE` | `100` | Textes par appel API |
| `EMBEDDING_CONTENT_TRUNC` | `1500` | Troncature contenu (chars) |

---

## Job 4 — `index-codes-droit`

**Module :** `jobs.transformation.codes_droit.index.index_codes`  
**Schedule :** `30 4 * * 0` (dimanche 04h30 UTC)

### Steps

| Step | Rôle | Sortie |
|---|---|---|
| `create_knowledge_source` | Crée ou récupère `codes_droit_{date}` dans `ai_knowledge_sources` ; **idempotent** (skip si INDEXED) | `{"source_id": uuid, "skipped": bool}` |
| `index_articles` | Charge matrice `.npy` + `embeddings_metadata.json` + contenus JSON curated ; insère 1 Document + 1 Chunk par article dans une transaction SQLite | `{"documents_count": N, "chunks_count": N}` |

### Idempotence

```
Run 1 (nouveau) :
  create_knowledge_source → status INDEXING → création
  index_articles          → N documents + N chunks → status INDEXED

Run 2 (même date) :
  create_knowledge_source → status INDEXED détecté → skipped=True
  index_articles          → skipped=True → retour immédiat (0 écritures)

Run 2 avec --force :
  create_knowledge_source → force_reindex=True → status INDEXING → recréation
  index_articles          → N documents + N chunks → status INDEXED
```

### Tables SQLite (`workflow.db`)

**`ai_knowledge_sources`** — 1 ligne par run hebdomadaire

| Colonne | Valeur exemple |
|---|---|
| `id` | `uuid4` |
| `name` | `codes_droit_2026-04-13` |
| `source_type` | `document` |
| `index_status` | `indexed` |
| `chunks_count` | `28 450` |
| `metadata` | `{"date": "2026-04-13", "origin": "codes.droit.org"}` |

**`ai_documents`** — 1 ligne par article juridique

| Colonne | Valeur exemple |
|---|---|
| `id` | `uuid4` |
| `source_id` | FK → `ai_knowledge_sources.id` |
| `title` | `Article 1` |
| `content` | Texte complet de l'article |
| `metadata` | `{"slug": "code_civil", "legiarti_id": "LEGIARTI000006302570"}` |
| `chunk_count` | `1` |

**`ai_chunks`** — 1 ligne par article (1 chunk = 1 article, ADR-025 D5)

| Colonne | Valeur exemple |
|---|---|
| `id` | `uuid4` |
| `document_id` | FK → `ai_documents.id` |
| `content` | Texte complet de l'article |
| `embedding` | `[0.012, -0.043, ..., 0.0071]` (3072 floats L2-normalisés) |
| `chunk_index` | `0` |
| `metadata` | `{"slug": "code_civil", "legiarti_id": "...", "number": "1"}` |

---

## Exécution manuelle

### Chaîne complète

```bash
# Job 1 — ingestion
python -m jobs.ingestion.codes_droit.extract_codes --date 2026-04-13

# Job 2 — transformation
python -m jobs.transformation.codes_droit.transform.transform_codes --date 2026-04-13

# Job 3 — embedding (nécessite OPENAI_API_KEY)
OPENAI_API_KEY=sk-... python -m jobs.transformation.codes_droit.embed.embed_codes --date 2026-04-13

# Job 4 — indexation
python -m jobs.transformation.codes_droit.index.index_codes --date 2026-04-13

# Job 4 — forcer la réindexation
python -m jobs.transformation.codes_droit.index.index_codes --date 2026-04-13 --force
```

### Sous-ensemble (développement)

```bash
# Télécharger uniquement le CGI et le Code civil
CODES_DROIT_SLUGS=cgi,code_civil python -m jobs.ingestion.codes_droit.extract_codes

# Puis transformer / embedder / indexer avec --date latest
python -m jobs.transformation.codes_droit.transform.transform_codes
OPENAI_API_KEY=sk-... python -m jobs.transformation.codes_droit.embed.embed_codes
python -m jobs.transformation.codes_droit.index.index_codes
```

---

## Volumes et coûts estimés (14 codes, ~30 000 articles)

| Étape | Volume | Durée estimée | Coût |
|---|---|---|---|
| Ingestion | 14 fichiers XML, ~50 MB | ≈ 20 min | Gratuit |
| Transformation | ~30 000 articles JSON | ≈ 15 min | Gratuit |
| Embedding | ~30 000 × 1 500 chars | ≈ 45 min | ~$2 / run (`text-embedding-3-large`) |
| Indexation | 30 000 Documents + Chunks | ≈ 5 min | Gratuit |

---

## Voir aussi

- [ADR-025 — Pipeline codes-droit-to-rag](../changelog/2026-04-16_adr_025_data-pipeline-codes-droit.md)
- [Guide RAG juridique](../guides/rag-juridique.md)
- [ADR-023 — Architecture Knowledge & RAG](../changelog/2026-04-12_adr_023_knowledge-rag-architecture.md)
- [ADR-004 — Data Lake local](./04-datalake-local-et-pipelines.md)
