# ADR-025 — Pipeline de données juridiques : ingestion → transformation → embedding → indexation RAG

| Champ | Valeur |
|---|---|
| **ID** | ADR-025 |
| **Date** | 16 avril 2026 |
| **Statut** | ✅ Implémentée — code + docs complets, tests manquants (backlog) |
| **Auteur** | équipe pyworkflow-engine |
| **Décisions liées** | ADR-005 (`@step`/`@job`), ADR-006 (hexagonal), ADR-023 (Knowledge & RAG), ADR-024 (scheduling) |
| **Version cible** | v0.5.0 |
| **Implémenté le** | 16 avril 2026 |

---

## Contexte

### Avant cette ADR

Le job `ingestion-codes-droit` (Job 1) télécharge les XML juridiques français depuis
`codes.droit.org` et les persiste dans le Data Lake (`raw/{slug}/{date}/{slug}.xml`).

Il s'arrête là. Les XML bruts ne sont **ni parsés**, **ni vectorisés**, **ni indexés** —
le moteur RAG (`KnowledgeSource / Document / Chunk`) défini dans ADR-023 est en place mais
aucun pipeline ne l'alimente.

Les archives `_archives/pytaxes-engine/` contiennent la logique historique :

| Fichier archive | Logique extraite |
|---|---|
| `tax_engine/models/tax_article.py` | Dataclasses `Article / Section / Chapter / Title / Book` |
| `generate_embeddings.py` | Batch OpenAI Embeddings, normalisation L2, sauvegarde `.npy` |
| `data/embeddings_openai.npy` | Matrice `2422 × 3072 float32` (CGI uniquement) |
| `data/openai_embeddings_clusters_cgi.json` | Clusters sémantiques calculés en notebook |

### Problème à résoudre

> Comment transformer les codes XML bruts en une base de connaissances
> RAG-ready (chunks vectorisés, interrogeables via `SemanticSearch`) en
> réutilisant l'architecture `@step/@job` et les models persistables existants ?

---

## Décision

### Chaîne de 4 jobs séquentiels

```
[codes.droit.org]
      │  HTTP XML (stdlib)
      ▼
Job 1 — ingestion-codes-droit          ✅ existant
      │  raw/{slug}/{date}/{slug}.xml
      ▼
Job 2 — transform-codes-droit          ✅ implémenté
      │  curated/{slug}/{date}/{slug}_articles.json
      ▼
Job 3 — embed-codes-droit              ✅ implémenté
      │  _embeddings/{date}/embeddings.npy + metadata.json
      ▼
Job 4 — index-codes-droit              ✅ implémenté
      │  ai_knowledge_sources / ai_documents / ai_chunks (SQLite)
      ▼
[RAG / SemanticSearch] 🎯
```

---

## Structure de fichiers

```
jobs/
├── shared/
│   ├── datalake.py                     # DataLake.from_env(), root helpers
│   └── logging.py                      # configure_platform_logging()
│
├── ingestion/
│   └── codes_droit/                    ✅ JOB 1
│       ├── config.yaml
│       ├── client.py                   # DroitCodesClient (stdlib)
│       └── extract_codes.py            # @job fetch → validate → load
│
└── transformation/
    └── codes_droit/
        ├── transform/                  ✅ JOB 2
        │   ├── parser.py               # _extract_articles(), _text_content()
        │   └── transform_codes.py      # @job load_raw → parse → save_curated
        │
        ├── embed/                      ✅ JOB 3
        │   ├── config.py               # DEFAULT_MODEL, BATCH_SIZE, TRUNC
        │   └── embed_codes.py          # @job load_articles → generate → save
        │
        └── index/                      ✅ JOB 4
            └── index_codes.py          # @job create_source → index_articles
```

### Data Lake partitionné

```
data/datalake/
├── raw/
│   └── codes_droit/{slug}/{YYYY-MM-DD}/{slug}.xml              ← Job 1
│
└── curated/
    └── codes_droit/
        └── {slug}/{YYYY-MM-DD}/
            ├── {slug}_articles.json                            ← Job 2 (articles JSON structurés)
            ├── {slug}_embeddings.npy                           ← Job 3 (N × 3072 float32)
            └── {slug}_embeddings_metadata.json                 ← Job 3 (légiarti_id, slug, number)
```

> **v2 — partitionnement par slug** : les embeddings sont colocalisés avec les articles (un `.npy` par code),
> ce qui supprime l'ancien dossier monolithique `_embeddings/` (supprimé le 16 avril 2026).

