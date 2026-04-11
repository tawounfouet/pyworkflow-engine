# ADR-04 — Data Lake local (`data/`) et orchestration (`pipelines/`)

> **Date :** 11 avril 2026  
> **Statut :** ✅ Approuvée  
> **Décideurs :** Thomas AWOUNFOUET  
> **Catégorie :** Architecture projet / données  
> **Pré-requis :** [ADR-01](./01-organisation-jobs.md), [ADR-02](./02-architecture-couches.md)

---

## Contexte

Deux questions restaient ouvertes après les ADR précédentes :

1. **Où stocker les données locales ?** L'abstraction `DataLake` référence un
   chemin local (`DATALAKE_PATH`), mais le dossier physique n'était pas formalisé.
2. **Où orchestrer le chaînage de jobs ?** Les fichiers dans `jobs/` sont des
   **jobs unitaires** (1 fichier = 1 unité de travail). Quand on veut enchaîner
   plusieurs jobs (ingestion → staging → marts → reporting), il faut un endroit
   dédié pour ces **pipelines d'orchestration**.

---

## Décision 1 — `data/` comme Data Lake local

Le dossier **`data/`** — déjà existant à la racine du projet, au même niveau que
`src/`, `jobs/` et `examples/` — sert de **Data Lake local** (filesystem) pour
le développement et les tests.

### Structure de `data/`

```
data/                                    ← Racine Data Lake local
├── datalake/                            ← Zone Bronze (données brutes)
│   └── raw/
│       ├── stripe/
│       │   ├── payments/
│       │   │   ├── 2026-04-10/
│       │   │   │   └── data.json
│       │   │   └── 2026-04-11/
│       │   │       └── data.json
│       │   └── subscriptions/
│       │       └── ...
│       ├── salesforce/
│       │   ├── leads/
│       │   │   └── ...
│       │   └── opportunities/
│       │       └── ...
│       ├── erp_sap/
│       │   └── ...
│       └── sftp_partners/
│           └── ...
│
├── warehouse/                           ← Zone DWH locale
│   └── warehouse.duckdb                 ← Base DuckDB (staging + marts)
│
└── exports/                             ← Zone de sortie (rapports, CSV…)
    └── reports/
        └── ...
```

### Convention de partitionnement

```
data/datalake/raw/{source}/{entity}/{date}/data.{format}
```

| Segment | Exemple | Description |
|---|---|---|
| `{source}` | `stripe`, `salesforce` | Nom de la source (= nom du dossier dans `jobs/ingestion/`) |
| `{entity}` | `payments`, `leads` | Entité extraite |
| `{date}` | `2026-04-10` | Date de partition (ISO 8601) |
| `{format}` | `json`, `parquet` | Format des données brutes |

### Gitignore

Le contenu de `data/` est **gitignored** (données locales, non versionnées).
Seul le dossier vide est conservé :

```gitignore
# Data Lake local — données non versionnées
data/datalake/
data/warehouse/
data/exports/

# Conserver la structure de dossiers
!data/.gitkeep
```

### Variables d'environnement par défaut

```bash
# .env (dev local)
DATALAKE_PATH=./data/datalake
WAREHOUSE_BACKEND=duckdb
WAREHOUSE_CONN=./data/warehouse/warehouse.duckdb
```

### En production

En production, `data/` n'existe pas. Les variables d'environnement pointent
vers les backends réels :

```bash
# .env.prod
DATALAKE_PATH=s3://company-datalake
WAREHOUSE_BACKEND=postgres
WAREHOUSE_CONN=postgresql://user:pass@host:5432/dwh
```

Le code des jobs et des pipelines ne change **pas du tout** — seules les
variables d'environnement changent.

---

## Décision 2 — `pipelines/` pour l'orchestration des jobs

### Le problème

Les fichiers dans `jobs/` sont des **unités atomiques** :
- `jobs/ingestion/stripe/extract_payments.py` → 1 job d'ingestion
- `jobs/transformation/staging/stg_payments.py` → 1 job de transformation

Mais en opérationnel, on a besoin de **chaîner** ces jobs :
> « Tous les jours à 02h00 : ingérer Stripe, puis transformer en staging,
> puis calculer les marts finance, puis envoyer le rapport KPI. »

Mélanger ce code d'orchestration dans `jobs/` polluerait la séparation
job unitaire / pipeline.

### La solution

Un dossier **`pipelines/`** à la racine, au même niveau que `jobs/` et `data/`,
dédié aux **scénarios d'orchestration** qui chaînent plusieurs jobs.

### Structure de `pipelines/`

