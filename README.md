# PyWorkflow Engine

Moteur d'orchestration de workflows Python pur — zero dépendance framework.

> **Architecture hexagonale** (Ports & Adapters) depuis v0.6.0 — [ADR-006](docs/changelog/2026-04-11_adr_006_hexagonal-ports-adapters.md)

## Vision

Deux APIs cohabitent pour s'adapter à tous les styles :

### API déclarative — `@step` / `@job` *(v0.5.0+, recommandée)*

```python
from pyworkflow_engine import step, job, WorkflowEngine

@step(name="fetch", timeout=30.0)
def fetch_data(source: str = "api") -> dict:
    # Fonction pure — testable sans aucun mock
    return {"records": [1, 2, 3], "source": source}

@step(name="transform", dependencies=["fetch"])
def transform(records: list | None = None) -> dict:
    # `records` est injecté automatiquement depuis la sortie de "fetch"
    return {"transformed": [r * 10 for r in (records or [])]}

@job(name="ETL Pipeline")
def etl_pipeline():
    fetch_data()
    transform()

engine = WorkflowEngine()
result = engine.run(etl_pipeline.build(), initial_context={"source": "db"})
print(result.status)       # RunStatus.SUCCESS
print(result.output_data)  # {"transformed": [10, 20, 30]}
```

> **Injection automatique** : paramètres résolus dans l'ordre — sorties des dépendances › contexte initial › valeur par défaut › `None`.
> Les fonctions restent **testables unitairement** sans runner : `fetch_data(source="test")`.

### API impérative — `Job` / `Step` *(toujours supportée, sans breaking change)*

```python
from pyworkflow_engine import Job, Step, StepType, WorkflowEngine
from pyworkflow_engine.config import WorkflowConfig, EngineConfig

def fetch_data(context):
    return {"records": [1, 2, 3], "count": 3}

def transform(context):
    records = context.get_step_output("fetch", {}).get("records", [])
    return {"transformed": [r * 10 for r in records]}

etl = Job(
    name="ETL Pipeline",
    steps=[
        Step(name="fetch", step_type=StepType.FUNCTION, handler=fetch_data),
        Step(name="transform", step_type=StepType.FUNCTION, handler=transform, dependencies=["fetch"]),
    ],
)

cfg = WorkflowConfig(engine=EngineConfig(parallel=True, max_workers=2))
engine = WorkflowEngine(config=cfg)
result = engine.run(etl, initial_context={"source": "api"})
```

## Caractéristiques

- **🚀 Zero dépendance** : Le core fonctionne avec la stdlib uniquement.
- **🏛️ Architecture hexagonale** : Ports (interfaces) & Adapters (implémentations) — séparation claire des contrats et des implémentations *(v0.6.0)*.
- **🎨 Double API** : Décorateurs `@step`/`@job` *(v0.5.0)* + API impérative `Job`/`Step` — cohabitation sans breaking change.
- **🔧 Pluggable** : Executors, triggers, et persistence modulaires via le système d'adapters.
- **🌐 Universal** : Fonctionne dans notebooks, scripts, Django, FastAPI, CLI.
- **⚡ Performant** : Exécution optimisée, possibilité d'exécution concurrente (`ParallelRunner`).
- **🎯 Type-safe** : Dataclasses + mypy pour une robustesse maximale.
- **🛡 Robuste** : Gestion unifiée des retries (`RetryHandler`), timeouts, et mécanisme de suspension/reprise.

## Installation

```bash
# Core seulement (zero dépendance)
pip install pyworkflow-engine

# Avec adapters spécifiques et backends
pip install pyworkflow-engine[celery]      # Exécution distribuée (Celery + Redis)
pip install pyworkflow-engine[sqlalchemy]  # Persistence via bases de données
pip install pyworkflow-engine[snowflake]   # Intégration Snowflake
pip install pyworkflow-engine[django]      # Pour Django
pip install pyworkflow-engine[fastapi]     # Pour FastAPI
pip install pyworkflow-engine[structlog]   # Logging structuré
pip install pyworkflow-engine[all]         # Tout installer
```

## Architecture (v0.6.0 — Hexagonal)

```
┌─────────────────────────────────────────────────────────────┐
│                  pyworkflow-engine (pure Python)             │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  facade.py — WorkflowEngine                           │  │
│  │  (assemble engine + ports + adapters)                  │  │
│  └──────────┬──────────────────────┬─────────────────────┘  │
│             │                      │                        │
│             ▼                      ▼                        │
│  ┌──────────────────┐   ┌──────────────────────────────┐   │
│  │  engine/          │   │  adapters/                    │   │
│  │  models/          │   │  ├── executors/  (local,      │   │
│  │  decorators/      │   │  │   thread, process, async)  │   │
│  │  config/          │   │  ├── persistence/ (memory,    │   │
│  │  (domaine)        │   │  │   json, sqlite, sqlalchemy)│   │
│  └────────┬──────────┘   │  ├── triggers/ (manual, cron) │   │
│           │              │  ├── celery/   (v0.7.0)       │   │
│           │              │  ├── snowflake/               │   │
│           ▼              │  └── structlog/               │   │
│  ┌────────────────────┐  └──────────┬────────────────────┘  │
│  │  ports/            │◄────────────┘                       │
│  │  (interfaces ABC)  │  Règle : adapters/ implémente       │
│  │  executor.py       │          ports/, engine/ dépend     │
│  │  persistence.py    │          de ports/ uniquement       │
│  │  trigger.py        │                                     │
│  └────────────────────┘                                     │
└─────────────────────────────────────────────────────────────┘
        │               │               │
   ┌────▼────┐    ┌─────▼─────┐   ┌─────▼──────┐
   │ Django  │    │  FastAPI  │   │  Notebook  │
   │ Adapter │    │  Adapter  │   │  (direct)  │
   └─────────┘    └───────────┘   └────────────┘
```

## Status

🚀 **Version 0.6.0** — Architecture hexagonale (Ports & Adapters) · 535 tests · 84 % couverture.

| Version | Milestone |
|---------|-----------|
| v0.3.0 | Refactoring modulaire (God Object → composants spécialisés) |
| v0.4.0 | Triggers, ParallelRunner, documentation ADR |
| v0.5.0 | API décorateurs `@step`/`@job` |
| **v0.6.0** | **Architecture hexagonale — `ports/` + `adapters/`** |
| v0.7.0 | Intégration Celery (exécution distribuée) — [ADR-007](docs/changelog/2026-04-11_adr_007_celery-adapter-integration.md) |

Cette librairie est née de la volonté d'extraire la logique métier d'orchestration d'anciennes applications monolithiques pour fournir un package Python pur et découplé.

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les guidelines de contribution.

## License

MIT - Voir [LICENSE](LICENSE) pour les détails.
