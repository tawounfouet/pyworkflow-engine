# Migration vers un Package Python Pur : Analyse & Recommandations

**Date**: 10 mars 2026  
**Status**: Recommandation approuvée  
**Stratégie**: "Library-first, Framework-second"  

---

## 🎯 Objectif de la Migration

Transformer l'application Django `django-workflows` existante en un **package Python pur** (`pyworkflow-engine`) utilisable dans n'importe quel environnement : scripts, notebooks, CLI, GUI, frameworks web (Django, FastAPI, Streamlit), etc.

### Vision

```
┌─────────────────────────────────────────────────┐
│              workflow-engine (pure Python)       │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Models   │  │  Engine  │  │  Executors   │  │
│  │(dataclass/│  │  (DAG    │  │  (base,sync, │  │
│  │ pydantic) │  │  resolve │  │  async,thread│  │
│  │          │  │  +run)   │  │  human,agent)│  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Triggers │  │  Context │  │  Persistence │  │
│  │(base,man,│  │  (I/O    │  │  (base,mem,  │  │
│  │ api,cron,│  │  passing) │  │  json,sqlite)│  │
│  │ signal)  │  │          │  │              │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────┘
        │               │               │
   ┌────▼────┐    ┌─────▼─────┐   ┌─────▼──────┐
   │ Django  │    │  FastAPI  │   │  Notebook  │
   │ Adapter │    │  Adapter  │   │  (direct)  │
   │         │    │           │   │            │
   │-ORM     │    │-Endpoints │   │-In-memory  │
   │-Admin   │    │-WebSocket │   │-Sync exec  │
   │-Signals │    │-Background│   │-Display    │
   │-Celery  │    │           │   │            │
   └─────────┘    └───────────┘   └────────────┘
```

---

## 📊 Analyse Comparative

### Architecture Django Existante

#### ✅ Ce qui est bien conçu

| Aspect | Détail |
|---|---|
| **Séparation Design-Time / Runtime** | Excellente. `Job`/`Step` (définition) vs `JobRun`/`StepRun`/`StepLog` (exécution) |
| **Registres extensibles** | `ExecutorRegistry` et `TriggerRegistry` permettent l'extensibilité |
| **DAG de dépendances** | Le `depends_on` entre Steps permet des workflows complexes |
| **Suspension/Reprise** | Pattern `WAITING_HUMAN` / `WAITING_EXTERNAL` avec `resume()` |
| **Snapshot de config** | Le `JobRun` conserve un instantané → reproductibilité |
| **SubJob** | L'imbrication de workflows est prévue nativement |

#### ❌ Couplages problématiques

| Couplage | Impact |
|---|---|
| **`django.db.models.Model`** | Impossible d'utiliser hors Django |
| **Signaux Django** | `SignalTrigger` dépend de `post_save`, `post_delete` |
| **Celery obligatoire** | Nécessite un broker même pour des cas simples |
| **`django.contrib.auth.User`** | Le `HumanExecutor` est couplé à l'auth Django |
| **Migrations Django** | Le schéma est géré par Django uniquement |
| **Multi-tenant Django** | Le `tenant` est câblé dans les modèles |

### Comparatif des Approches

```
                        Django App    Package Python Pur
                        ──────────    ──────────────────
Portabilité             ★☆☆☆☆         ★★★★★
Testabilité             ★★☆☆☆         ★★★★★
Vitesse de prototypage  ★★★☆☆         ★★★★★
Persistence intégrée    ★★★★★         ★★★☆☆ (pluggable)
UI Admin gratuite       ★★★★★         ☆☆☆☆☆
Écosystème async        ★★☆☆☆         ★★★★★
Dépendances             ★☆☆☆☆         ★★★★★
Maintenabilité          ★★★☆☆         ★★★★☆
Extensibilité           ★★★☆☆         ★★★★★
Time-to-market          ★★★★☆         ★★☆☆☆ (réécriture)
```

---

## 🏗️ Architecture Recommandée

### Structure du Package

