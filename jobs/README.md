# Jobs — Flux opérationnels de production

Ce dossier contient l'ensemble des **jobs unitaires** du projet, organisés par domaine.

> Chaque fichier = 1 job atomique. Pour le chaînage de plusieurs jobs,
> voir le dossier [`pipelines/`](../pipelines/README.md).

## Structure

```
jobs/
├── ingestion/          ← Couche 1 — Bronze / Raw (1 dossier par source)
├── transformation/     ← Couche 2 — Silver + Gold (staging, marts, quality)
├── ml/                 ← Couche 3 — Machine Learning (training, inference, monitoring)
├── reporting/          ← Couche 4 — Rapports
├── ops/                ← Maintenance / opérations
└── shared/             ← Utilitaires transversaux (DataLake, Warehouse, connections)
```

## Architecture

Voir la documentation complète dans [`docs/data-plateforme/`](../docs/data-plateforme/README.md).

## Exécution

```bash
# Exécuter un job unitaire directement
python -m jobs.ingestion.stripe.extract_payments

# Exécuter une pipeline complète (chaînage)
python -m pipelines.daily.stripe_to_dwh
```
