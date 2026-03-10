# IAS Workflow Engine

Moteur d'orchestration de workflows Python pur — zero dépendance framework.

## Vision

Transformer les workflows complexes en code Python simple et portable :

```python
from ias_workflow_engine import Job, Step, WorkflowEngine

def fetch_data(source: str = "", **kw):
    return {"records": [1, 2, 3], "count": 3}

def transform(records: list = None, **kw):
    return {"transformed": [r * 10 for r in (records or [])]}

# Définir le workflow
etl = Job(name="ETL Pipeline", steps=[
    Step(id="fetch", name="Fetch", callable=fetch_data),
    Step(id="transform", name="Transform", callable=transform, depends_on=["fetch"]),
])

# Exécuter
engine = WorkflowEngine()
result = engine.run(etl, context={"source": "api"})
print(result.status)  # RunStatus.SUCCESS
```

## Caractéristiques

- **🚀 Zero dépendance** : Le core fonctionne avec la stdlib uniquement
- **🔧 Pluggable** : Executors, triggers, et persistence modulaires  
- **🌐 Universal** : Fonctionne dans notebooks, scripts, Django, FastAPI, CLI
- **⚡ Performant** : Tests < 2s, exécution optimisée
- **🎯 Type-safe** : Dataclasses + mypy pour une robustesse maximale

## Installation

```bash
# Core seulement (zero dépendance)
pip install ias-workflow-engine

# Avec adapters spécifiques
pip install ias-workflow-engine[django]    # Pour Django
pip install ias-workflow-engine[fastapi]   # Pour FastAPI  
pip install ias-workflow-engine[all]       # Tout installer
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│              workflow-engine (pure Python)       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Models   │  │  Engine  │  │  Executors   │  │
│  │(dataclass)│  │  (DAG)   │  │ (pluggable)  │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Triggers │  │ Context  │  │ Persistence  │  │
│  │(pluggable)│  │ (I/O)    │  │ (pluggable)  │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────┘
        │               │               │
   ┌────▼────┐    ┌─────▼─────┐   ┌─────▼──────┐
   │ Django  │    │  FastAPI  │   │  Notebook  │
   │ Adapter │    │  Adapter  │   │  (direct)  │
   └─────────┘    └───────────┘   └────────────┘
```

## Status

🚧 **En développement actif** - Version 0.1.0-alpha

Cette librairie est en cours de développement dans le cadre de la migration de l'application Django `django-workflows` vers un package Python pur.

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les guidelines de contribution.

## License

MIT - Voir [LICENSE](LICENSE) pour les détails.