```
pyworkflow_engine/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
│
├── src/
│   └── pyworkflow_engine/
│       ├── __init__.py                    # API publique
│       ├── py.typed                       # Type checking
│       │
│       │# CORE — Zéro dépendance externe
│       ├── core/
│       │   ├── __init__.py
│       │   ├── models/
│       │   │   ├── __init__.py
│       │   │   ├── enums.py               # TriggerType, StepType, ExecutorType, RunStatus
│       │   │   ├── design_time.py         # Job, Step, SubJob (dataclasses)
│       │   │   └── runtime.py             # JobRun, StepRun, StepLog (dataclasses)
│       │   ├── engine.py                  # WorkflowEngine — orchestrateur principal
│       │   ├── dag.py                     # DAGResolver — résolution graphe dépendances
│       │   ├── context.py                 # WorkflowContext — passage I/O entre steps
│       │   └── exceptions.py              # WorkflowSuspended, WorkflowFailed, etc.
│       │
│       │# EXECUTORS — Comment une étape est exécutée
│       ├── executors/
│       │   ├── __init__.py
│       │   ├── base.py                    # ABC BaseExecutor
│       │   ├── registry.py                # ExecutorRegistry
│       │   ├── local.py                   # LocalExecutor — sync, dans le process
│       │   ├── thread.py                  # ThreadExecutor — ThreadPoolExecutor
│       │   ├── async_executor.py          # AsyncExecutor — asyncio natif
│       │   ├── process.py                 # ProcessExecutor — multiprocessing
│       │   ├── human.py                   # HumanExecutor — suspend, WAITING_HUMAN
│       │   ├── agent.py                   # AgentExecutor — délègue à un agent IA
│       │   └── external.py               # ExternalExecutor — suspend, WAITING_EXTERNAL
│       │
│       │# TRIGGERS — Comment un workflow est déclenché
│       ├── triggers/
│       │   ├── __init__.py
│       │   ├── base.py                    # ABC BaseTrigger
│       │   ├── registry.py                # TriggerRegistry
│       │   ├── manual.py                  # ManualTrigger — appel direct
│       │   ├── api.py                     # ApiTrigger — déclenché par endpoint
│       │   ├── webhook.py                 # WebhookTrigger — payload entrant
│       │   ├── schedule.py                # ScheduleTrigger — cron (pas Celery Beat)
│       │   ├── signal.py                  # SignalTrigger — pub/sub interne
│       │   └── event.py                   # EventTrigger — event bus générique
│       │
│       │# PERSISTENCE — Où les données sont stockées
│       ├── persistence/
│       │   ├── __init__.py
│       │   ├── base.py                    # ABC BaseStorage
│       │   ├── memory.py                  # InMemoryStorage — tests, scripts, notebooks
│       │   ├── json_file.py              # JSONFileStorage — fichier JSON local
│       │   └── sqlite.py                 # SQLiteStorage — sqlite3 stdlib
│       │
│       │# SERIALIZATION — Conversion dataclass ↔ dict/JSON
│       ├── serialization/
│       │   ├── __init__.py
│       │   ├── serializer.py             # to_dict / from_dict pour Job, JobRun, etc.
│       │   └── snapshot.py               # Création de snapshots immuables
│       │
│       │# CONTRIB — Fonctionnalités opt-in
│       ├── contrib/
│       │   ├── __init__.py
│       │   ├── retry.py                  # RetryPolicy — backoff exponentiel, jitter
│       │   ├── timeout.py                # TimeoutPolicy — deadline par step/job
│       │   ├── hooks.py                  # Lifecycle hooks
│       │   ├── middleware.py             # Pipeline de middlewares
│       │   └── validators.py            # Validation de DAG
│       │
│       │# ADAPTERS — Intégrations framework (extras pip)
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── django/                   # pip install pyworkflow-engine[django]
│       │   │   ├── __init__.py
│       │   │   ├── models.py             # Modèles Django wrappant dataclasses core
│       │   │   ├── persistence.py        # DjangoORMPersistence(BaseStorage)
│       │   │   ├── signals.py            # DjangoSignalTrigger
│       │   │   ├── admin.py              # Admin Django
│       │   │   ├── views.py              # Vues DRF
│       │   │   ├── urls.py               # Routes API
│       │   │   └── apps.py               # AppConfig Django
│       │   ├── fastapi/                  # pip install pyworkflow-engine[fastapi]
│       │   │   ├── __init__.py
│       │   │   ├── routes.py             # APIRouter FastAPI
│       │   │   ├── dependencies.py       # Injection de dépendances
│       │   │   └── websocket.py          # WS pour suivi temps réel
│       │   ├── celery/                   # pip install pyworkflow-engine[celery]
│       │   │   ├── __init__.py
│       │   │   ├── executor.py           # CeleryExecutor(BaseExecutor)
│       │   │   ├── tasks.py              # Tâches Celery génériques
│       │   │   └── schedule.py           # Celery Beat → ScheduleTrigger bridge
│       │   ├── sqlalchemy/               # pip install pyworkflow-engine[sqlalchemy]
│       │   │   ├── __init__.py
│       │   │   ├── models.py             # Tables SQLAlchemy
│       │   │   └── persistence.py        # SQLAlchemyStorage(BaseStorage)
│       │   └── streamlit/                # pip install pyworkflow-engine[streamlit]
│       │       ├── __init__.py
│       │       ├── components.py         # Widgets workflow
│       │       └── dashboard.py          # Dashboard pré-construit
│       │
│       │# CLI — Interface ligne de commande
│       └── cli/
│           ├── __init__.py
│           ├── main.py                   # Point d'entrée CLI
│           ├── commands/
│           │   ├── __init__.py
│           │   ├── run.py                # workflow run <job_id>
│           │   ├── list.py               # workflow list [--status running]
│           │   ├── inspect.py            # workflow inspect <run_id>
│           │   ├── validate.py           # workflow validate <job_file.yaml>
│           │   └── export.py             # workflow export <job_id> --format yaml|json
│           └── formatters.py             # Rich/table output
│
├── tests/                                # Tests complets
├── docs/                                 # Documentation
├── examples/                             # Exemples d'usage
└── .github/workflows/                    # CI/CD
```