### Base de données (SQLite `workflow.db`)

```
ai_knowledge_sources    ← Job 4 : 1 source par run (codes_droit_{date})
ai_documents            ← Job 4 : 1 document par article juridique
ai_chunks               ← Job 4 : 1 chunk par article (content + embedding vector)
```

---

## Détail des jobs

### Job 2 — `transform-codes-droit`

**Module :** `jobs.transformation.codes_droit.transform.transform_codes`

**Responsabilités :**
- Charger les XML bruts depuis `raw/` (fallback sur la dernière date si `ingest_date` absent)
- Parser le XML Légifrance via `xml.etree.ElementTree` (stdlib)
- Filtrer les articles `etat == "VIGUEUR"` avec contenu non vide
- Sauvegarder le JSON structuré dans `curated/`

**Pipeline :**

```
load_raw_xml
    ↓   {"files": [...], "file_count": N}
parse_articles
    ↓   {"articles_by_slug": {...}, "total_articles": N}
save_curated
    →   {"files_written": N, "paths": [...]}
```

**Champs extraits par article :**

| Champ | Source XML | Description |
|---|---|---|
| `legiarti_id` | `ARTICLE[@id]` | Identifiant Légifrance |
| `etat` | `META_ARTICLE[@ETAT]` | `VIGUEUR` \| `ABROGE` |
| `number` | `META_ARTICLE[@NUM]` | Numéro d'article (ex : `4 A`) |
| `title` | Construit | `Article {number}` |
| `content` | `BLOC_TEXTUEL/CONTENU` | Texte brut concatené |
| `effective_date` | `META_ARTICLE[@DATE_DEBUT]` | Date d'entrée en vigueur |
| `slug` | Contexte | Identifiant du code source |

---

### Job 3 — `embed-codes-droit`

**Module :** `jobs.transformation.codes_droit.embed.embed_codes`

**Responsabilités :**
- Charger les articles JSON depuis `curated/`
- Construire le texte d'input : `"{title}. {content[:1500]}"`
- Appeler l'API OpenAI Embeddings par batches de 100
- Normaliser les vecteurs (L2) pour que `cosine_similarity == dot_product`
- Sauvegarder la matrice `.npy` + le fichier de métadonnées JSON

**Pipeline :**

```
load_articles
    ↓   {"texts": [...], "metadata": [...], "count": N}
generate_embeddings          timeout=1800s
    ↓   {"embeddings_list": [...], "shape": [N, 3072], "model": "..."}
save_embeddings
    →   {"npy_path": "...", "meta_path": "..."}
```

**Paramètres configurables (env) :**

| Variable | Défaut | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Obligatoire |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | Modèle OpenAI |
| `EMBEDDING_BATCH_SIZE` | `100` | Taille de batch API |
| `EMBEDDING_CONTENT_TRUNC` | `1500` | Troncature texte (chars) |

**Note :** la matrice est transportée entre steps via `embeddings_list` (liste Python
sérialisable JSON). Elle est reconvertie en `np.ndarray` dans `save_embeddings`.

---

### Job 4 — `index-codes-droit`

**Module :** `jobs.transformation.codes_droit.index.index_codes`

**Responsabilités :**
- Créer une `KnowledgeSource` (ADR-023) pour la session d'ingestion
- Créer un `Document` + un `Chunk` (avec embedding) par article
- Alimenter les tables `ai_*` de `workflow.db`

**Pipeline :**

```
create_knowledge_source
    ↓   {"source_id": "uuid", "source": {...}}
index_articles
    →   {"documents_count": N, "chunks_count": N, ...}
```

**Relation avec les models existants :**

```
KnowledgeSource (source_type=DOCUMENT, index_status=PENDING → INDEXING → INDEXED)
    └── Document (1 par article, content, metadata: {slug, legiarti_id})
            └── Chunk (1 par article, content, embedding=[...float32...], chunk_index=0)
```

---

## Décisions techniques

### D1 — Un job par couche (pas un méga-job)

**Retenu :** 4 jobs indépendants (`@job`) chaînés manuellement ou via manifest  
**Rejeté :** un seul job monolithique `ingest-transform-embed-index`

**Justification :**
- Ré-exécution partielle possible (ex : régénérer les embeddings sans re-télécharger)
- Chaque job est testable et observable indépendamment via `WorkflowEngine`
- Correspond aux couches `raw` / `curated` / `semantic` du Data Lake
- Compatible avec le scheduling ADR-024 (fréquences différentes possibles)

