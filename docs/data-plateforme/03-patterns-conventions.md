# 03 — Patterns, conventions et abstractions partagées

> **Date :** 11 avril 2026  
> **Statut :** ✅ Approuvée  
> **Pré-requis :** [ADR-01](./01-organisation-jobs.md), [ADR-02](./02-architecture-couches.md)

---

## Table des matières

1. [Patron d'un job d'ingestion](#1-patron-dun-job-dingestion)
2. [Patron d'un job de transformation](#2-patron-dun-job-de-transformation-staging)
3. [Abstraction DataLake](#3-abstraction-datalake)
4. [Abstraction Warehouse](#4-abstraction-warehouse)
5. [Conventions de nommage](#5-conventions-de-nommage)
6. [Variables d'environnement](#6-variables-denvironnement)
7. [Template de nouvelle source](#7-template-de-nouvelle-source)
8. [Orchestration bout-en-bout](#8-orchestration-bout-en-bout)
9. [Checklist ajout d'une source](#9-checklist-ajout-dune-source)

---

## 1. Patron d'un job d'ingestion

Chaque job d'ingestion suit le flux : **Extract → Validate → Load to DL**.

```python
"""
Ingestion — Stripe Payments → Data Lake (raw).

Fréquence : quotidien (01h00 UTC)
Source    : API Stripe /v1/charges
Cible     : datalake://raw/stripe/payments/{date}/
Owner     : data-team@company.com
"""

from pyworkflow_engine.models import Job, Step

from jobs.ingestion.stripe.client import StripeClient
from jobs.shared.datalake import DataLake


def extract(**ctx):
    """Appel API Stripe — récupération des paiements du jour."""
    client = StripeClient.from_env()
    since = ctx.get("since_date")
    charges = client.list_charges(created_gte=since, limit=1000)
    return {"raw_charges": charges, "count": len(charges)}


def validate_raw(**ctx):
    """Validation minimale avant écriture (schéma, non-vide)."""
    raw = ctx["raw_charges"]
    if not raw:
        return {"status": "empty", "skip_load": True}
    required = {"id", "amount", "currency", "created"}
    missing = [r for r in raw if not required.issubset(r.keys())]
    if missing:
        raise ValueError(f"{len(missing)} records missing required fields")
    return {"status": "valid", "skip_load": False}


def load_to_datalake(**ctx):
    """Écriture brute (JSON/Parquet) dans le Data Lake."""
    if ctx.get("skip_load"):
        return {"rows_written": 0, "skipped": True}
    dl = DataLake.from_env()
    partition = ctx.get("since_date", "latest")
    path = f"raw/stripe/payments/{partition}/"
    rows = dl.write_json(path, ctx["raw_charges"])
    return {"rows_written": rows, "path": path}


# ── Job definition ───────────────────────────────────────────────────

job = Job(
    name="ingestion-stripe-payments",
    version="1.0.0",
    steps=[
        Step(name="extract", handler=extract),
        Step(name="validate_raw", handler=validate_raw, depends_on=["extract"]),
        Step(name="load_to_datalake", handler=load_to_datalake, depends_on=["validate_raw"]),
    ],
)
```

### Points clés

- Le **docstring du module** contient les métadonnées (fréquence, source, cible, owner)
- Les steps retournent des **dicts** qui alimentent le contexte des steps suivants
- Le step `validate_raw` peut court-circuiter le load via `skip_load`
- Le job est **idempotent** (partitionnement par date)

---

## 2. Patron d'un job de transformation (staging)

Chaque job de staging suit le flux : **Read DL → Clean → Load DWH → Quality Check**.

```python
"""
Transformation — Raw Payments → Staging (DWH).

Fréquence : quotidien (03h00 UTC, après ingestion)
Source    : datalake://raw/stripe/payments/
Cible     : DWH staging.stg_payments (DuckDB / Postgres)
Owner     : data-team@company.com
"""

from pyworkflow_engine.models import Job, Step

from jobs.shared.datalake import DataLake
from jobs.shared.warehouse import Warehouse


def read_from_datalake(**ctx):
    """Lecture des données brutes depuis le Data Lake."""
    dl = DataLake.from_env()
    partition = ctx.get("partition", "latest")
    raw = dl.read_json(f"raw/stripe/payments/{partition}/")
    return {"raw_records": raw, "source_count": len(raw)}


def clean_and_type(**ctx):
    """Nettoyage, typage, déduplication."""
    import pandas as pd

    df = pd.DataFrame(ctx["raw_records"])
    df["amount_cents"] = df["amount"].astype(int)
    df["amount"] = df["amount_cents"] / 100
    df["created_at"] = pd.to_datetime(df["created"], unit="s", utc=True)
    df["currency"] = df["currency"].str.upper()

    before = len(df)
    df = df.drop_duplicates(subset=["id"], keep="last")
    dupes = before - len(df)

    df = df.rename(columns={"id": "payment_id"})
    cols = ["payment_id", "amount", "amount_cents", "currency", "created_at", "status"]
    df = df[[c for c in cols if c in df.columns]]

    return {
        "clean_records": df.to_dict(orient="records"),
        "clean_count": len(df),
        "duplicates_removed": dupes,
    }


def load_to_warehouse(**ctx):
    """Écriture dans le DWH (staging schema)."""
    wh = Warehouse.from_env()
    rows = wh.upsert(
        table="staging.stg_payments",
        data=ctx["clean_records"],
        key="payment_id",
    )
    return {"rows_upserted": rows}


def quality_check(**ctx):
    """Vérifications post-chargement."""
    wh = Warehouse.from_env()
    count = wh.query_scalar("SELECT COUNT(*) FROM staging.stg_payments")
    nulls = wh.query_scalar(
        "SELECT COUNT(*) FROM staging.stg_payments WHERE amount IS NULL"
    )
    return {
        "total_rows": count,
        "null_amounts": nulls,
        "quality_passed": nulls == 0,
    }


# ── Job definition ───────────────────────────────────────────────────

job = Job(
    name="transform-stg-payments",
    version="1.0.0",
    steps=[
        Step(name="read_from_datalake", handler=read_from_datalake),
        Step(name="clean_and_type", handler=clean_and_type, depends_on=["read_from_datalake"]),
        Step(name="load_to_warehouse", handler=load_to_warehouse, depends_on=["clean_and_type"]),
        Step(name="quality_check", handler=quality_check, depends_on=["load_to_warehouse"]),
    ],
)
```

---

## 3. Abstraction DataLake

L'abstraction `DataLake` encapsule le stockage brut. Le backend est
choisi par variable d'environnement, le code des jobs ne change pas.

```python
"""
jobs/shared/datalake.py
Abstraction Data Lake — lecture/écriture de données brutes.

Supporte : filesystem local, S3, Azure Blob (extensible).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class DataLake:
    """Interface unifiée pour le Data Lake."""

    def __init__(self, base_path: str):
        self._base = base_path

    @classmethod
    def from_env(cls) -> DataLake:
        """Factory depuis variables d'environnement."""
        base = os.environ.get("DATALAKE_PATH", "./data/datalake")
        return cls(base_path=base)

    def write_json(self, relative_path: str, data: list[dict]) -> int:
        """Écrit des données brutes en JSON dans le Data Lake."""
        full = Path(self._base) / relative_path
        full.mkdir(parents=True, exist_ok=True)
        target = full / "data.json"
        target.write_text(json.dumps(data, default=str, indent=2))
        return len(data)

    def read_json(self, relative_path: str) -> list[dict]:
        """Lit des données brutes JSON depuis le Data Lake."""
        target = Path(self._base) / relative_path / "data.json"
        if not target.exists():
            return []
        return json.loads(target.read_text())

    def write_parquet(self, relative_path: str, data: list[dict]) -> int:
        """Écrit des données en Parquet (nécessite pyarrow)."""
        import pyarrow as pa          # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        full = Path(self._base) / relative_path
        full.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist(data)
        pq.write_table(table, full / "data.parquet")
        return len(data)

    def read_parquet(self, relative_path: str) -> list[dict]:
        """Lit des données Parquet depuis le Data Lake."""
        import pyarrow.parquet as pq  # noqa: PLC0415

        target = Path(self._base) / relative_path / "data.parquet"
        if not target.exists():
            return []
        return pq.read_table(target).to_pylist()
```

### Diagramme de responsabilité

```
jobs/ingestion/*                    jobs/transformation/*
       │                                    │
       ▼                                    ▼
  dl.write_json(...)                  dl.read_json(...)
       │                                    │
       └──────────── DataLake ──────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │   Backend réel   │
              │ data/ (dev)      │
              │ S3/Blob (prod)   │
              └─────────────────┘
```

---

## 4. Abstraction Warehouse

L'abstraction `Warehouse` encapsule le Data Warehouse. DuckDB en dev,
PostgreSQL en prod — même API.

```python
"""
jobs/shared/warehouse.py
Abstraction Data Warehouse — DuckDB ou PostgreSQL.

Le backend est choisi via WAREHOUSE_BACKEND (env var).
"""

from __future__ import annotations

import os
from typing import Any


class Warehouse:
    """Interface unifiée pour le Data Warehouse."""

    def __init__(self, backend: str, connection_string: str):
        self._backend = backend
        self._conn_str = connection_string
        self._conn = None

    @classmethod
    def from_env(cls) -> Warehouse:
        """Factory depuis variables d'environnement."""
        backend = os.environ.get("WAREHOUSE_BACKEND", "duckdb")
        conn_str = os.environ.get("WAREHOUSE_CONN", "./data/warehouse/warehouse.duckdb")
        return cls(backend=backend, connection_string=conn_str)

    def _get_connection(self):
        if self._conn is None:
            if self._backend == "duckdb":
                import duckdb  # noqa: PLC0415
                self._conn = duckdb.connect(self._conn_str)
            elif self._backend == "postgres":
                import psycopg2  # noqa: PLC0415
                self._conn = psycopg2.connect(self._conn_str)
            else:
                raise ValueError(f"Unknown warehouse backend: {self._backend}")
        return self._conn

    def upsert(self, table: str, data: list[dict], key: str) -> int:
        """Upsert générique — insère ou met à jour selon la clé."""
        conn = self._get_connection()
        # Implémentation simplifiée — à adapter selon le backend
        return len(data)

    def query_scalar(self, sql: str) -> Any:
        """Exécute une requête SQL retournant une valeur scalaire."""
        conn = self._get_connection()
        result = conn.execute(sql).fetchone()
        return result[0] if result else None

    def query(self, sql: str) -> list[dict]:
        """Exécute une requête SQL retournant des lignes."""
        conn = self._get_connection()
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
```

### Matrice dev / prod

```
┌─────────────────┬────────────────────┬──────────────────────┐
│                  │    DEV (local)     │    PROD (serveur)    │
├─────────────────┼────────────────────┼──────────────────────┤
│ WAREHOUSE_BACKEND│   duckdb           │   postgres           │
│ WAREHOUSE_CONN   │   ./data/warehouse/│   postgresql://...   │
│                  │   warehouse.duckdb │                      │
│ DATALAKE_PATH    │   ./data/datalake  │   s3://bucket/raw    │
├─────────────────┼────────────────────┼──────────────────────┤
│ Avantages        │ Zero config        │ Concurrent access    │
│                  │ Pas de serveur     │ Scalabilité          │
│                  │ Itération rapide   │ Intégration BI       │
└─────────────────┴────────────────────┴──────────────────────┘
```

---

## 5. Conventions de nommage

### Jobs

| Couche | Pattern | Exemple |
|---|---|---|
| Ingestion | `ingestion-{source}-{entity}` | `ingestion-stripe-payments` |
| Staging | `transform-stg-{entity}` | `transform-stg-payments` |
| Marts | `transform-mart-{domain}-{metric}` | `transform-mart-finance-revenue` |
| ML | `ml-{action}-{model}` | `ml-train-churn-model` |
| Reporting | `report-{frequency}-{name}` | `report-weekly-kpi` |

### Fichiers

| Couche | Pattern | Exemple |
|---|---|---|
| Ingestion | `extract_{entity}.py` | `extract_payments.py` |
| Staging | `stg_{entity}.py` | `stg_payments.py` |
| Marts | `mart_{metric}.py` | `mart_revenue.py` |

### Data Lake paths

```
raw/{source}/{entity}/{date}/data.json
raw/stripe/payments/2026-04-10/data.json
raw/salesforce/leads/2026-04-11/data.parquet
```

### DWH schemas/tables

```
staging.stg_{entity}          → staging.stg_payments
marts.{domain}.{metric}       → marts.finance.revenue
```

---

## 6. Variables d'environnement

| Variable | Default | Description |
|---|---|---|
| `DATALAKE_PATH` | `./data/datalake` | Chemin racine du Data Lake (dossier `data/` à la racine du projet) |
| `WAREHOUSE_BACKEND` | `duckdb` | Backend DWH (`duckdb` ou `postgres`) |
| `WAREHOUSE_CONN` | `./data/warehouse/warehouse.duckdb` | Connection string du DWH |
| `STRIPE_API_KEY` | — | Clé API Stripe |
| `SALESFORCE_CLIENT_ID` | — | OAuth client ID Salesforce |
| `SFTP_HOST` | — | Hôte SFTP partenaires |

> ⚠️ **Règle absolue** : aucun secret dans les fichiers `config.yaml` ni
> dans le code. Utiliser des variables d'environnement, un fichier `.env`
> (gitignored), ou un vault (HashiCorp Vault, AWS Secrets Manager…).

---

## 7. Template de nouvelle source

Le dossier `jobs/ingestion/_template/` fournit un point de départ pour
ajouter une source rapidement :

```python
# jobs/ingestion/_template/client.py
"""
Connecteur pour [NOM_SOURCE].

Remplacer les TODO par les valeurs réelles.
"""

from __future__ import annotations

import os
from typing import Any


class TemplateClient:
    """Connecteur vers [NOM_SOURCE]."""

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url

    @classmethod
    def from_env(cls) -> TemplateClient:
        return cls(
            api_key=os.environ["TODO_API_KEY"],
            base_url=os.environ.get("TODO_BASE_URL", "https://api.example.com"),
        )

    def fetch_data(self, since: str | None = None) -> list[dict[str, Any]]:
        """TODO: Implémenter l'extraction."""
        raise NotImplementedError
```

```python
# jobs/ingestion/_template/extract_example.py
"""
Ingestion — [SOURCE] [ENTITY] → Data Lake (raw).

Fréquence : TODO
Source    : TODO
Cible     : datalake://raw/[source]/[entity]/{date}/
Owner     : TODO
"""

from pyworkflow_engine.models import Job, Step

from jobs.ingestion._template.client import TemplateClient
from jobs.shared.datalake import DataLake


def extract(**ctx):
    client = TemplateClient.from_env()
    data = client.fetch_data(since=ctx.get("since_date"))
    return {"raw_data": data, "count": len(data)}


def validate_raw(**ctx):
    raw = ctx["raw_data"]
    if not raw:
        return {"status": "empty", "skip_load": True}
    return {"status": "valid", "skip_load": False}


def load_to_datalake(**ctx):
    if ctx.get("skip_load"):
        return {"rows_written": 0, "skipped": True}
    dl = DataLake.from_env()
    partition = ctx.get("since_date", "latest")
    path = f"raw/TODO_SOURCE/TODO_ENTITY/{partition}/"
    rows = dl.write_json(path, ctx["raw_data"])
    return {"rows_written": rows, "path": path}


job = Job(
    name="ingestion-TODO_SOURCE-TODO_ENTITY",
    version="1.0.0",
    steps=[
        Step(name="extract", handler=extract),
        Step(name="validate_raw", handler=validate_raw, depends_on=["extract"]),
        Step(name="load_to_datalake", handler=load_to_datalake, depends_on=["validate_raw"]),
    ],
)

if __name__ == "__main__":
    from pyworkflow_engine import WorkflowEngine
    result = WorkflowEngine().run(job)
    print(f"Terminé : {result.status}")
```

---

## 8. Orchestration bout-en-bout

> Les pipelines d'orchestration vivent dans le dossier `pipelines/` à la racine
> du projet. Voir [ADR-04](./04-datalake-local-et-pipelines.md) pour le détail.

### Pipeline complète : Ingestion → Staging → Marts

```python
"""
pipelines/daily/stripe_to_dwh.py

Pipeline quotidienne complète.

1. Ingestion Stripe → Data Lake (data/datalake/raw/stripe/...)
2. Staging payments → DWH (data/warehouse/warehouse.duckdb)
3. Mart revenue → DWH
"""

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.config import WorkflowConfig

from jobs.ingestion.stripe.extract_payments import job as ingest_job
from jobs.transformation.staging.stg_payments import job as staging_job
from jobs.transformation.marts.finance.mart_revenue import job as mart_job


def run_daily_pipeline():
    engine = WorkflowEngine(config=WorkflowConfig.from_env())
    date = "2026-04-10"

    # Couche 1 — Ingestion
    ingest = engine.run(ingest_job, initial_context={"since_date": date})
    print(f"Ingestion: {ingest.status}")

    if ingest.status.value != "SUCCESS":
        print("❌ Ingestion échouée — arrêt du pipeline")
        return

    # Couche 2a — Staging
    staging = engine.run(staging_job, initial_context={"partition": date})
    print(f"Staging: {staging.status}")

    if staging.status.value != "SUCCESS":
        print("❌ Staging échoué — arrêt du pipeline")
        return

    # Couche 2b — Marts
    mart = engine.run(mart_job)
    print(f"Mart: {mart.status}")


if __name__ == "__main__":
    run_daily_pipeline()
```

### Diagramme de séquence

```
  Scheduler        Pipeline          Engine          Ingestion      data/datalake   Transformation   data/warehouse
     │                │                │                │                │                │                │
     │  cron 02h00    │                │                │                │                │                │
     │───────────────▶│                │                │                │                │                │
     │                │  engine.run    │                │                │                │                │
     │                │  (ingest_job)  │                │                │                │                │
     │                │───────────────▶│                │                │                │                │
     │                │                │  run(ingest)   │                │                │                │
     │                │                │───────────────▶│                │                │                │
     │                │                │                │  extract()     │                │                │
     │                │                │                │  ──── API ───▶ │                │                │
     │                │                │                │  ◀──── data ── │                │                │
     │                │                │                │  validate()    │                │                │
     │                │                │                │  load()        │                │                │
     │                │                │                │───────────────▶│                │                │
     │                │                │                │    write_json  │                │                │
     │                │                │  ◀─ SUCCESS ───│                │                │                │
     │                │  ◀─ SUCCESS ───│                │                │                │                │
     │                │                │                │                │                │                │
     │                │  engine.run    │                │                │                │                │
     │                │  (staging_job) │                │                │                │                │
     │                │───────────────▶│                │                │                │                │
     │                │                │  run(staging)  │                │                │                │
     │                │                │──────────────────────────────────────────────────▶│                │
     │                │                │                │                │  read_json()   │                │
     │                │                │                │                │◀───────────────│                │
     │                │                │                │                │                │  clean()       │
     │                │                │                │                │                │  upsert()      │
     │                │                │                │                │                │───────────────▶│
     │                │                │                │                │                │  quality()     │
     │                │                │  ◀─ SUCCESS ──────────────────────────────────────│                │
     │                │  ◀─ SUCCESS ───│                │                │                │                │
     │  ◀─ done ──────│                │                │                │                │                │
```

---

## 9. Checklist ajout d'une source

Lorsqu'une nouvelle source de données doit être intégrée :

- [ ] **Copier** `jobs/ingestion/_template/` → `jobs/ingestion/{source}/`
- [ ] **Implémenter** `client.py` (authentification, pagination, rate limiting)
- [ ] **Créer** un ou plusieurs `extract_{entity}.py`
- [ ] **Remplir** `config.yaml` (endpoints, mapping, limites)
- [ ] **Ajouter** les variables d'environnement dans `.env.example`
- [ ] **Ajouter** le staging correspondant dans `jobs/transformation/staging/stg_{entity}.py`
- [ ] **Écrire** les tests dans `tests/jobs/ingestion/{source}/`
- [ ] **Enregistrer** dans `manifest.yaml` (schedule, owner, tags)
- [ ] **Documenter** dans le `README.md` de la source
- [ ] **Créer ou mettre à jour** la pipeline dans `pipelines/` si le job doit être chaîné

---

## Résumé des décisions

| # | Décision | Justification |
|---|---|---|
| D-01 | Dossier `jobs/` à la racine | Séparation framework / métier |
| D-02 | 1 sous-dossier par source dans `ingestion/` | Isolation, maintenabilité |
| D-03 | Architecture Medallion (Bronze → Silver → Gold) | Standard industrie, replay possible |
| D-04 | Abstraction `DataLake` + `Warehouse` | Portabilité dev/prod |
| D-05 | DuckDB en dev, PostgreSQL en prod | Itération rapide vs. robustesse |
| D-06 | Template `_template/` pour nouvelles sources | Accélération onboarding |
| D-07 | Quality checks systématiques | Fiabilité des données |
| D-08 | Secrets via env vars uniquement | Sécurité |
| D-09 | Manifest YAML pour le scheduling | Découverte et automatisation |
| D-10 | Conventions de nommage strictes | Lisibilité à l'échelle |
| D-11 | `data/` à la racine = Data Lake local | Même niveau que `src/`, `jobs/`, gitignored |
| D-12 | `data/datalake/raw/` + `data/warehouse/` | Séparation Bronze / DWH en local |
| D-13 | `pipelines/` à la racine pour l'orchestration | Séparation job unitaire / chaînage |
| D-14 | Pipelines organisées par fréquence | Aligné sur le scheduling |

> Voir aussi [ADR-04 — Data Lake local et Pipelines](./04-datalake-local-et-pipelines.md)
> pour le détail des décisions D-11 à D-16.
