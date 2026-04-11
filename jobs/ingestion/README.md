# Ingestion — Couche 1 (Bronze)

Extraction brute des sources externes → Data Lake.

## Principe

- **1 dossier par source** (Stripe, Salesforce, SAP ERP, SFTP…)
- Chaque dossier contient :
  - `client.py` — Connecteur spécifique à la source
  - `extract_*.py` — Job(s) d'extraction (1 par entité)
  - `config.yaml` — Paramètres de la source
- Les données sont écrites **brutes** (JSON/Parquet) dans `data/datalake/raw/`

## Ajouter une nouvelle source

1. Copier `_template/` → `{nom_source}/`
2. Implémenter `client.py`
3. Créer les `extract_*.py`
4. Remplir `config.yaml`
5. Ajouter les variables d'env dans `.env.example`

Voir la checklist complète : `docs/data-plateforme/03-patterns-conventions.md` § 9.

## Exécution

```bash
python -m jobs.ingestion.stripe.extract_payments
```
