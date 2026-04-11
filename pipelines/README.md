# pipelines/

> Orchestration et chaînage des jobs en scénarios opérationnels.

## Structure

```
pipelines/
├── __init__.py
├── README.md              ← ce fichier
├── daily/                 # Pipelines quotidiennes
│   ├── __init__.py
│   └── stripe_to_dwh.py  # Stripe → DataLake → Staging → Mart
├── weekly/                # Pipelines hebdomadaires
│   └── __init__.py
├── monthly/               # Pipelines mensuelles
│   └── __init__.py
├── on_demand/             # Pipelines manuelles (backfill, reprocess…)
│   └── __init__.py
└── shared/                # Utilitaires d'orchestration
    ├── __init__.py
    ├── runner.py           # PipelineRunner — séquenceur de jobs
    └── notifications.py    # Notifications pipeline-level
```

## Convention de nommage

| Élément          | Pattern                          | Exemple                      |
|-----------------|----------------------------------|------------------------------|
| Fichier pipeline | `{source}_to_{destination}.py`  | `stripe_to_dwh.py`          |
| Nom pipeline     | `{fréquence}-{source}-to-{dest}` | `daily-stripe-to-dwh`       |

## Utilisation

### Exécution directe

```bash
# Pipeline quotidienne Stripe (date du jour)
python -m pipelines.daily.stripe_to_dwh

# Avec une date spécifique
python -m pipelines.daily.stripe_to_dwh --date 2026-04-10
```

### Utilisation programmatique

```python
from pipelines.daily.stripe_to_dwh import build_pipeline

runner = build_pipeline(date="2026-04-10")
result = runner.execute()

print(result.summary)
assert result.success
```

### PipelineRunner API

```python
from pipelines.shared.runner import PipelineRunner
from jobs.ingestion.stripe.extract_payments import job as ingest_job
from jobs.transformation.staging.stg_payments import job as staging_job

runner = PipelineRunner("my-custom-pipeline")
runner.add_job(ingest_job, initial_context={"since_date": "2026-04-10"})
runner.add_job(staging_job, initial_context={"partition": "2026-04-10"})

result = runner.execute()
for jr in result.job_results:
    print(f"  {jr.job_name}: {jr.status.value} ({jr.duration_s}s)")
```

## Flux de données

```
Pipeline daily-stripe-to-dwh
│
├─ 1. ingestion-stripe-payments
│     API Stripe → data/datalake/raw/stripe/payments/{date}/
│
├─ 2. transform-stg-payments
│     data/datalake/raw/… → DWH staging_stg_payments
│
├─ 3. transform-mart-finance-revenue
│     DWH staging_stg_payments → DWH marts_finance_revenue
│
└─ 4. quality-check-completeness
      Vérification tables staging + taux de NULL
```

## Créer une nouvelle pipeline

1. Choisir le dossier de fréquence (`daily/`, `weekly/`, `monthly/`, `on_demand/`)
2. Créer le fichier `{source}_to_{destination}.py`
3. Importer les jobs depuis `jobs/`
4. Construire un `PipelineRunner` et chaîner les jobs avec `add_job()`
5. Ajouter un `if __name__ == "__main__"` pour l'exécution directe

## Voir aussi

- [`jobs/README.md`](../jobs/README.md) — Jobs unitaires
- [`docs/data-plateforme/04-datalake-local-et-pipelines.md`](../docs/data-plateforme/04-datalake-local-et-pipelines.md) — ADR architecture
- [`docs/data-plateforme/02-architecture-couches.md`](../docs/data-plateforme/02-architecture-couches.md) — Architecture Medallion
