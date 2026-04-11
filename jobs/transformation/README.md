# Transformation — Couche 2 (Silver + Gold)

Nettoyage, typage, agrégation des données brutes → Data Warehouse.

## Structure

```
transformation/
├── staging/      ← Silver : nettoyage 1:1 depuis le Data Lake
├── marts/        ← Gold : modèles métier agrégés
│   ├── finance/
│   └── sales/
└── quality/      ← Checks de qualité post-chargement
```

## Conventions

- **Staging** = 1 fichier par entité source (pas de jointures)
- **Marts** = combinent plusieurs staging par domaine métier
- **Nommage** : `stg_` pour staging, `mart_` pour marts
- **Upsert** systématique (idempotence)
- **Quality check** en fin de chaque pipeline

## Exécution

```bash
python -m jobs.transformation.staging.stg_payments
python -m jobs.transformation.marts.finance.mart_revenue
python -m jobs.transformation.quality.check_completeness
```