### D2 — Transport des embeddings via liste Python entre steps

**Retenu :** `embeddings_list: list[list[float]]` dans le contexte du job  
**Rejeté :** écriture intermédiaire `.npy` entre `generate_embeddings` et `save_embeddings`

**Justification :**
- Cohérence avec le pattern `@step` qui échange des dictionnaires JSON-sérialisables
- Le `.npy` final est écrit une seule fois dans `save_embeddings`
- La taille en mémoire est acceptable (14 codes × ~2 000 articles × 3 072 dims ≈ 350 Mo max)

### D3 — Stdlib XML (ElementTree) pour le parsing Légifrance

**Retenu :** `xml.etree.ElementTree` (stdlib)  
**Rejeté :** `lxml`, `BeautifulSoup`, parsers tiers

**Justification :**
- Cohérence avec le principe « stdlib d'abord » du projet (cf. `client.py`)
- Les XML Légifrance sont bien formés et ne nécessitent pas de tolérance HTML
- Zéro dépendance externe supplémentaire

### D4 — Fallback date dans `load_raw_xml` / `load_articles`

**Retenu :** si `ingest_date` absent → utiliser la dernière date disponible (tri lexicographique `YYYY-MM-DD`)  
**Rejeté :** erreur si la date exacte est absente

**Justification :**
- Permet de chaîner les jobs sans passer explicitement `ingest_date` à chaque fois
- Robuste aux exécutions manuelles (développement, debug)

### D5 — 1 Chunk par article (pas de chunking par paragraphe)

**Retenu :** un seul `Chunk` par article juridique  
**Rejeté :** découpage en sous-chunks de 512 tokens

**Justification :**
- Les articles juridiques ont une taille moyenne de 300-800 tokens (compatibles avec le modèle)
- La granularité article est la bonne unité sémantique pour la recherche juridique
- Simplifie l'indexation et la reconstruction du contexte RAG
- Évolutif : un futur job `rechunk-codes-droit` pourrait subdiviser si nécessaire

---

## Intégration avec le scheduling (ADR-024)

Entrées ajoutées dans `jobs/manifest.yaml` ✅ :

```yaml
- name: transform-codes-droit
  module: jobs.transformation.codes_droit.transform.transform_codes
  attr: transform_codes_droit
  schedule: "30 3 * * 0"      # dimanche 03h30 UTC (après ingestion à 03h00)
  owner: data-team@company.com
  tags: [transformation, codes-droit, xml, parsing]
  depends_on: [ingestion-codes-droit]

- name: embed-codes-droit
  module: jobs.transformation.codes_droit.embed.embed_codes
  attr: embed_codes_droit
  schedule: "0 4 * * 0"       # dimanche 04h00 UTC
  owner: data-team@company.com
  tags: [embedding, openai, codes-droit, rag]
  depends_on: [transform-codes-droit]

- name: index-codes-droit
  module: jobs.transformation.codes_droit.index.index_codes
  attr: index_codes_droit
  schedule: "30 4 * * 0"      # dimanche 04h30 UTC
  owner: data-team@company.com
  tags: [indexation, rag, knowledge-base, codes-droit]
  depends_on: [embed-codes-droit]
```

**Fenêtre hebdomadaire dimanche :**

```
03h00  ingestion-codes-droit    (≈ 20 min — 14 fichiers XML, ~50 MB)
03h30  transform-codes-droit    (≈ 15 min — parsing + JSON)
04h00  embed-codes-droit        (≈ 45 min — API OpenAI, ~30K articles)
04h30  index-codes-droit        (≈ 5 min  — insertion SQLite)
05h00  ✅ RAG opérationnel
```

---

## Fichiers à créer

| Fichier | Statut | Description |
|---|---|---|
| `jobs/transformation/__init__.py` | ✅ Existait déjà | Package Python |
| `jobs/transformation/codes_droit/__init__.py` | ✅ Créé | Package Python |
| `jobs/transformation/codes_droit/transform/__init__.py` | ✅ Créé | Package Python |
| `jobs/transformation/codes_droit/transform/parser.py` | ✅ Créé | `_extract_articles()`, `_text_content()` |
| `jobs/transformation/codes_droit/transform/transform_codes.py` | ✅ Créé | Job 2 |
| `jobs/transformation/codes_droit/embed/__init__.py` | ✅ Créé | Package Python |
| `jobs/transformation/codes_droit/embed/config.py` | ✅ Créé | Constantes embedding |
| `jobs/transformation/codes_droit/embed/embed_codes.py` | ✅ Créé | Job 3 |
| `jobs/transformation/codes_droit/index/__init__.py` | ✅ Créé | Package Python |
| `jobs/transformation/codes_droit/index/index_codes.py` | ✅ Créé | Job 4 |
| `jobs/manifest.yaml` | ✅ Mis à jour | 3 nouvelles entrées + `depends_on` (Jobs 2, 3, 4) |
| `docs/changelog/README.md` | ✅ Mis à jour | Statut ADR-025 → 🚧 En cours |

