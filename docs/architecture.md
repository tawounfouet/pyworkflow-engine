# Architecture de `pyworkflow-engine`

> **Version documentée :** 0.3.0  
> **Auteur :** Thomas AWOUNFOUET  
> **Licence :** MIT  
> **Python :** ≥ 3.11

---

## 1. Vue d'ensemble

`pyworkflow-engine` est un moteur d'orchestration de workflows **Python pur**, conçu selon le principe **library-first** : le cœur du package n'a aucune dépendance externe et fonctionne avec la seule stdlib Python.

L'objectif est de permettre la définition, l'exécution et la gestion de workflows complexes (pipelines ETL, tâches humaines, sous-workflows imbriqués…) dans n'importe quel environnement Python — scripts, notebooks, Django, FastAPI, Celery, etc.

---

## 2. Principe directeur : Séparation Design-Time / Runtime

Le projet repose sur une distinction fondamentale entre deux phases :

| Phase            | Modèle        | Mutabilité    | Rôle                                      |
|------------------|---------------|---------------|-------------------------------------------|
| **Design-time**  | `Job`, `Step` | `frozen=True` | Définir statiquement la structure du workflow |
| **Runtime**      | `JobRun`, `StepRun`, `StepLog` | mutable | Suivre l'état d'une exécution en cours |

Cette séparation claire garantit que les définitions de workflows sont immuables, sérialisables, et réutilisables à travers de multiples exécutions.

---

## 3. Structure des répertoires

```
pyworkflow-engine/
├── src/
│   └── pyworkflow_engine/          # Package principal
│       ├── __init__.py             # API publique (lazy imports PEP 562)
│       ├── facade.py               # WorkflowEngine — façade principale (~400 LOC)
│       ├── exceptions.py           # Hiérarchie complète d'exceptions
│       ├── py.typed                # Marker PEP 561
│       │
│       ├── models/                 # 🔵 COUCHE DOMAINE — ce qui EST
│       │   ├── __init__.py         #   Re-exports + thin wrappers de sérialisation
│       │   ├── enums.py            #   RunStatus, StepType, ExecutorType, Priority, TriggerType
│       │   ├── step.py             #   Step, SubJob (frozen dataclasses + to_dict/from_dict)
│       │   ├── job.py              #   Job (frozen dataclass + to_dict/from_dict + graph helpers)
│       │   └── run.py              #   StepLog, StepRun, JobRun (mutable + to_dict/from_dict)
│       │
│       ├── engine/                 # 🟢 COUCHE ORCHESTRATION — ce qui FAIT
│       │   ├── __init__.py
│       │   ├── runner.py           #   WorkflowRunner — exécution pure des steps
│       │   ├── dag.py              #   DAGResolver — tri topologique, détection de cycles
│       │   ├── context.py          #   WorkflowContext — passage I/O entre steps
│       │   ├── retry.py            #   RetryHandler — retry unifié
│       │   └── suspension.py       #   SuspensionManager — persistence-aware
│       │
│       ├── executors/              # 🟠 COUCHE EXÉCUTION — COMMENT exécuter
│       │   ├── __init__.py
│       │   ├── base.py             #   BaseExecutor (ABC), ExecutorRegistry
│       │   ├── local.py            #   LocalExecutor — synchrone même processus
│       │   ├── thread_pool.py      #   ThreadPoolStepExecutor, ProcessPoolStepExecutor
│       │   ├── async_exec.py       #   AsyncStepExecutor
│       │   └── retryable.py        #   RetryableExecutor
│       │
│       ├── persistence/            # 🔴 COUCHE STOCKAGE — OÙ persister
│       │   ├── __init__.py
│       │   ├── base.py             #   BaseStorage (ABC)
│       │   ├── memory.py           #   InMemoryStorage
│       │   ├── json_file.py        #   JSONFileStorage
│       │   ├── sqlite.py           #   SQLiteStorage
│       │   └── sqlalchemy.py       #   SQLAlchemyStorage (opt: pip install [sqlalchemy])
│       │
│       ├── logging/                # 🟣 COUCHE OBSERVABILITÉ
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── formatters.py
│       │   ├── handlers.py
│       │   ├── logger.py
│       │   └── utils.py
│       │
│       └── adapters/               # 🔘 INTÉGRATIONS EXTERNES (optionnelles)
│           ├── celery/
│           ├── snowflake/
│           ├── sqlalchemy/
│           └── structlog/
├── tests/
│   ├── unit/                       # Tests unitaires
│   └── integration/                # Tests d'intégration
├── examples/                       # Exemples d'utilisation
├── docs/                           # Documentation
├── pyproject.toml
└── uv.lock
```

