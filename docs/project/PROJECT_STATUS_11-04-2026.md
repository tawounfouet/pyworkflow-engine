# PyWorkflow Engine — Statut du projet

> Dernière mise à jour : 11 avril 2026 · Version courante : **v0.4.0**

---

## 🏗️ Architecture actuelle (v0.4.0)

```
src/pyworkflow_engine/
├── __init__.py             # API publique (exports)
├── facade.py               # WorkflowEngine — façade unique
├── exceptions.py           # Hiérarchie d'exceptions
├── py.typed                # Marqueur PEP 561
├── engine/                 # Cœur d'exécution
│   ├── runner.py           # WorkflowRunner (séquentiel)
│   ├── parallel_runner.py  # ParallelRunner (concurrent.futures)
│   ├── dag.py              # DAGResolver
│   ├── context.py          # WorkflowContext
│   ├── retry.py            # RetryHandler
│   └── suspension.py       # SuspensionManager
├── executors/              # Stratégies d'exécution
│   ├── base.py             # BaseExecutor, ExecutorRegistry
│   ├── local.py            # LocalExecutor
│   ├── thread_pool.py      # ThreadPoolStepExecutor
│   ├── process_pool.py     # ProcessPoolStepExecutor
│   ├── async_exec.py       # AsyncStepExecutor
│   └── retryable.py        # RetryableExecutor
├── models/                 # Modèles de données
│   ├── enums.py            # RunStatus, StepType, ExecutorType
│   ├── job.py              # Job
│   ├── step.py             # Step
│   └── run.py              # JobRun, StepRun
├── triggers/               # Déclencheurs — nouveau v0.4.0
│   ├── base.py             # BaseTrigger, TriggerState
│   ├── manual.py           # ManualTrigger
│   └── schedule.py         # ScheduleTrigger, CronExpression
├── persistence/            # Backends de persistence
│   ├── base.py             # BasePersistence (ABC)
│   ├── memory.py           # InMemoryPersistence
│   ├── json_file.py        # JSONFilePersistence
│   ├── sqlite.py           # SQLitePersistence
│   └── sqlalchemy.py       # SQLAlchemyPersistence
├── logging/                # Système de logging structuré
└── adapters/               # Intégrations optionnelles (celery, snowflake, structlog)
```

**Supprimé en v0.4.0** : `core/` (God Object monolithique, ~2 600 lignes)

---

## ✅ Fonctionnalités livrées

### Core engine
- [x] Exécution séquentielle (`WorkflowRunner`)
- [x] Exécution parallèle (`ParallelRunner` — `concurrent.futures`)
- [x] Résolution DAG avec détection de cycles (`DAGResolver`)
- [x] Contexte d'exécution avec propagation des sorties (`WorkflowContext`)
- [x] Retry avec back-off configurable (`RetryHandler`)
- [x] Suspension / reprise de workflows (`SuspensionManager`)

### Triggers *(nouveau v0.4.0)*
- [x] `ManualTrigger` — déclenchement explicite par code (API, bouton, test)
- [x] `ScheduleTrigger` — déclenchement par cron, thread d'arrière-plan (stdlib pure)
- [x] `CronExpression` — parser cron 5 champs, `matches()`, zéro dépendance externe
- [x] Callbacks `on_run_complete` / `on_run_error`
- [x] `initial_context_factory` pour injecter un contexte dynamique à chaque déclenchement

### Executors
- [x] `LocalExecutor` (synchrone, zéro overhead)
- [x] `ThreadPoolStepExecutor`
- [x] `ProcessPoolStepExecutor`
- [x] `AsyncStepExecutor`
- [x] `RetryableExecutor`
- [x] `ExecutorRegistry` (lookup par nom)

### Persistence
- [x] `InMemoryPersistence` ✅
- [x] `JSONFilePersistence` ✅
- [x] `SQLitePersistence` ✅
- [x] `SQLAlchemyPersistence` ✅
- [x] Checkpoints step-by-step dans `run_with_persistence()`
- [x] `cleanup_old_runs(older_than, dry_run=False)` — contrat LSP aligné sur tous les backends

### Qualité & tests
- [x] **338 passed**, 15 skipped, 0 failed, 0 errors
- [x] Couverture : ~81% (cible 85%)
- [x] Tests d'intégration : `test_persistence_roundtrip.py`, `test_parallel_runner.py`
- [x] Ruff (lint) + MyPy (type checking)
- [x] Règle ruff `TID252` configurée (`ban-relative-imports = "parents"`)

---

## 🚧 En cours — ADR-004

| Tâche | Statut |
|---|---|
| Imports absolus — migration `src/` (~20 fichiers, `ruff --select TID252 --fix`) | ⬜ Planifié |
| Module `config/` — `WorkflowConfig`, `EngineConfig`, `ExecutorConfig`, `LoggingConfig` | ⬜ Planifié |
| `WorkflowEngine(config=WorkflowConfig(…))` avec rétrocompatibilité | ⬜ Planifié |

> Voir [ADR-004](docs/changelog/2026-04-11-import-style-and-config-module.md) pour le détail complet.

---

## 📋 Journal des décisions (ADR)

| ADR | Titre | Statut |
|-----|-------|--------|
| [ADR-001](docs/changelog/2026-04-10-naming-decision.md) | Nommage du package | ✅ Implémenté |
| [ADR-002](docs/changelog/2026-04-10-architecture-refactoring-proposal.md) | God Object → couches modulaires | ✅ Implémenté (v0.3 + v0.4) |
| [ADR-003](docs/changelog/2026-04-10-architecture-critique-integration.md) | Intégration de l'analyse critique | ✅ Implémenté |
| [ADR-004](docs/changelog/2026-04-11-import-style-and-config-module.md) | Imports absolus + module `config/` | 🚧 En cours |

---

## 📦 Installation

```bash
# Core (zéro dépendance)
pip install pyworkflow-engine

# Avec persistence SQL
pip install pyworkflow-engine[sqlalchemy]

# Avec structlog
pip install pyworkflow-engine[structlog]

# Tout
pip install pyworkflow-engine[all]
```

## 🚀 Usage rapide (v0.4.0)

```python
from pyworkflow_engine import (
    WorkflowEngine, Job, Step, StepType,
    ManualTrigger, ScheduleTrigger, CronExpression,
)

def fetch(context): return {"records": 42}
def process(context):
    return {"total": context.get_step_output("fetch")["records"]}

job = Job(name="pipeline", steps=[
    Step(name="fetch",   step_type=StepType.FUNCTION, handler=fetch),
    Step(name="process", step_type=StepType.FUNCTION, handler=process,
         dependencies=["fetch"]),
])

# Exécution simple
engine = WorkflowEngine()
result = engine.run(job)  # JobRun(status=SUCCESS)

# Exécution parallèle
engine = WorkflowEngine(parallel=True, max_workers=4)

# Trigger planifié (cron, thread d'arrière-plan)
trigger = ScheduleTrigger(engine=engine, job=job, cron="0 9 * * 1-5")
trigger.start()
```

---

*Version : v0.4.0 · 11 avril 2026*