```
pipelines/                               ← Orchestration des jobs
├── __init__.py
├── README.md
│
├── daily/                               ← Pipelines quotidiennes
│   ├── __init__.py
│   ├── stripe_to_dwh.py                ← Stripe: ingestion → staging → marts
│   ├── salesforce_to_dwh.py            ← Salesforce: ingestion → staging
│   └── full_refresh.py                 ← Toutes les sources
│
├── weekly/                              ← Pipelines hebdomadaires
│   ├── __init__.py
│   ├── ml_training.py                  ← Ré-entraînement des modèles
│   └── kpi_report.py                   ← Rapport KPI hebdo
│
├── monthly/                             ← Pipelines mensuelles
│   ├── __init__.py
│   └── finance_closing.py              ← Clôture comptable
│
├── on_demand/                           ← Pipelines manuelles / déclenchées
│   ├── __init__.py
│   ├── backfill.py                     ← Rejouer N jours d'historique
│   └── full_reprocess.py               ← Retraitement complet
│
└── shared/                              ← Utilitaires de pipeline
    ├── __init__.py
    ├── runner.py                        ← PipelineRunner helper
    └── notifications.py                 ← Alertes inter-jobs
```

### Distinction `jobs/` vs `pipelines/`

| Aspect | `jobs/` | `pipelines/` |
|---|---|---|
| **Granularité** | 1 fichier = 1 job atomique | 1 fichier = N jobs chaînés |
| **Responsabilité** | Faire **une seule chose** bien | **Orchestrer** la séquence |
| **Dépendance** | Aucune entre fichiers | Importe des jobs depuis `jobs/` |
| **Exécutable seul** | ✅ Oui (`python -m jobs.ingestion...`) | ✅ Oui (`python -m pipelines.daily...`) |
| **Réutilisable** | ✅ Par plusieurs pipelines | Un pipeline = un scénario spécifique |
| **Analogie** | Fonction | Script `main()` qui appelle les fonctions |

### Patron d'un fichier pipeline

```python
"""
Pipeline quotidienne — Stripe → DWH complet.

Chaîne les jobs :
  1. ingestion/stripe/extract_payments
  2. ingestion/stripe/extract_subscriptions
  3. transformation/staging/stg_payments
  4. transformation/staging/stg_subscriptions
  5. transformation/marts/finance/mart_mrr

Fréquence : quotidien (02h00 UTC)
Owner     : data-team@company.com
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.config import WorkflowConfig
from pyworkflow_engine.logging import get_logger

from jobs.ingestion.stripe.extract_payments import job as ingest_payments
from jobs.ingestion.stripe.extract_subscriptions import job as ingest_subs
from jobs.transformation.staging.stg_payments import job as stg_payments
from jobs.transformation.staging.stg_subscriptions import job as stg_subs
from jobs.transformation.marts.finance.mart_mrr import job as mart_mrr

_logger = get_logger("pipeline.daily.stripe_to_dwh")


def run(target_date: str | None = None) -> bool:
    """Exécute la pipeline complète Stripe → DWH.

    Args:
        target_date: Date cible (ISO). Défaut = hier.

    Returns:
        True si tous les jobs ont réussi, False sinon.
    """
    target = target_date or (date.today() - timedelta(days=1)).isoformat()
    engine = WorkflowEngine(config=WorkflowConfig.from_env())

    # ── Définition de la séquence ────────────────────────────────────
    pipeline = [
        ("Ingestion Payments", ingest_payments, {"since_date": target}),
        ("Ingestion Subscriptions", ingest_subs, {"since_date": target}),
        ("Staging Payments", stg_payments, {"partition": target}),
        ("Staging Subscriptions", stg_subs, {"partition": target}),
        ("Mart MRR", mart_mrr, {}),
    ]

    # ── Exécution séquentielle avec arrêt au premier échec ───────────
    for label, job, ctx in pipeline:
        _logger.info("▶ [%s] Démarrage...", label)
        result = engine.run(job, initial_context=ctx)

        if result.status.value != "SUCCESS":
            _logger.error("✗ [%s] Échec — arrêt du pipeline", label)
            # TODO: notification Slack/email
            return False

        _logger.info("✓ [%s] Succès (%s)", label, result.duration)

    _logger.info("🏁 Pipeline Stripe → DWH terminée avec succès")
    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    success = run(target_date=target)
    sys.exit(0 if success else 1)
```

### Exécution

```bash
# Pipeline quotidienne (date = hier par défaut)
python -m pipelines.daily.stripe_to_dwh

# Pipeline avec date spécifique
python -m pipelines.daily.stripe_to_dwh 2026-04-10

# Backfill sur 7 jours
python -m pipelines.on_demand.backfill --days 7 --source stripe

# Via le CLI pyworkflow (futur)
pyworkflow pipeline run daily/stripe_to_dwh --date 2026-04-10
```

---

## Vue d'ensemble — Arborescence complète

