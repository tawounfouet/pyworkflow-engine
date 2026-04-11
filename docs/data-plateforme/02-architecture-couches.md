# ADR-02 — Architecture en couches : Ingestion et Transformation

> **Date :** 11 avril 2026  
> **Statut :** ✅ Approuvée  
> **Décideurs :** Thomas AWOUNFOUET  
> **Catégorie :** Architecture données  
> **Pré-requis :** [ADR-01 — Organisation `jobs/`](./01-organisation-jobs.md)

---

## Contexte

L'ADR-01 définit le dossier `jobs/` pour les flux opérationnels. La question
suivante se pose : **comment structurer les pipelines de données** au sein
de ce dossier, en particulier pour les cas d'usage ETL/ELT récurrents ?

Les besoins identifiés :

1. **Connecter** de multiples sources (API, SFTP, bases, fichiers…)
2. **Stocker en brut** les données extraites (Data Lake)
3. **Transformer** les données brutes pour alimenter un Data Warehouse
   (DuckDB en dev, PostgreSQL en prod)
4. **Isoler** chaque source dans un dossier dédié (maintenabilité)

## Décision

Adopter une **architecture Medallion** (Bronze → Silver → Gold) organisée
en deux couches principales dans `jobs/` :

| Couche | Dossier | Rôle | Cible |
|---|---|---|---|
| **Ingestion** (Bronze) | `jobs/ingestion/` | Extraction brute des sources | Data Lake |
| **Transformation** (Silver + Gold) | `jobs/transformation/` | Nettoyage, typage, agrégation | Data Warehouse |

---

## Architecture Medallion

```
┌──────────────────────────────────────────────────────────────────┐
│                      SOURCES EXTERNES                            │
│  SAP ERP │ Salesforce │ Stripe │ SFTP │ Google Analytics │ ...   │
└────┬──────────┬──────────┬────────┬──────────┬───────────────────┘
     │          │          │        │          │
     ▼          ▼          ▼        ▼          ▼
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   jobs/ingestion/          COUCHE 1 — BRONZE                     │
│   1 dossier par source     Connecteurs + extraction + validation │
│   Écriture brute JSON/Parquet                                    │
│                                                                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│              DATA LAKE  (dev: data/datalake/ — prod: S3/Blob)     │
│   raw/stripe/payments/2026-04-10/data.json                       │
│   raw/salesforce/leads/2026-04-10/data.parquet                   │
│                                                                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   jobs/transformation/     COUCHE 2 — SILVER + GOLD              │
│   staging/   → Nettoyage, typage, dédup → staging.*              │
│   marts/     → Agrégation, modèles métier → marts.*              │
│   quality/   → Checks post-load                                  │
│                                                                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│           DATA WAREHOUSE  (dev: data/warehouse/ — prod: PG)      │
│   staging.stg_payments │ staging.stg_customers │ ...             │
│   marts.finance.revenue │ marts.sales.pipeline │ ...             │
│                                                                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   jobs/reporting/ + jobs/ml/       COUCHES 3-4                   │
│   Rapports │ Dashboards │ Training │ Scoring                     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Couche Ingestion — `jobs/ingestion/`

### Principe

Chaque **source de données** possède son propre dossier contenant :

| Fichier | Rôle |
|---|---|
| `client.py` | Connecteur spécifique à la source (API, SFTP, DB…) |
| `extract_*.py` | Job(s) d'extraction (1 par entité/table) |
| `config.yaml` | Paramètres de la source (endpoints, mapping…) |
| `README.md` | Documentation de la source (optionnel) |

### Structure

```
jobs/ingestion/
├── __init__.py
├── README.md
│
├── erp_sap/                        # Source : SAP ERP
│   ├── __init__.py
│   ├── client.py                   # Connecteur API SAP
│   ├── extract_orders.py           # Job : extraction commandes
│   ├── extract_customers.py        # Job : extraction clients
│   └── config.yaml
│
├── salesforce/                     # Source : Salesforce CRM
│   ├── __init__.py
│   ├── client.py                   # Connecteur API Salesforce
│   ├── extract_leads.py
│   ├── extract_opportunities.py
│   └── config.yaml
│
├── stripe/                         # Source : Stripe (paiements)
│   ├── __init__.py
│   ├── client.py
│   ├── extract_payments.py
│   ├── extract_subscriptions.py
│   └── config.yaml
│
├── sftp_partners/                  # Source : fichiers SFTP
│   ├── __init__.py
│   ├── client.py
│   ├── ingest_partner_a.py
│   └── config.yaml
│
├── google_analytics/               # Source : GA4
│   ├── __init__.py
│   ├── client.py
│   ├── extract_events.py
│   └── config.yaml
│
└── _template/                      # Template pour nouvelles sources
    ├── __init__.py
    ├── client.py
    ├── extract_example.py
    └── config.yaml