---

## Impact sur la documentation

| Document | Action | Statut |
|---|---|---|
| `docs/data-plateforme/pipeline-codes-droit.md` | Créer — architecture bout-en-bout (flux de données, schémas, partitions) | ✅ Créé |
| `docs/guides/rag-juridique.md` | Créer — guide d'utilisation du RAG (requêtes SemanticSearch, exemples) | ✅ Créé |
| `docs/changelog/README.md` | Mettre à jour — entrée ADR-025 | ✅ Fait |
| `docs/changelog/2026-04-16_adr_025_*.md` | Ce document | ✅ Mis à jour |

---

## Ce qui reste à faire

### 🔴 Obligatoire avant de passer le statut à ✅ Implémentée

| Tâche | Fichier(s) cible(s) | Priorité |
|---|---|---|
| **Tests unitaires `parser.py`** — cas XML valide, article ABROGE filtré, contenu vide filtré, XML malformé | `tests/transformation/codes_droit/test_parser.py` | Haute |
| **Tests unitaires Job 2** — mock DataLake, vérification JSON curated | `tests/transformation/codes_droit/test_transform_codes.py` | Haute |
| **Tests Job 3** — mock client OpenAI (éviter appels API réels en CI), vérification normalisation L2, écriture `.npy` | `tests/transformation/codes_droit/test_embed_codes.py` | Haute |
| **Tests Job 4** — vérification création KnowledgeSource / Document / Chunk avec `UnifiedStorage(:memory:)` | `tests/transformation/codes_droit/test_index_codes.py` | Haute |
| **Validation run complet en staging** — exécuter la chaîne complète sur un sous-ensemble (ex : CGI uniquement) avant le premier run de production | Manuel / script CI | Haute |

### 🟡 Recommandé (non bloquant pour la mise en production)

| Tâche | Description | Effort | Statut |
|---|---|---|---|
| **Pipeline `weekly-codes-droit-to-rag`** | Entrée `pipelines:` dans `manifest.yaml` regroupant les 4 jobs, avec `depends_on` et commentaires horaires | Faible | ✅ Fait |
| **Documentation `pipeline-codes-droit.md`** | Schéma bout-en-bout, partitions Data Lake, structure SQLite, volumes/coûts, exécution manuelle | Moyen | ✅ Créé |
| **Guide `rag-juridique.md`** | `load_chunks_into_store()`, `search_juridique()`, exemples par code, requêtes SQL directes, FAQ | Moyen | ✅ Créé |
| **Idempotence Job 4** — skip si `codes_droit_{date}` déjà INDEXED ; flag `--force` pour forcer | `index_codes.py` → `create_knowledge_source` + `index_articles` + entrypoint `--force` | Moyen | ✅ Implémenté (v1.1.0) |

### 🟢 Évolutions futures (backlog)

| Évolution | Effort | Valeur |
|---|---|---|
| **Chunking par paragraphe** — subdiviser les longs articles en chunks de 512 tokens | Moyen | Haute pour les articles très longs (Code du travail) |
| **Détection de changements** — ne ré-embedder que les articles modifiés (diff XML) | Élevé | Haute — économie API OpenAI (~$2/run complet) |
| **Support multi-modèles** — `text-embedding-3-small` pour les codes non fiscaux | Faible | Moyenne — équilibre coût/qualité |
| **Clusters sémantiques** — migrer `openai_embeddings_clusters_cgi.json` en job `cluster-codes-droit` | Moyen | Moyenne — navigation thématique |
| **Incremental indexing** — ne pas recréer les chunks déjà en base | Moyen | Haute — idempotence des runs hebdomadaires |
| **FastAPI endpoint** — `GET /api/search?q=...` branché sur `SemanticSearch` + chunks | Élevé | Très haute — première interface utilisateur RAG |
