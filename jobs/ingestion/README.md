# Ingestion — Couche 1 (Bronze)

Extraction brute des sources externes → Data Lake.

## Principe

- **1 dossier par source** (Stripe, books.toscrape, REST Countries…)
- Chaque dossier contient :
  - `client.py` — Connecteur spécifique à la source
  - `extract_*.py` — Job(s) d'extraction (1 par entité), API décorateurs `@step`/`@job`
  - `config.yaml` — Paramètres de la source (endpoints, champs, env vars)
- Les données sont écrites **brutes** (JSON) dans `data/datalake/raw/`

---

## Sources disponibles

### `books_toscrape` — HTTP scraping

> Site de démonstration books.toscrape.com (aucun accès refusé).
> Pipeline impératif `Job(steps=[…])`.

| Variable | Défaut | Description |
|---|---|---|
| `BOOKS_BASE_URL` | `http://books.toscrape.com/` | URL de base |
| `BOOKS_MAX_PAGES` | `0` (illimité) | Nombre max de pages par catégorie |
| `BOOKS_CATEGORIES` | *(toutes)* | Catégories filtrées, séparées par virgule |
| `DATALAKE_PATH` | `./data/datalake` | Répertoire racine du Data Lake |

**Output :** `data/datalake/raw/books_toscrape/books/{date}/data.json`

```bash
# Lancement simple (date du jour en partition)
python -m jobs.ingestion.books_toscrape.extract_books

# Limiter à 2 pages par catégorie
BOOKS_MAX_PAGES=2 python -m jobs.ingestion.books_toscrape.extract_books

# Filtrer sur une seule catégorie
BOOKS_CATEGORIES=mystery python -m jobs.ingestion.books_toscrape.extract_books

# Data Lake alternatif
DATALAKE_PATH=/tmp/datalake python -m jobs.ingestion.books_toscrape.extract_books
```

---

### `restcountries` — REST Countries API v3.1

> API publique — 250+ pays (codes ISO, noms EN/FR/natif, géographie,
> devises, langues, drapeaux, fuseaux horaires…).
> Pipeline déclaratif `@step`/`@job` — retry x3 sur le fetch, injection
> automatique des paramètres entre steps.

| Variable | Défaut | Description |
|---|---|---|
| `RESTCOUNTRIES_BASE_URL` | `https://restcountries.com/v3.1` | URL de base de l'API |
| `RESTCOUNTRIES_INDEPENDENT_ONLY` | `false` | `true` = pays indépendants seulement |
| `RESTCOUNTRIES_TIMEOUT` | `30` | Timeout HTTP en secondes |
| `DATALAKE_PATH` | `./data/datalake` | Répertoire racine du Data Lake |

**Output :** `data/datalake/raw/restcountries/countries/{date}/data.json`

```bash
# Lancement simple (tous les pays, date du jour)
python -m jobs.ingestion.restcountries.extract_countries

# Pays independants seulement
RESTCOUNTRIES_INDEPENDENT_ONLY=true python -m jobs.ingestion.restcountries.extract_countries

# Timeout reduit + Data Lake alternatif
RESTCOUNTRIES_TIMEOUT=10 DATALAKE_PATH=/tmp/datalake \
  python -m jobs.ingestion.restcountries.extract_countries

# API miroir ou proxy local
RESTCOUNTRIES_BASE_URL=http://localhost:8080/v3.1 \
  python -m jobs.ingestion.restcountries.extract_countries
```

---

## Ajouter une nouvelle source

1. Copier `_template/` vers `{nom_source}/`
2. Implémenter `client.py`
3. Créer `extract_*.py` avec `@step`/`@job`
4. Remplir `config.yaml`
5. Ajouter les variables d'env dans `.env.example`
6. Ecrire les tests dans `tests/unit/test_ingestion_{nom_source}.py`

Voir la checklist complète : `docs/data-plateforme/03-patterns-conventions.md` § 9.