```

### Flux d'un job d'ingestion

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   EXTRACT   │────▶│  VALIDATE    │────▶│  LOAD TO        │
│  (API call) │     │  (raw check) │     │  DATA LAKE      │
└─────────────┘     └──────────────┘     └─────────────────┘
       │                    │                      │
       ▼                    ▼                      ▼
  Appel source        Champs requis?        Écriture brute
  (pagination,        Non-vide?             JSON / Parquet
   auth, retry)       Schema valide?        Partitionné /date
```

### Conventions d'ingestion

| Règle | Détail |
|---|---|
| **Idempotence** | Chaque job est rejouable (partitionnement par date, pas d'insert aveugle) |
| **Brut = brut** | Aucune transformation dans la couche ingestion — données telles quelles |
| **Partitionnement** | `raw/{source}/{entity}/{date}/` |
| **Format** | JSON pour les petits volumes, Parquet pour les gros volumes |
| **Validation minimale** | Vérifier la non-vacuité et la présence des champs critiques |

---

## Couche Transformation — `jobs/transformation/`

### Principe

Deux sous-couches suivant le modèle **dbt** :

| Sous-couche | Schéma DWH | Rôle |
|---|---|---|
| **staging/** (Silver) | `staging.*` | Nettoyage, typage, déduplication, renommage |
| **marts/** (Gold) | `marts.*` | Agrégation, modèles métier, KPIs |
| **quality/** | — | Checks de qualité post-chargement |

### Structure

```
jobs/transformation/
├── __init__.py
├── README.md
│
├── staging/                         # Silver : nettoyage
│   ├── __init__.py
│   ├── stg_orders.py               # staging.stg_orders
│   ├── stg_customers.py            # staging.stg_customers
│   ├── stg_payments.py             # staging.stg_payments
│   └── stg_leads.py                # staging.stg_leads
│
├── marts/                           # Gold : modèles métier
│   ├── __init__.py
│   ├── finance/
│   │   ├── __init__.py
│   │   ├── mart_revenue.py         # marts.finance.revenue
│   │   └── mart_mrr.py             # marts.finance.mrr
│   ├── sales/
│   │   ├── __init__.py
│   │   ├── mart_pipeline.py        # marts.sales.pipeline
│   │   └── mart_conversion.py      # marts.sales.conversion
│   └── product/
│       ├── __init__.py
│       └── mart_usage_metrics.py   # marts.product.usage_metrics
│
└── quality/                         # Checks de qualité
    ├── __init__.py
    ├── check_completeness.py
    └── check_freshness.py
```

### Flux d'un job de transformation (staging)

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐     ┌──────────────┐
│  READ FROM    │────▶│  CLEAN &      │────▶│  LOAD TO      │────▶│  QUALITY     │
│  DATA LAKE    │     │  TYPE         │     │  WAREHOUSE    │     │  CHECK       │
└───────────────┘     └───────────────┘     └───────────────┘     └──────────────┘
       │                     │                      │                     │
       ▼                     ▼                      ▼                     ▼
  Lecture raw/          Typage colonnes       Upsert dans          COUNT, NULL
  JSON ou Parquet       Déduplication         staging.*            checks, freshness
  depuis le DL          Renommage             (DuckDB/Postgres)    validation
```

### Conventions de transformation

| Règle | Détail |
|---|---|
| **Staging = 1:1** | Un fichier staging par entité source (pas de jointures) |
| **Marts = N:1** | Les marts combinent plusieurs staging selon le domaine métier |
| **Upsert** | Toujours upsert (pas insert) pour l'idempotence |
| **Quality gate** | Chaque pipeline se termine par un step de quality check |
| **Nommage** | `stg_` prefix pour staging, `mart_` prefix pour marts |

---

## Choix technologiques

### Data Lake

| Critère | Choix |
|---|---|
| **Dev local** | Filesystem local (`./data/datalake/`) |
| **Staging** | S3 / Azure Blob / MinIO |
| **Production** | S3 / Azure Blob Storage |
| **Abstraction** | `jobs/shared/datalake.py` — interface unifiée |

Le passage d'un backend à l'autre se fait par variable d'environnement,
sans modification du code des jobs.

### Data Warehouse

| Critère | Choix |
|---|---|
| **Dev local** | DuckDB (`data/warehouse/warehouse.duckdb`, zero config) |
| **Production** | PostgreSQL |
| **Abstraction** | `jobs/shared/warehouse.py` — interface unifiée |

**DuckDB** est idéal pour le développement et les petits volumes :
- Zéro dépendance serveur
- Compatible SQL analytique
- Lecture directe Parquet / CSV

**PostgreSQL** prend le relais en production pour :
- Accès concurrent
- Scalabilité
- Intégration outils BI

Le choix est transparent grâce à l'abstraction `Warehouse` :

```python
# Le même code fonctionne en dev (DuckDB) et en prod (Postgres)
wh = Warehouse.from_env()  # lit WAREHOUSE_BACKEND + WAREHOUSE_CONN
wh.upsert("staging.stg_payments", data, key="payment_id")
```

---

## Diagramme de flux bout-en-bout

```
                    ┌─────────────────────────┐
                    │    SCHEDULING LAYER      │
                    │  (cron / Celery / CLI)   │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │     pipelines/           │
                    │  daily/stripe_to_dwh.py  │
                    │  weekly/kpi_report.py     │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    WorkflowEngine       │
                    │    (pyworkflow-engine)   │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
              ▼                  ▼                   ▼
    ┌─────────────────┐ ┌───────────────┐ ┌─────────────────┐
    │ jobs/ingestion/  │ │ jobs/transf./ │ │ jobs/reporting/  │
    │                  │ │               │ │ jobs/ml/         │
    │ extract → DL     │ │ DL → DWH      │ │ DWH → output    │
    └────────┬────────┘ └───────┬───────┘ └────────┬────────┘
             │                  │                   │
             ▼                  ▼                   ▼
    ┌─────────────────┐ ┌───────────────┐ ┌─────────────────┐
    │   data/datalake/ │ │data/warehouse/│ │  data/exports/  │
    │   (S3 en prod)   │ │(PG en prod)   │ │ (PDF/Email/API) │
    └─────────────────┘ └───────────────┘ └─────────────────┘
```

> Voir [ADR-04](./04-datalake-local-et-pipelines.md) pour le détail de `data/`
> et `pipelines/`.

---

## Orchestration chaînée

Les couches peuvent être **chaînées** via un fichier pipeline dans
`pipelines/` (voir [ADR-04](./04-datalake-local-et-pipelines.md)) ou
exécutées indépendamment via le scheduling :

### Option A — Scheduling indépendant (recommandé)

```yaml
# manifest.yaml — chaque job a son propre schedule
jobs:
  - path: ingestion/stripe/extract_payments.py
    schedule: "0 1 * * *"         # 01h00 — ingestion d'abord

  - path: transformation/staging/stg_payments.py
    schedule: "0 3 * * *"         # 03h00 — transformation après

  - path: reporting/weekly_kpi_report.py
    schedule: "0 8 * * 1"         # Lundi 08h00
```

### Option B — Pipeline orchestrée (dans `pipelines/`)

```python
"""
pipelines/daily/stripe_to_dwh.py
Pipeline complète : Ingestion Stripe → Staging → Marts.
"""

from pyworkflow_engine import WorkflowEngine
from jobs.ingestion.stripe.extract_payments import job as ingest_job
from jobs.transformation.staging.stg_payments import job as staging_job

engine = WorkflowEngine()

# Exécution séquentielle avec propagation de contexte
ingest = engine.run(ingest_job, initial_context={"since_date": "2026-04-10"})
if ingest.status.value == "SUCCESS":
    engine.run(staging_job, initial_context={"partition": "2026-04-10"})
```

> Voir [ADR-04](./04-datalake-local-et-pipelines.md) pour le patron complet
> d'un fichier pipeline avec gestion d'erreurs et notifications.

---

## Alternatives considérées

| Alternative | Rejetée car |
|---|---|
| Un seul dossier `etl/` plat | Ne scale pas au-delà de 20 jobs |
| Organisation par fréquence (`daily/`, `weekly/`) | Un même job peut changer de fréquence |
| dbt pour la transformation | Dépendance externe lourde ; pyworkflow couvre le besoin |
| Tout dans le DWH (ELT pur) | Perte des données brutes ; pas de replay possible |

## Conséquences

### Positives
- Architecture éprouvée (Medallion / Bronze-Silver-Gold)
- Chaque source est isolée → maintenabilité
- Replay possible à chaque couche (données brutes conservées)
- DuckDB en dev → itération rapide, Postgres en prod → robustesse
- Abstractions `DataLake` / `Warehouse` → portabilité

### Points d'attention
- Les secrets (API keys, credentials) ne doivent **jamais** être dans `config.yaml` → env vars / vault
- Le template `_template/` doit être maintenu à jour
- Les data contracts (schemas) doivent être définis dans `shared/schemas.py`
- La lineage est fournie gratuitement par le DAG de pyworkflow-engine
