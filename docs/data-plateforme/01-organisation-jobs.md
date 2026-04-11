# ADR-01 — Organisation du dossier `jobs/`

> **Date :** 11 avril 2026  
> **Statut :** ✅ Approuvée  
> **Décideurs :** Thomas AWOUNFOUET  
> **Catégorie :** Architecture projet

---

## Contexte

Le projet `pyworkflow-engine` dispose de :

- **`src/pyworkflow_engine/`** — le framework (moteur d'orchestration)
- **`examples/`** — des exemples pédagogiques pour la documentation

Les flux opérationnels de production (ETL, ELT, ML, Reporting…) n'ont
pas de place dédiée. Ils risquent de finir :
- mélangés dans `examples/` (confusion pédagogie vs. production)
- dispersés dans `src/` (pollution du package)
- dans des repos séparés (perte de cohérence)

## Décision

**Créer un dossier `jobs/` à la racine**, au même niveau que `src/` et
`examples/`, pour héberger l'ensemble des flux opérationnels organisés
par domaine.

## Justification

### Séparation des responsabilités

| Dossier | Rôle | Audience |
|---|---|---|
| `src/` | Le **framework** (moteur, modèles, adapters) | Développeurs du moteur |
| `examples/` | **Exemples pédagogiques** (onboarding, docs) | Nouveaux utilisateurs |
| `jobs/` | **Flux de production** (vrais workflows) | Data engineers, ML engineers |

### Cohérence avec l'écosystème

Des outils comparables adoptent la même convention :

| Outil | Dossier de workflows |
|---|---|
| Apache Airflow | `dags/` |
| Prefect | `flows/` |
| dbt | `models/` |
| Luigi | `tasks/` |
| **pyworkflow-engine** | **`jobs/`** ← cohérent avec le modèle `Job` |

Le nom `jobs/` est cohérent avec le vocabulaire du framework (`Job`, `JobRun`).

### Scalabilité

Un dossier dédié permet de passer de 5 à 500 jobs sans refactoring
structurel. Chaque domaine est un sous-dossier isolé.

## Structure adoptée

```
jobs/
├── __init__.py
├── manifest.yaml               # Registry de tous les jobs (optionnel)
│
├── etl/                        # Extract-Transform-Load
│   ├── __init__.py
│   ├── daily_sales_ingestion.py
│   ├── customer_sync.py
│   └── README.md
│
├── elt/                        # Extract-Load-Transform (dbt-style)
│   ├── __init__.py
│   ├── raw_to_staging.py
│   └── staging_to_marts.py
│
├── ml/                         # Machine Learning pipelines
│   ├── __init__.py
│   ├── training/
│   │   ├── churn_model_train.py
│   │   └── demand_forecast.py
│   ├── inference/
│   │   └── batch_scoring.py
│   └── monitoring/
│       └── model_drift_check.py
│
├── reporting/                  # Génération de rapports
│   ├── __init__.py
│   ├── weekly_kpi_report.py
│   └── monthly_finance.py
│
├── ops/                        # Maintenance / opérations
│   ├── __init__.py
│   ├── db_cleanup.py
│   └── health_check.py
│
├── ingestion/                  # Couche d'ingestion (→ ADR-02)
│   └── ...
│
├── transformation/             # Couche transformation (→ ADR-02)
│   └── ...
│
└── shared/                     # Utilitaires partagés entre jobs
    ├── __init__.py
    ├── connections.py          # Factories de connexions (DB, API, S3…)
    ├── datalake.py             # Abstraction lecture/écriture Data Lake
    ├── warehouse.py            # Abstraction DuckDB / Postgres
    ├── validators.py           # Validations communes
    └── notifications.py        # Alertes Slack/email/Teams
```

## Convention par fichier de job

Chaque fichier de job suit un **patron cohérent** :

```python
"""
[Catégorie] — Description courte.

Fréquence : quotidien (02h00 UTC)
Source    : API ERP → PostgreSQL staging
Owner     : data-team@company.com
"""

from pyworkflow_engine.models import Job, Step
from jobs.shared.connections import get_erp_client


# ── Steps ────────────────────────────────────────────────────────────────

def extract(**ctx):
    """Extraction depuis la source."""
    ...
    return {"raw_data": data}


def transform(**ctx):
    """Transformation des données."""
    ...
    return {"clean_data": cleaned}


def load(**ctx):
    """Chargement dans la cible."""
    ...
    return {"rows_inserted": count}


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="domain-action-descriptif",
    version="1.0.0",
    steps=[
        Step(name="extract", handler=extract),
        Step(name="transform", handler=transform, depends_on=["extract"]),
        Step(name="load", handler=load, depends_on=["transform"]),
    ],
)


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pyworkflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    result = engine.run(job)
    print(f"Terminé : {result.status}")
```

## Manifest (optionnel)

Un fichier `jobs/manifest.yaml` centralise les métadonnées pour le
scheduling et la découverte automatique :

```yaml
jobs:
  - path: etl/daily_sales_ingestion.py
    schedule: "0 2 * * *"
    category: etl
    owner: data-team@company.com
    tags: [sales, erp, critical]

  - path: ml/training/churn_model_train.py
    schedule: "0 6 * * 0"
    category: ml
    owner: ml-team@company.com
    tags: [churn, training]

  - path: reporting/weekly_kpi_report.py
    schedule: "0 8 * * 1"
    category: reporting
    owner: analytics@company.com
```

Ce manifest peut être consommé par :
- L'adapter **CLI** pour la découverte (`pyworkflow list-jobs`)
- L'adapter **Celery** pour le scheduling automatique
- L'adapter **API** pour l'exposition REST

## Configuration `pyproject.toml`

```toml
[tool.pytest.ini_options]
pythonpath = ["src", "jobs", "pipelines"]
```

> **Note :** `pipelines/` est ajouté au path pour l'orchestration des jobs.
> Voir [ADR-04 — Data Lake local et Pipelines](./04-datalake-local-et-pipelines.md).

## Alternatives considérées

| Alternative | Rejetée car |
|---|---|
| Tout dans `examples/` | Confusion pédagogie / production |
| Tout dans `src/` | Pollution du package distribué |
| Repos séparés par domaine | Fragmentation, perte de cohérence |
| Dossier `workflows/` | Moins cohérent avec le vocabulaire `Job` du framework |
| Pipelines dans `jobs/` | Mélange jobs unitaires et orchestration → voir ADR-04 pour `pipelines/` |

## Conséquences

### Positives
- Séparation claire framework / métier
- Onboarding facilité (structure lisible)
- Scale de 5 à 500+ jobs sans refactoring
- Compatible avec le scheduling (manifest.yaml)

### Points d'attention
- `jobs/` doit être ajouté au `PYTHONPATH` pour les imports
- Les tests des jobs vont dans `tests/jobs/` (miroir)
- Ne pas dupliquer entre `examples/` et `jobs/`