> **Note :** Le répertoire `core/` a été supprimé en v0.3.0. Les imports
> `from pyworkflow_engine.core import ...` ne fonctionnent plus.
> L'API publique `from pyworkflow_engine import ...` reste inchangée.

---

## 4. Architecture en couches

```
┌──────────────────────────────────────────────────────────────────────┐
│                       API Publique (__init__.py)                     │
│          Job · Step · WorkflowEngine · RunStatus · ...               │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ (lazy imports PEP 562)
┌──────────────────────────── ▼ ────────────────────────────────────── ┐
│                         facade.py  (WorkflowEngine)                  │
│  Compose : WorkflowRunner · RetryHandler · SuspensionManager         │
└──────────┬──────────────────┬─────────────────────┬──────────────────┘
           │                  │                     │
    ┌──────▼──────┐   ┌───────▼────────┐   ┌───────▼──────────────────┐
    │  models/    │   │   engine/      │   │   executors/             │
    │  step.py    │   │   runner.py    │   │   local.py               │
    │  job.py     │   │   dag.py       │   │   thread_pool.py         │
    │  run.py     │   │   context.py   │   │   async_exec.py          │
    │  enums.py   │   │   retry.py     │   │   retryable.py           │
    └─────────────┘   │   suspension.py│   └──────────────────────────┘
                      └────────────────┘
          │                    │                      │
┌─────────▼─────┐   ┌──────────▼──────┐   ┌──────────▼───────────────┐
│   logging/    │   │  persistence/   │   │   adapters/ (opt-in)      │
│  stdlib only  │   │  memory / json  │   │  celery · snowflake       │
│  JSON / Queue │   │  sqlite / SA    │   │  sqlalchemy · structlog   │
└───────────────┘   └─────────────────┘   └──────────────────────────┘
```

---

## 5. Composants

### 5.1 Modèles Design-Time (`models/step.py`, `models/job.py`)

Ces modèles sont des **dataclasses `frozen=True`** — immuables et sérialisables.

#### `Step`
Unité atomique d'exécution. Un step peut être :

| `StepType`       | Description                              |
|------------------|------------------------------------------|
| `FUNCTION`       | Exécute une fonction Python callable     |
| `SUBPROCESS`     | Lance un processus système               |
| `HTTP_REQUEST`   | Effectue une requête HTTP                |
| `SQL_QUERY`      | Exécute une requête SQL                  |
| `HUMAN_TASK`     | Tâche nécessitant une intervention humaine |
| `EXTERNAL_TASK`  | Tâche déléguée à un système externe      |
| `SUB_WORKFLOW`   | Lance un sous-workflow imbriqué          |

Attributs clés de `Step` :
- `name` : identifiant unique dans le job
- `callable` : fonction Python à invoquer (pour `StepType.FUNCTION`)
- `dependencies` : liste des noms de steps dépendants
- `timeout` : `timedelta` optionnel
- `retry_count` / `retry_delay` : logique de retry intégrée
- `condition` : callable `(Dict) → bool` pour exécution conditionnelle
- `executor_type` : `ExecutorType` déterminant le routing de l'executor
- `executor_name` : nom d'un executor enregistré dans `ExecutorRegistry`

Chaque `Step` expose `to_dict()` / `from_dict(cls, data)` pour la sérialisation.

#### `Job`
Contient la définition complète d'un workflow :
- Liste de `Step`s composant le DAG
- Liste de `SubJob`s pour les sous-workflows
- Configuration des `TriggerType`s acceptés
- `timeout` global, `priority`, `tags`, `version`
- Validation à l'initialisation : unicité des noms, dépendances existantes