```
pyworkflow-engine/
│
├── src/                                 ← FRAMEWORK (moteur)
│   └── pyworkflow_engine/
│       ├── facade.py                    ← WorkflowEngine
│       ├── engine/                      ← Runner, DAG, Retry, Suspension
│       ├── models/                      ← Job, Step, JobRun, StepRun
│       ├── adapters/                    ← Persistence, CLI, API
│       └── ...
│
├── data/                                ← DATA LAKE LOCAL (dev) ★
│   ├── datalake/
│   │   └── raw/{source}/{entity}/{date}/
│   ├── warehouse/
│   │   └── warehouse.duckdb
│   └── exports/
│
├── jobs/                                ← JOBS UNITAIRES ★
│   ├── ingestion/                       ← 1 dossier par source
│   │   ├── stripe/
│   │   ├── salesforce/
│   │   └── ...
│   ├── transformation/
│   │   ├── staging/                     ← Silver
│   │   ├── marts/                       ← Gold
│   │   └── quality/
│   ├── ml/
│   ├── reporting/
│   ├── ops/
│   └── shared/                          ← DataLake, Warehouse, connections
│
├── pipelines/                           ← ORCHESTRATION ★
│   ├── daily/                           ← Chaînage quotidien
│   ├── weekly/                          ← Chaînage hebdomadaire
│   ├── monthly/                         ← Chaînage mensuel
│   ├── on_demand/                       ← Backfill, reprocess
│   └── shared/                          ← PipelineRunner, notifications
│
├── examples/                            ← EXEMPLES PÉDAGOGIQUES
├── tests/
├── docs/
├── pyproject.toml
└── README.md
```

---

## Diagramme de flux complet

```
                     ┌──────────────────────────┐
                     │     SCHEDULING LAYER      │
                     │   cron / Celery / CLI      │
                     └────────────┬─────────────┘
                                  │
                                  ▼
                     ┌──────────────────────────┐
                     │      pipelines/           │
                     │  daily/stripe_to_dwh.py   │
                     │  weekly/kpi_report.py      │
                     │  on_demand/backfill.py     │
                     └────────────┬─────────────┘
                                  │
                    ┌─────────────┼──────────────┐
                    │ engine.run  │  engine.run   │  engine.run
                    ▼             ▼               ▼
         ┌──────────────┐ ┌────────────┐ ┌──────────────┐
         │ jobs/         │ │ jobs/      │ │ jobs/        │
         │ ingestion/    │ │ transf./   │ │ reporting/   │
         │ extract_*     │ │ stg_*      │ │ weekly_*     │
         └──────┬───────┘ └─────┬──────┘ └──────┬───────┘
                │               │                │
                ▼               │                │
  ┌──────────────────────┐      │                │
  │    data/datalake/     │      │                │
  │    raw/{source}/...   │◀────┘                │
  │    (Bronze)           │                      │
  └──────────────────────┘                       │
                │                                │
                ▼                                │
  ┌──────────────────────┐                       │
  │   data/warehouse/     │                       │
  │   warehouse.duckdb    │───────────────────────┘
  │   (Silver + Gold)     │
  └──────────────────────┘
         OU (en prod)
  ┌──────────────────────┐
  │   PostgreSQL          │
  │   staging.* / marts.* │
  └──────────────────────┘
```

---

## Relation entre les dossiers

```
pipelines/daily/stripe_to_dwh.py
    │
    │  importe et chaîne
    │
    ├── jobs/ingestion/stripe/extract_payments.py ──▶ data/datalake/raw/stripe/payments/
    ├── jobs/ingestion/stripe/extract_subs.py ──────▶ data/datalake/raw/stripe/subscriptions/
    ├── jobs/transformation/staging/stg_payments.py ─▶ data/warehouse/warehouse.duckdb
    ├── jobs/transformation/staging/stg_subs.py ────▶ data/warehouse/warehouse.duckdb
    └── jobs/transformation/marts/finance/mart_mrr.py ▶ data/warehouse/warehouse.duckdb
```

La flèche est claire :
- **`pipelines/`** orchestre → **`jobs/`** exécute → **`data/`** stocke

---

## `pyproject.toml` — mise à jour

```toml
[tool.pytest.ini_options]
pythonpath = ["src", "jobs", "pipelines"]
```

---

## Alternatives considérées

| Alternative | Rejetée car |
|---|---|
| Pipelines dans `jobs/` | Mélange responsabilités (unitaire vs. orchestration) |
| `data/` dans `jobs/shared/` | Couplage données ↔ code, pas gitignore-friendly |
| `data/` dans `/tmp/` ou hors projet | Perte de contexte dev, non reproductible |
| Pas de dossier `pipelines/` (tout en CLI) | Pas de versioning, pas de code-review |
| Organiser `pipelines/` par domaine (`etl/`, `ml/`) plutôt que par fréquence | La fréquence drive le scheduling ; le domaine est déjà dans `jobs/` |

---

## Résumé des décisions

| # | Décision | Justification |
|---|---|---|
| D-11 | `data/` à la racine = Data Lake local | Déjà existant, même niveau que `src/` et `jobs/`, gitignored |
| D-12 | Sous-structure `data/datalake/raw/` + `data/warehouse/` | Séparation Bronze / DWH en local |
| D-13 | `data/` gitignored, variables d'env pour le chemin | Portabilité dev → prod sans changement de code |
| D-14 | `pipelines/` à la racine pour l'orchestration | Séparation job unitaire / chaînage |
| D-15 | Organisation par fréquence (`daily/`, `weekly/`, `on_demand/`) | Aligné sur le scheduling, lisible |
| D-16 | Chaque pipeline = 1 fichier Python exécutable | Simple, testable, versionné, code-reviewable |
