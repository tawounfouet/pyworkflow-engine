# Data Plateforme — Documentation

> **Date :** 11 avril 2026  
> **Auteur :** Thomas AWOUNFOUET  
> **Statut :** ADR approuvée — implémentation à planifier

---

Ce dossier documente les **décisions architecturales** pour l'organisation
des flux opérationnels de données autour de `pyworkflow-engine`.

## Documents

| Document | Description |
|---|---|
| [01 — Organisation `jobs/`](./01-organisation-jobs.md) | ADR : création du dossier `jobs/` à la racine pour les flux de production |
| [02 — Architecture en couches](./02-architecture-couches.md) | Design de la couche Ingestion (Bronze) et Transformation (Silver/Gold) |
| [03 — Patterns et conventions](./03-patterns-conventions.md) | Patrons de code, conventions de nommage, abstractions partagées |
| [04 — Data Lake local et Pipelines](./04-datalake-local-et-pipelines.md) | ADR : `data/` comme Data Lake local et `pipelines/` pour l'orchestration |

## Contexte

Le projet `pyworkflow-engine` fournit un **moteur d'orchestration** (le framework).
La question se pose de **comment organiser les flux métier concrets** — ETL, ELT,
ML, Reporting — qui utilisent ce moteur au quotidien.

Les décisions documentées ici répondent à :

1. **Où placer** les définitions de jobs de production vs. les exemples pédagogiques ?
2. **Comment structurer** les flux par domaine (ETL, ELT, ML, Reporting, Ops) ?
3. **Comment architecturer** une pipeline data complète avec couche d'ingestion
   (sources → Data Lake) et couche de transformation (Data Lake → Data Warehouse) ?
4. **Où stocker** les données locales (Data Lake) et **comment orchestrer** le
   chaînage des jobs (pipelines) ?

## Diagramme de synthèse

```
pyworkflow-engine/
├── src/                    ← Le framework (moteur)
├── data/                   ← Data Lake local (FS) ★ — déjà existant
│   └── datalake/
│       └── raw/            ← Données brutes par source
├── examples/               ← Exemples pédagogiques
├── jobs/                   ← Jobs unitaires (1 fichier = 1 job) ★
│   ├── ingestion/          ← Couche 1 — Bronze / Raw
│   ├── transformation/     ← Couche 2 — Silver + Gold
│   ├── ml/                 ← Couche 3 — Machine Learning
│   ├── reporting/          ← Couche 4 — Rapports
│   ├── ops/                ← Maintenance
│   └── shared/             ← Utilitaires transversaux
├── pipelines/              ← Orchestration des jobs (chaînage) ★
│   ├── daily/
│   ├── weekly/
│   └── on_demand/
├── tests/
└── docs/
```