---

### 5.2 Modèles Runtime (`models/run.py`)

Ces modèles sont des **dataclasses mutables** mises à jour tout au long de l'exécution.

#### `StepRun`
Représente l'exécution d'un step. États supportés via des méthodes dédiées :
- `start_execution()` → `RUNNING`
- `complete_success(output)` → `SUCCESS`
- `complete_failure(error)` → `FAILED`
- `suspend(reason)` → `SUSPENDED`
- `mark_timeout()` → `TIMEOUT`

Chaque transition calcule automatiquement `duration_ms` et enregistre un `StepLog`.

#### `JobRun`
Agrège l'état global du workflow avec la liste de ses `StepRun`s.

---

### 5.3 Enums (`models/enums.py`)

| Enum           | Valeurs principales                                                    |
|----------------|------------------------------------------------------------------------|
| `RunStatus`    | `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `SUSPENDED`, `WAITING_HUMAN`, `WAITING_EXTERNAL`, `CANCELLED`, `TIMEOUT` |
| `StepType`     | `FUNCTION`, `SUBPROCESS`, `HTTP_REQUEST`, `SQL_QUERY`, `HUMAN_TASK`, `EXTERNAL_TASK`, `SUB_WORKFLOW` |
| `ExecutorType` | `LOCAL`, `THREAD`, `PROCESS`, `ASYNC`, `CUSTOM`, `CELERY`, `KUBERNETES`, `HUMAN`, `EXTERNAL` |
| `TriggerType`  | `MANUAL`, `SCHEDULE`, `SIGNAL`, `WEBHOOK`, `FILE_WATCHER`             |
| `Priority`     | `LOW` (1), `NORMAL` (5), `HIGH` (10), `CRITICAL` (20)                 |

---

### 5.4 DAGResolver (`engine/dag.py`)

| Méthode                     | Description                                                |
|-----------------------------|------------------------------------------------------------|
| `get_execution_order()`     | Tri topologique via **algorithme de Kahn**                 |
| `get_parallel_groups()`     | Groupes de steps pouvant s'exécuter en parallèle           |
| `get_critical_path()`       | Chemin le plus long                                        |
| `get_entry_points()`        | Steps sans dépendances                                     |
| `get_exit_points()`         | Steps sans dépendants                                      |
| `get_graph_stats()`         | Statistiques : total steps, max parallèle, chemin critique |

---

### 5.5 WorkflowEngine (`facade.py`)

Façade principale — compose `WorkflowRunner`, `RetryHandler` et `SuspensionManager`.

```python
engine = WorkflowEngine(
    default_executor=None,        # Executor par défaut (function step)
    step_executors={...},         # Mapping StepType → executor personnalisé
    executor_registry=None,       # Registry des executors nommés
    persistence=None,             # Backend de persistance (optionnel)
)
```

**Contrat `run()` vs `run_with_storage()` :**

| Méthode                     | Persistence | Checkpoints        | Usage                          |
|-----------------------------|:-----------:|:------------------:|--------------------------------|
| `run(job)`                  | ❌ Aucune   | —                  | Exécution pure, tests, scripts |
| `run_with_storage(job)` | ✅ Backend  | Initial + par step + final | Production                |

**Méthodes publiques :**

| Méthode                  | Description                                          |
|--------------------------|------------------------------------------------------|
| `run(job, ...)`          | Exécution pure, sans side-effect de persistence      |
| `run_with_storage()` | Exécution + sauvegarde avec checkpoints intermédiaires |
| `resume(run_id, ...)`    | Reprend un workflow suspendu                         |
| `cancel(run_id)`         | Annule un workflow suspendu                          |
| `validate_job(job)`      | Valide un job sans l'exécuter                        |
| `get_execution_plan(job)`| Génère un plan d'exécution détaillé                  |
| `register_executor(...)` | Enregistre un executor nommé dans le registry        |

---

### 5.6 WorkflowRunner (`engine/runner.py`)

Responsabilité unique : orchestrer l'appel aux executors dans l'ordre topologique. Pas de retry, pas de persistence, pas de suspension.

**Routing `ExecutorType` (`_resolve_executor`) :**

| `executor_type`  | Executor utilisé              |
|------------------|-------------------------------|
| `LOCAL`          | `_execute_function_step` (direct) |
| `THREAD`         | `ThreadPoolStepExecutor`      |
| `PROCESS`        | `ProcessPoolStepExecutor`     |
| `ASYNC`          | `AsyncStepExecutor`           |
| `CUSTOM`         | `ExecutorRegistry` lookup via `step.executor_name` |
| Autres           | Passthrough (adapters externes) |

Priorité : `executor_name` (registry) > `executor_type` > `step_type` mapping > default.

---

### 5.7 Executors (`executors/`)

Tous héritent de `BaseExecutor(ABC)`.

| Executor                  | Cas d'usage                                   |
|---------------------------|-----------------------------------------------|
| `LocalExecutor`           | Synchrone même processus, zero overhead       |
| `ThreadPoolStepExecutor`  | I/O-bound : réseau, fichiers                  |
| `ProcessPoolStepExecutor` | CPU-bound (fonctions picklables)              |
| `AsyncStepExecutor`       | Fonctions `async/await`                       |
| `RetryableExecutor`       | Decorator : retry + backoff exponentiel + jitter |

`ExecutorRegistry` : registre nommé (`register`, `get`, `shutdown_all`).

---

### 5.8 Système d'exceptions (`exceptions.py`)

```
WorkflowError (base)
├── WorkflowValidationError
│   └── DAGValidationError           ← cycles, dépendances manquantes
├── WorkflowExecutionError
│   ├── StepExecutionError           ← échec d'un step spécifique
│   ├── WorkflowFailed               ← échec complet du workflow
│   ├── WorkflowTimeoutError         ← dépassement de timeout
│   └── ExecutorError                ← échec de l'executor
├── WorkflowSuspended                ← mécanisme de suspension (flow control)
│   ├── WorkflowSuspendedHuman       ← attente d'une approbation humaine
│   └── WorkflowSuspendedExternal    ← attente d'un système externe
├── WorkflowCancelled                ← workflow annulé
├── StorageError                 ← erreur backend de persistance
└── ContextError                     ← accès invalide au contexte
```

---

## 6. Système de Logging (`logging/`)

Conforme à **PEP 282** :

- **NullHandler par défaut** → silencieux sans configuration explicite
- **Namespace hiérarchique** : `pyworkflow_engine.engine`, `pyworkflow_engine.persistence.sqlite`…
- **`configure_logging(LoggingConfig)`** : helper optionnel

`LoggingConfig` (dataclass `frozen`) expose :
- `level`, `json_output`, `log_file`, `enable_queue`, `extra_fields`

Utilitaires : `logged_operation` (context manager), `StepLogBridge` (handler → `StepRun.add_log`), `LoggingConfigBuilder` (builder fluide).

> Intégration `structlog` disponible via `adapters/structlog/`.

---

## 7. Persistance (`persistence/`)

Interface `BaseStorage(ABC)` :

| Méthode                           | Description                              |
|-----------------------------------|------------------------------------------|
| `save_job(job)`                   | Sauvegarde une définition de job         |
| `get_job(job_name)`               | Récupère une définition de job           |
| `save_job_run(job_run)`           | Sauvegarde un état d'exécution           |
| `get_job_run(run_id)`             | Récupère un état d'exécution             |
| `list_job_runs(...)`              | Filtre par job, statut, date             |
| `cleanup_old_runs(dt, dry_run)`   | Nettoie les vieux runs (dry_run=True pour simuler) |
| `transaction()`                   | Contexte manager transactionnel          |

**Backends disponibles :**

| Backend                | Dépendance      | Usage recommandé                        |
|------------------------|-----------------|-----------------------------------------|
| `InMemoryStorage`  | aucune          | Tests, développement, sessions courtes  |
| `JSONFileStorage`  | aucune          | Workflows locaux, configuration simple  |
| `SQLiteStorage`    | aucune (stdlib) | Déploiements mono-nœud                  |
| `SQLAlchemyStorage`| `sqlalchemy`    | Production, PostgreSQL, MySQL…          |

---

## 8. API Publique et Lazy Imports

Le `__init__.py` utilise les **lazy imports PEP 562** (`__getattr__` module-level).

```python
# Design-time
from pyworkflow_engine import Job, Step, SubJob