### Principes Architecturaux

| Règle | Application |
|---|---|
| **Le `core/` n'importe RIEN d'extérieur** | Pas de `import django`, `import celery`, etc. dans `core/` |
| **Les `adapters/` importent core + framework** | Sens unique : `adapter → core`, jamais l'inverse |
| **Les executors built-in utilisent stdlib uniquement** | `local`, `thread`, `process`, `human` = zéro dépendance |
| **Les extras pip contrôlent les dépendances** | Installation modulaire selon les besoins |
| **API publique via `__init__.py`** | Import simple : `from pyworkflow_engine import Job, WorkflowEngine` |
| **Tests core sans dépendances** | `pytest tests/unit/` → < 2s, zéro DB, zéro broker |

---

## 📝 Configuration du Package

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pyworkflow-engine"
version = "0.1.0"
description = "Moteur d'orchestration de workflows Python pur — zero dépendance framework"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [
    { name = "IAS", email = "dev@ias.com" },
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]

# ⚠️ ZERO dépendance obligatoire pour le core
dependencies = []

[project.optional-dependencies]
# Adapters — chaque intégration est opt-in
django = ["django>=4.2", "djangorestframework>=3.14"]
fastapi = ["fastapi>=0.100", "uvicorn>=0.20"]
celery = ["celery>=5.3"]
sqlalchemy = ["sqlalchemy>=2.0"]
streamlit = ["streamlit>=1.30"]

# CLI
cli = ["click>=8.0", "rich>=13.0"]

# Dev / Tests
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.0",
]
docs = [
    "mkdocs>=1.5",
    "mkdocs-material>=9.0",
    "mkdocstrings[python]>=0.24",
]

# Tout installer
all = [
    "pyworkflow-engine[django,fastapi,celery,sqlalchemy,streamlit,cli]",
]

[project.scripts]
workflow = "pyworkflow_engine.cli.main:cli"

[project.urls]
Homepage = "https://github.com/ias/pyworkflow-engine"
Documentation = "https://ias.github.io/pyworkflow-engine"
Repository = "https://github.com/ias/pyworkflow-engine"

