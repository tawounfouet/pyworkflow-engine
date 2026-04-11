# PyWorkflow Engine

Moteur d'orchestration de workflows Python pur — zero dépendance framework.

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
- **🎨 Double API** : Décorateurs `@step`/`@job` *(v0.5.0)* + API impérative `Job`/`Step` — cohabitation sans breaking change.
- **🔧 Pluggable** : Executors, triggers, et persistence modulaires.
- **🌐 Universal** : Fonctionne dans notebooks, scripts, Django, FastAPI, CLI.
- **⚡ Performant** : Exécution optimisée, possibilité d'exécution concurrente (`ParallelRunner`).
- **🎯 Type-safe** : Dataclasses + mypy pour une robustesse maximale.
- **🛡 Robuste** : Gestion unifiée des retries (`RetryHandler`), timeouts, et mécanisme de suspension/reprise.

## Installation

```bash
# Core seulement (zero dépendance)
pip install pyworkflow-engine

# Avec adapters spécifiques et backends
pip install pyworkflow-engine[django]      # Pour Django
pip install pyworkflow-engine[fastapi]     # Pour FastAPI
pip install pyworkflow-engine[sqlalchemy]  # Persistence via bases de données
pip install pyworkflow-engine[all]         # Tout installer
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│              pyworkflow-engine (pure Python)      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  Models  │  │  Engine  │  │   Executors  │   │
│  │(dataclass)  │  (DAG)   │  │  (pluggable) │   │
│  └──────────┘  └──────────┘  └──────────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Triggers │  │ Context  │  │ Persistence  │   │
│  │(pluggable)  │  (I/O)   │  │ (pluggable)  │   │
│  └──────────┘  └──────────┘  └──────────────┘   │
│  ┌────────────────────────────────────────────┐  │
│  │  Decorators — @step / @job  (v0.5.0)       │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
        │               │               │
   ┌────▼────┐    ┌─────▼─────┐   ┌─────▼──────┐
   │ Django  │    │  FastAPI  │   │  Notebook  │
   │ Adapter │    │  Adapter  │   │  (direct)  │
   └─────────┘    └───────────┘   └────────────┘
```

## Status

🚀 **Version 0.5.0** — API décorateurs `@step`/`@job` disponible.

Cette librairie est née de la volonté d'extraire la logique métier d'orchestration d'anciennes applications monolithiques pour fournir un package Python pur et découplé.

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les guidelines de contribution.

## License

MIT - Voir [LICENSE](LICENSE) pour les détails.