# Runtime
from pyworkflow_engine import JobRun, StepRun, StepLog

# Enums
from pyworkflow_engine import TriggerType, StepType, ExecutorType, RunStatus

# Engine & Context
from pyworkflow_engine import WorkflowEngine, WorkflowContext

# Exceptions
from pyworkflow_engine import WorkflowError, WorkflowSuspended, WorkflowFailed
from pyworkflow_engine import StepExecutionError, DAGValidationError

# Executors
from pyworkflow_engine import (
    LocalExecutor, ExecutorRegistry,
    ThreadPoolStepExecutor, ProcessPoolStepExecutor,
    AsyncStepExecutor, RetryableExecutor,
)

# Persistence
from pyworkflow_engine import InMemoryStorage, BaseStorage
```

---

## 9. Exemple minimal d'utilisation

```python
from pyworkflow_engine import Job, Step, WorkflowEngine, StepType, RunStatus

def extract(context):
    return {"records": [1, 2, 3]}

def transform(context):
    records = context.get_step_output("extract")["records"]
    return {"transformed": [r * 2 for r in records]}

def load(context):
    data = context.get_step_output("transform")["transformed"]
    print(f"Loaded {len(data)} records")
    return {"loaded": len(data)}

job = Job(
    name="etl-pipeline",
    steps=[
        Step(name="extract", step_type=StepType.FUNCTION, callable=extract),
        Step(name="transform", step_type=StepType.FUNCTION, callable=transform,
             dependencies=["extract"]),
        Step(name="load", step_type=StepType.FUNCTION, callable=load,
             dependencies=["transform"]),
    ]
)

