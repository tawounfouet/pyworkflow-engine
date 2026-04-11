# PyWorkflow Engine

Moteur d'orchestration de workflows Python pur — zero dépendance framework.

## Vision

Transformer les workflows complexes en code Python simple et portable :

```python
from pyworkflow_engine import Job, Step, StepType, WorkflowEngine
from pyworkflow_engine.config import WorkflowConfig, EngineConfig

def fetch_data(context):
    # Accès au contexte initial ou intermédiaire
    return {"records": [1, 2, 3], "count": 3}

def transform(context):
    # Récupération des données du step précédent
    records = context.get_step_output("fetch", {}).get("records", [])
    return {"transformed": [r * 10 for r in records]}

# Définir le workflow
etl = Job(
    name="ETL Pipeline", 
    steps=[
        Step(
            name="fetch", 
            step_type=StepType.FUNCTION, 
            handler=fetch_data
        ),
        Step(
            name="transform", 
            step_type=StepType.FUNCTION, 
            handler=transform, 
            dependencies=["fetch"]
        ),
    ]
)

# Configuration de l'exécution (Optionnelle)
cfg = WorkflowConfig(engine=EngineConfig(parallel=True, max_workers=2))

# Exécuter
engine = WorkflowEngine(config=cfg)
result = engine.run(etl, initial_context={"source": "api"})

print(result.status)  # RunStatus.SUCCESS
print(result.output_data)
```

## Caractéristiques

- **🚀 Zero dépendance** : Le core fonctionne avec la stdlib uniquement.
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
┌─────────────────────────────────────────────────┐
│              pyworkflow-engine (pure Python)     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Models  │  │  Engine  │  │   Executors  │  │
│  │(dataclass)  │  (DAG)   │  │  (pluggable) │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Triggers │  │ Context  │  │ Persistence  │  │
│  │(pluggable)  │  (I/O)   │  │ (pluggable)  │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────┘
        │               │               │
   ┌────▼────┐    ┌─────▼─────┐   ┌─────▼──────┐
   │ Django  │    │  FastAPI  │   │  Notebook  │
   │ Adapter │    │  Adapter  │   │  (direct)  │
   └─────────┘    └───────────┘   └────────────┘
```

## Status

🚧 **En développement actif** - Version 0.4.0

Cette librairie est née de la volonté d'extraire la logique métier d'orchestration d'anciennes applications monolithiques pour fournir un package Python pur et découplé.

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les guidelines de contribution.

## License

MIT - Voir [LICENSE](LICENSE) pour les détails.