[tool.hatch.build.targets.wheel]
packages = ["src/pyworkflow_engine"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "TCH"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
```

---

## 🚀 Plan de Migration

### Phase 1 — Core pur (semaines 1-2)

**Objectif** : Extraire les modèles et le moteur d'exécution sans aucune dépendance.

#### Modèles Design-Time (`core/models/design_time.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from enum import Enum
import uuid

class TriggerType(str, Enum):
    MANUAL = "manual"
    API = "api"
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    SIGNAL = "signal"
    EVENT = "event"

class StepType(str, Enum):
    PYTHON = "python"
    HTTP = "http"
    EMAIL = "email"
    DATABASE = "database"
    SUBWORKFLOW = "subworkflow"
    AI = "ai"

class ExecutorType(str, Enum):
    LOCAL = "local"
    THREAD = "thread"
    ASYNC = "async"
    HUMAN = "human"
    AGENT = "agent"
    EXTERNAL = "external"

@dataclass
class Step:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    step_type: StepType = StepType.PYTHON
    executor_type: ExecutorType = ExecutorType.LOCAL
    config: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    retry_count: int = 0
    timeout: int | None = None
    callable: Any = None  # Pour step_type=PYTHON

@dataclass
class Job:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    trigger_type: TriggerType = TriggerType.MANUAL
    steps: list[Step] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### Modèles Runtime (`core/models/runtime.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from enum import Enum
import uuid

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_HUMAN = "waiting_human"
    WAITING_EXTERNAL = "waiting_external"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

@dataclass
class StepLog:
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    level: str = "info"
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

@dataclass 
class StepRun:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_id: str = ""
    step_snapshot: dict[str, Any] = field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    attempt: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    logs: list[StepLog] = field(default_factory=list)
    executor_info: dict[str, Any] = field(default_factory=dict)

@dataclass
class JobRun:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    job_snapshot: dict[str, Any] = field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    context: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    step_runs: list[StepRun] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    @classmethod
    def from_job(cls, job: "Job", context: dict[str, Any] | None = None) -> "JobRun":
        # Implémentation du snapshot
        pass
```

#### Moteur d'Exécution (`core/engine.py`)

```python
from __future__ import annotations
from typing import Any
from datetime import datetime, timezone

from .models.runtime import JobRun, StepRun, RunStatus
from .models.design_time import Job, Step
from ..executors.registry import ExecutorRegistry
from .exceptions import WorkflowSuspended, WorkflowFailed

class WorkflowEngine:
    """Moteur d'orchestration pur Python — zero dépendance framework."""
    
    def __init__(self, executor_registry: ExecutorRegistry | None = None):
        self.executor_registry = executor_registry or ExecutorRegistry.default()
    
    def run(self, job: Job, context: dict[str, Any] | None = None) -> JobRun:
        """Crée un JobRun et exécute le workflow."""
        job_run = JobRun.from_job(job, context)
        return self.execute(job_run, job)
    
    def execute(self, job_run: JobRun, job: Job) -> JobRun:
        """Exécute ou reprend un JobRun."""
        # Implémentation complète de l'orchestration
        pass
    
    def resume(self, job_run: JobRun, job: Job, step_run_id: str, 
               outputs: dict[str, Any] | None = None) -> JobRun:
        """Reprend un workflow suspendu après une action humaine/externe."""
        # Implémentation de la reprise
        pass
```

### Phase 2 — Executors & Persistence (semaines 2-3)

**Objectif** : Implémenter les exécuteurs pluggables et les systèmes de persistance.

#### Interface Executor (`executors/base.py`)

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from ..core.models.design_time import Step
from ..core.models.runtime import StepRun

class BaseExecutor(ABC):
    @abstractmethod
    def execute(self, step: Step, step_run: StepRun, 
                inputs: dict[str, Any]) -> dict[str, Any] | None:
        """Exécute une étape. Retourne les outputs ou None."""
        ...

class LocalExecutor(BaseExecutor):
    """Exécute la fonction Python directement dans le process."""
    
    def execute(self, step: Step, step_run: StepRun,
                inputs: dict[str, Any]) -> dict[str, Any] | None:
        if step.callable is None:
            raise ValueError(f"Step {step.name} has no callable defined")
        result = step.callable(**inputs)
        if isinstance(result, dict):
            return result
        return {"result": result}
```

#### Interface Persistence (`persistence/base.py`)

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from ..core.models.design_time import Job
from ..core.models.runtime import JobRun

class BaseStorage(ABC):
    """Interface de persistance — swap entre memory, JSON, SQLite, SQLAlchemy, Django ORM."""
    
    @abstractmethod
    def save_job(self, job: Job) -> None: ...
    
    @abstractmethod
    def get_job(self, job_id: str) -> Job | None: ...
    
    @abstractmethod
    def save_job_run(self, job_run: JobRun) -> None: ...
    
    @abstractmethod
    def get_job_run(self, run_id: str) -> JobRun | None: ...
    
    @abstractmethod
    def list_job_runs(self, job_id: str | None = None, 
                      status: str | None = None) -> list[JobRun]: ...

class InMemoryStorage(BaseStorage):
    """Parfait pour les tests, scripts, notebooks."""
    
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._runs: dict[str, JobRun] = {}
    
    # Implémentation complète...
```

### Phase 3 — Adapters Framework (semaines 3-4)

**Objectif** : Créer les adapters pour Django, FastAPI, Celery, etc.

#### Adapter Django (`adapters/django/persistence.py`)

```python
"""
Adapter Django — rebranche l'ancien système sur le nouveau core.
Usage: pip install pyworkflow-engine[django]
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from django.db import models

from ...persistence.base import BaseStorage
from ...core.models.design_time import Job
from ...core.models.runtime import JobRun

class DjangoORMPersistence(BaseStorage):
    """Persiste les Jobs/JobRuns via l'ORM Django.
    
    Les modèles Django deviennent de simples wrappers de sérialisation
    autour des dataclasses du core.
    """
    
    def save_job(self, job: Job) -> None:
        from myapp.models import JobModel  # Import tardif pour éviter couplage
        import dataclasses
        JobModel.objects.update_or_create(
            uid=job.id,
            defaults={"data": dataclasses.asdict(job)}
        )
    
    def get_job(self, job_id: str) -> Job | None:
        from myapp.models import JobModel
        try:
            obj = JobModel.objects.get(uid=job_id)
            return _deserialize_job(obj.data)
        except JobModel.DoesNotExist:
            return None
    
    # ... etc.
```

### Phase 4 — Usage Final & Migration

**Objectif** : Valider l'usage dans différents contextes et migrer l'existant.

#### Exemple : Usage dans un Notebook Jupyter

```python
# Exemple : dans un notebook Jupyter
from pyworkflow_engine import Job, Step, StepType, WorkflowEngine

def fetch_data(source: str = "", **kw):
    return {"records": [1, 2, 3], "count": 3}

def transform(records: list = None, **kw):
    return {"transformed": [r * 10 for r in (records or [])]}

def load(transformed: list = None, **kw):
    print(f"Loaded {len(transformed or [])} records")
    return {"loaded": True}

# Définir le workflow
etl = Job(name="ETL Pipeline", steps=[
    Step(id="fetch", name="Fetch", callable=fetch_data),
    Step(id="transform", name="Transform", callable=transform, depends_on=["fetch"]),
    Step(id="load", name="Load", callable=load, depends_on=["transform"]),
])

# Exécuter
engine = WorkflowEngine()
result = engine.run(etl, context={"source": "api"})
print(result.status)   # RunStatus.SUCCESS
print(result.result)   # {'fetch': {...}, 'transform': {...}, 'load': {...}}
```

#### Migration Progressive de l'Existant

1. **Installer le nouveau package** : `pip install pyworkflow-engine[django]`
2. **Créer un adapter bridge** : Wrapper qui convertit les modèles Django existants
3. **Tests parallèles** : Valider que les deux systèmes produisent les mêmes résultats
4. **Migration graduelle** : Feature flag pour basculer progressivement
5. **Décommissioning** : Suppression de l'ancienne implémentation

---

## 📈 Bénéfices Attendus

### Pour les Développeurs

| Bénéfice | Impact |
|---|---|
| **Zero setup** | `pip install pyworkflow-engine` → ready to go |
| **Testabilité** | Tests du core < 2s, pas de DB, pas de Docker |
| **Prototypage rapide** | Notebook → Production sans changement de code |
| **Type safety** | Dataclasses + mypy = erreurs caught à l'écriture |
| **Debugging facile** | Logs structurés, états inspectables |

### Pour les Projets

| Bénéfice | Impact |
|---|---|
| **Réutilisabilité** | Un package → N projets (scripts, web apps, CLI) |
| **Maintenance réduite** | Une seule codebase au lieu de N implémentations |
| **Performance** | Async natif, pas de surcharge ORM pour les cas simples |
| **Extensibilité** | Nouveaux executors/triggers sans modifier le core |
| **Portabilité** | Fonctionne partout où Python fonctionne |

### Pour l'Organisation

| Bénéfice | Impact |
|---|---|
| **Standardisation** | Workflows identiques across tous les environnements |
| **Réduction des dépendances** | Moins de packages à maintenir/auditer |
| **Open Source ready** | Publiable sur PyPI, contributeurs externes |
| **Future-proof** | Architecture découplée, migration framework facile |

---

## 🎯 Recommandation Finale

**➡️ Adopter l'Approche B — Package Python Pur avec Adapter Django**

### Pourquoi cette approche gagne

1. **Le core n'importe aucun framework** → utilisable partout
2. **Django devient un adapter** → on ne perd rien de l'existant
3. **Les tests du core tournent en < 1s** → pas de DB, pas de `django.setup()`
4. **On peut prototyper dans un notebook** puis déployer en production Django/FastAPI sans changer le workflow
5. **Le package est publiable sur PyPI** → réutilisable dans tous vos projets
6. **L'architecture conceptuelle existante est préservée** — on change le *comment*, pas le *quoi*

### Stratégie "Library-first, Framework-second"

L'idée n'est pas de *jeter* le Django existant mais d'**extraire le cœur** dans un package pur puis de **rebrancher Django par-dessus** via un adapter mince.

Cette approche nous donne le meilleur des deux mondes : la puissance de l'architecture existante + la flexibilité d'un package Python pur.

---

**Status** : ✅ **Recommandation Approuvée**  
**Next Steps** : Définir les sprints de développement et commencer par la Phase 1