engine = WorkflowEngine()
job_run = engine.run(job)
assert job_run.status == RunStatus.SUCCESS
```

---

## 10. Décisions d'architecture

| ID  | Décision                                | Statut         |
|-----|-----------------------------------------|----------------|
| D1  | Sérialisation intégrée aux classes (`to_dict`/`from_dict`) | ✅ Implémentée |
| D2  | Exécution séquentielle v0.3.0, parallèle en v0.4 | ✅ Assumée |
| D3  | Engine stateless — état dans la persistence | ✅ Implémentée |
| D4  | Suppression totale de `core/` (rupture nette) | ✅ Implémentée |
| D5  | `step.callable` → `step.handler` reporté en v0.4 (32 callsites, breaking) | ⏳ Différé |

---

## 11. Statut du projet (v0.3.0)

| Composant            | Statut                    |
|----------------------|---------------------------|
| Models (step, job, run, enums) | ✅ Stable       |
| Engine (facade, runner, retry, suspension, DAG, context) | ✅ Stable |
| Executors (local, thread_pool, async, retryable) | ✅ Stable |
| ExecutorType routing | ✅ Implémenté (v0.3.0)    |
| Persistence (memory, json_file, sqlite, sqlalchemy) | ✅ Stable |
| Logging (formatters, handlers, logger, utils) | ✅ Stable |
| Integration tests    | ✅ Ajoutés                |
| `core/` supprimé     | ✅ Rupture nette assumée  |

> **Version actuelle :** 0.3.0

---

## 12. Toolchain

| Outil          | Rôle                                         |
|----------------|----------------------------------------------|
| `hatchling`    | Build backend (wheel, sdist)                 |
| `uv`           | Gestionnaire de dépendances et environnements |
| `pytest`       | Framework de tests (unit + integration)       |
| `pytest-cov`   | Couverture de code (HTML + XML)              |
| `ruff`         | Linter + formatter (cible Python 3.11)       |
| `mypy`         | Vérification de types                        |
