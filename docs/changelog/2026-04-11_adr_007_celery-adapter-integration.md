# ADR-007 — Intégration Celery : adapter complexe vs simple executor

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-007                             |
| **Date**    | 11 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (architecture hexagonale Ports & Adapters) |
| **Version cible** | v0.7.0                         |

---

## Contexte

### Situation actuelle

Suite à l'ADR-006, l'architecture hexagonale est en place :

```
src/pyworkflow_engine/
├── ports/
│   ├── executor.py          ← BaseExecutor (ABC)
│   ├── persistence.py       ← BasePersistence
│   └── trigger.py           ← BaseTrigger
├── adapters/
│   ├── executors/           ← Executors simples (stdlib)
│   │   ├── local.py
│   │   ├── thread_pool.py
│   │   ├── process_pool.py
│   │   ├── async_exec.py
│   │   └── retryable.py
│   ├── persistence/         ← Backends de stockage
│   ├── triggers/            ← Déclencheurs
│   ├── celery/              ← VIDE — à implémenter
│   └── snowflake/           ← Intégration Snowflake
```

Le `ExecutorType` enum définit déjà `CELERY = "celery"` dans `models/enums.py`, et le `_resolve_executor()` du `WorkflowRunner` retourne `None` pour ce type (non implémenté dans le core).

Le `pyproject.toml` déclare déjà l'extra `celery = ["celery>=5.3"]`.

### La question

Celery doit-il :
- **(A)** vivre dans `adapters/executors/celery.py` (un fichier parmi les autres executors) ?
- **(B)** rester dans `adapters/celery/` (dossier dédié multi-fichiers) ?

---

## Analyse : Celery est plus qu'un executor

### Ce que Celery apporte au-delà de l'exécution

| Capacité | Simple executor ? | Spécifique Celery ? |
|---|---|---|
| Exécuter une fonction en arrière-plan | ✅ | — |
| Distribution sur des workers distants | — | ✅ |
| Broker de messages (Redis / RabbitMQ) | — | ✅ |
| Monitoring (Flower) | — | ✅ |
| Configuration propre (`celery_app`) | — | ✅ |
| Retry natif Celery (distinct de `RetryHandler`) | — | ✅ |
| Sérialisation des tasks | — | ✅ |
| Result backend | — | ✅ |
| Scheduling natif (Celery Beat) | — | ✅ (overlap avec `adapters/triggers/`) |

### Comparaison avec les executors simples

| Executor | Fichiers nécessaires | Dépendances externes | Configuration propre |
|---|---|---|---|
| `LocalExecutor` | 1 (`local.py`) | Aucune (stdlib) | Non |
| `ThreadPoolStepExecutor` | 1 (`thread_pool.py`) | Aucune (stdlib) | Non |
| `ProcessPoolStepExecutor` | 1 (`process_pool.py`) | Aucune (stdlib) | Non |
| `AsyncStepExecutor` | 1 (`async_exec.py`) | Aucune (stdlib) | Non |
| `RetryableExecutor` | 1 (`retryable.py`) | Aucune (stdlib) | Non |
| **CeleryExecutor** | **3-4** (executor + app factory + tasks + config) | **celery, redis/rabbitmq** | **Oui** (broker, backend, serializer, etc.) |

### Verdict

> Celery **implémente** le port `BaseExecutor` (il exécute des steps), mais il nécessite une **configuration, sérialisation et glue** qui dépassent largement l'interface `BaseExecutor.execute()`.

---

## Décision

### Celery vit dans `adapters/celery/` — dossier dédié multi-fichiers

#### Règle de placement

```
┌──────────────────────────────────────────────────────────┐
│  Adapter SIMPLE (1 concern, 1 fichier, stdlib only)      │
│  → adapters/{category}/{name}.py                         │
│                                                          │
│  Adapter COMPLEXE (config + glue + deps externes)        │
│  → adapters/{name}/                                      │
│    ├── __init__.py   (re-exports publics)                │
│    ├── executor.py   (implémente le port)                │
│    ├── config.py     (configuration spécifique)          │
│    └── ...           (glue spécifique)                   │
└──────────────────────────────────────────────────────────┘
```

Un adapter mérite son propre package dès que :
1. Il nécessite **2+ fichiers** coordonnés, **ou**
2. Il dépend d'une **bibliothèque tierce** avec configuration propre, **ou**
3. Il expose des **concepts spécifiques** au-delà du port (tasks, app, config)

Celery coche les 3 critères.

#### Structure cible

```
adapters/celery/
├── __init__.py        ← re-export public : CeleryExecutor, CeleryConfig
├── executor.py        ← implémente ports.executor.BaseExecutor
├── app.py             ← factory Celery app (singleton configurable)
├── tasks.py           ← @celery_task wrappers pour l'exécution des steps
└── config.py          ← CeleryConfig dataclass (broker, backend, serializer, etc.)
```

#### Contrat de chaque fichier

##### `executor.py` — Implémente le port

```python
"""CeleryExecutor — exécution distribuée des workflow steps via Celery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkflow_engine.ports.executor import BaseExecutor

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext
    from pyworkflow_engine.models import Step


class CeleryExecutor(BaseExecutor):
    """Executor qui délègue l'exécution des steps à des Celery workers.

    Respecte le contrat ``BaseExecutor.execute(step, context)`` et délègue
    l'exécution réelle à une Celery task via le broker configuré.

    Usage::

        from pyworkflow_engine.adapters.celery import CeleryExecutor

        executor = CeleryExecutor(broker_url="redis://localhost:6379/0")
        engine = WorkflowEngine()
        engine.register_executor("celery", executor)
    """

    def __init__(
        self,
        broker_url: str = "redis://localhost:6379/0",
        result_backend: str | None = None,
        task_timeout: float | None = None,
        task_serializer: str = "json",
    ) -> None: ...

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Envoie l'exécution au broker Celery et attend le résultat."""
        ...
```

##### `app.py` — Factory Celery application

```python
"""Factory pour l'instance Celery application (singleton configurable)."""

from __future__ import annotations

from functools import lru_cache

from celery import Celery


@lru_cache(maxsize=1)
def get_celery_app(
    broker_url: str = "redis://localhost:6379/0",
    result_backend: str | None = None,
    app_name: str = "pyworkflow_engine",
) -> Celery:
    """Crée et configure l'application Celery singleton.

    La factory est cachée : un seul appel crée l'app, les suivants
    retournent la même instance (tant que les paramètres sont identiques).
    """
    app = Celery(app_name, broker=broker_url, backend=result_backend)
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
    )
    return app
```

##### `tasks.py` — Celery tasks wrappers

```python
"""Celery tasks — wrappers pour l'exécution sérialisée des steps."""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.adapters.celery.app import get_celery_app

app = get_celery_app()


@app.task(bind=True, name="pyworkflow_engine.execute_step")
def execute_step_task(self: Any, func: Any, *args: Any, **kwargs: Any) -> Any:
    """Task Celery qui exécute une fonction step sur un worker distant."""
    return func(*args, **kwargs)
```

##### `config.py` — Configuration dédiée

```python
"""Configuration du Celery adapter — dataclass immuable."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CeleryConfig:
    """Configuration pour le CeleryExecutor.

    Tous les champs ont des valeurs par défaut raisonnables.
    L'utilisateur peut surcharger via env vars ou passage explicite.
    """

    broker_url: str = "redis://localhost:6379/0"
    result_backend: str | None = None
    task_serializer: str = "json"
    result_serializer: str = "json"
    accept_content: tuple[str, ...] = ("json",)
    timezone: str = "UTC"
    enable_utc: bool = True
    task_track_started: bool = True
    task_timeout: float | None = None
    task_default_queue: str = "pyworkflow"
    worker_concurrency: int | None = None
    worker_prefetch_multiplier: int = 4
```

##### `__init__.py` — Re-exports publics

```python
"""Celery adapter — exécution distribuée des workflow steps.

Installation : ``pip install pyworkflow-engine[celery]``

Usage::

    from pyworkflow_engine.adapters.celery import CeleryExecutor, CeleryConfig

    executor = CeleryExecutor(broker_url="redis://localhost:6379/0")
    engine.register_executor("celery", executor)
"""

from pyworkflow_engine.adapters.celery.config import CeleryConfig
from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

__all__ = ["CeleryExecutor", "CeleryConfig"]
```

---

## Intégration avec le routing existant

### `WorkflowRunner._resolve_executor()` — modification requise

Le router actuel retourne `None` pour `ExecutorType.CELERY`. L'intégration se fait de **deux manières complémentaires** :

#### Voie 1 — Via `ExecutorRegistry` (recommandée)

L'utilisateur enregistre explicitement le `CeleryExecutor` :

```python
from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.adapters.celery import CeleryExecutor

engine = WorkflowEngine()
engine.register_executor("celery", CeleryExecutor(
    broker_url="redis://localhost:6379/0",
))

# Les steps avec executor_type=CELERY ou executor_name="celery"
# seront routés automatiquement vers cet executor.
```

#### Voie 2 — Auto-discovery par `_resolve_executor()` (optionnelle, phase ultérieure)

Modifier le router pour tenter un lazy import quand `ExecutorType.CELERY` est détecté :

```python
if et == ExecutorType.CELERY:
    try:
        from pyworkflow_engine.adapters.celery import CeleryExecutor
        return CeleryExecutor()
    except ImportError:
        raise StepExecutionError(
            f"Celery adapter non installé. "
            f"Installez-le avec : pip install pyworkflow-engine[celery]"
        )
```

**Recommandation** : commencer par la **voie 1** (explicite, zéro magie). Ajouter la voie 2 si les retours utilisateurs le justifient.

---

## Gestion des erreurs et lazy imports

### Pattern `ImportError` gracieux

Celery est une dépendance **optionnelle**. L'import doit échouer proprement si le package n'est pas installé :

```python
# adapters/celery/__init__.py
try:
    from pyworkflow_engine.adapters.celery.config import CeleryConfig
    from pyworkflow_engine.adapters.celery.executor import CeleryExecutor
except ImportError as exc:
    raise ImportError(
        "Le Celery adapter nécessite la dépendance 'celery'. "
        "Installez-la avec : pip install pyworkflow-engine[celery]"
    ) from exc

__all__ = ["CeleryExecutor", "CeleryConfig"]
```

Ce pattern est le standard de l'écosystème Python pour les extras optionnels (SQLAlchemy, Pydantic, FastAPI le font tous).

---

## Cohérence avec les autres adapters complexes

La même règle s'applique aux futurs adapters :

| Adapter | Type | Emplacement | Justification |
|---|---|---|---|
| `LocalExecutor` | Simple | `adapters/executors/local.py` | 1 fichier, stdlib only |
| `ThreadPoolStepExecutor` | Simple | `adapters/executors/thread_pool.py` | 1 fichier, stdlib only |
| **CeleryExecutor** | **Complexe** | **`adapters/celery/`** | Multi-fichiers, dep externe, config propre |
| **SnowflakeLogHandler** | **Complexe** | **`adapters/snowflake/`** | Multi-fichiers, dep externe, config propre |
| `InMemoryPersistence` | Simple | `adapters/persistence/memory.py` | 1 fichier, stdlib only |
| **SQLAlchemyPersistence** | **Complexe** | **`adapters/sqlalchemy/`** | Multi-fichiers, dep externe, config propre |
| Futur `KubernetesExecutor` | Complexe | `adapters/kubernetes/` | Multi-fichiers, dep externe, config propre |

### Analogie avec l'écosystème

| Projet | Adapter simple | Adapter complexe |
|---|---|---|
| **Django** | `backends/sqlite3.py` | `backends/postgresql/` (dossier) |
| **SQLAlchemy** | `dialects/sqlite/` | `dialects/postgresql/` (dossier avec types, etc.) |
| **Airflow** | `executors/local_executor.py` | `executors/celery_executor.py` + `celery/` (package dédié) |
| **Prefect** | `task_runners/sequential.py` | `infrastructure/kubernetes.py` + `workers/kubernetes/` |

---

## Sérialisation des steps — contrainte critique

### Le problème

Celery sérialise les arguments des tasks via le broker (Redis/RabbitMQ). Les fonctions Python **ne sont pas sérialisables en JSON**.

### Solutions possibles

| Approche | Description | Complexité |
|---|---|---|
| **Référence par nom** | Envoyer le nom qualifié de la fonction (`"module.func"`) et la résoudre côté worker via `importlib` | Faible |
| **Pickle** | Utiliser le sérialiseur pickle de Celery (fonctionne pour les fonctions locales) | Faible mais risqué (sécurité) |
| **Task registry** | Pré-enregistrer les handlers comme `@app.task` Celery et ne transmettre que le task name | Moyenne |

**Recommandation** : commencer par l'approche **référence par nom** (sûre, simple, standard) :

```python
# Dans executor.py
import importlib

def _serialize_handler(self, handler: Callable) -> str:
    """Sérialise un handler en référence importable."""
    return f"{handler.__module__}.{handler.__qualname__}"

def _deserialize_handler(self, handler_ref: str) -> Callable:
    """Résout une référence en handler callable."""
    module_path, _, func_name = handler_ref.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, func_name)
```

---

## Plan d'implémentation

### Phase 1 — Scaffolding (v0.7.0-alpha)

| Tâche | Fichier | Effort |
|---|---|---|
| Créer `CeleryConfig` dataclass | `adapters/celery/config.py` | 30 min |
| Créer la factory `get_celery_app()` | `adapters/celery/app.py` | 30 min |
| Créer `execute_step_task` | `adapters/celery/tasks.py` | 1h |
| Implémenter `CeleryExecutor` | `adapters/celery/executor.py` | 2h |
| Re-exports + lazy import guard | `adapters/celery/__init__.py` | 15 min |

### Phase 2 — Intégration router (v0.7.0-beta)

| Tâche | Fichier | Effort |
|---|---|---|
| Ajouter routing `ExecutorType.CELERY` dans `_resolve_executor` | `engine/runner.py` | 30 min |
| Ajouter `redis` à l'extra celery dans pyproject.toml | `pyproject.toml` | 5 min |
| Exemple end-to-end | `examples/celery_distributed.py` | 1h |

### Phase 3 — Tests et documentation (v0.7.0)

| Tâche | Fichier | Effort |
|---|---|---|
| Tests unitaires (mock Celery) | `tests/unit/test_celery_adapter.py` | 2h |
| Tests d'intégration (Redis local) | `tests/integration/test_celery_workflow.py` | 2h |
| Documentation utilisateur | `docs/integrations/celery.md` | 1h |

### Effort total estimé : ~10h

---

## Alternatives considérées

### Alternative A — `adapters/executors/celery.py` (fichier unique)

Placer tout le code Celery dans un seul fichier parmi les autres executors.

**Pour** : cohérent avec le placement des autres executors.
**Contre** :
- Fichier monolithique mêlant executor, app factory, tasks et config (~300+ lignes)
- Impossible de tester `tasks.py` indépendamment de `executor.py`
- Incohérent avec `adapters/snowflake/` et `adapters/sqlalchemy/` qui ont déjà un dossier dédié
- Viole le Single Responsibility Principle

**Verdict** : ❌ Rejetée — un adapter complexe ne tient pas dans un seul fichier sans sacrifier la maintenabilité.

### Alternative B — Celery hors du package (package séparé `pyworkflow-celery`)

Publier un package séparé `pyworkflow-celery` sur PyPI.

**Pour** : isolation totale, versionning indépendant.
**Contre** :
- Overhead de maintenance (2 repos, 2 CI, 2 versions à synchroniser)
- Disproportionné à ce stade du projet
- L'écosystème Python (Django, Airflow, Prefect) embarque les adapters standard dans le package principal

**Verdict** : ❌ Rejetée — pertinent uniquement si l'adapter devient très volumineux ou si des contributeurs externes le maintiennent. À reconsidérer si `adapters/celery/` dépasse ~15 fichiers.

### Alternative C — Wrapper thin avec délégation totale à Celery

Ne pas implémenter `BaseExecutor`, juste exposer un helper qui transforme un `Job` en DAG Celery natif (`chain`, `group`, `chord`).

**Pour** : exploite pleinement les primitives Celery.
**Contre** :
- Casse l'abstraction hexagonale — le domaine (`engine/`) devrait connaître Celery
- Impossible de basculer entre `LocalExecutor` et `CeleryExecutor` sans changer le code métier
- Perte de la portabilité de l'architecture

**Verdict** : ❌ Rejetée — l'intérêt de l'architecture hexagonale est précisément de rendre les adapters interchangeables.

---

## Conséquences

### Positives

- **Interchangeabilité** — un workflow développé avec `LocalExecutor` se déploie en distribué en changeant une seule ligne (`engine.register_executor("celery", CeleryExecutor(...))`)
- **Cohérence architecturale** — suit exactement le pattern établi par ADR-006 pour les adapters complexes
- **Testabilité** — chaque fichier (`config`, `app`, `tasks`, `executor`) est testable indépendamment
- **Lazy loading** — Celery n'est importé que si l'utilisateur en a besoin (`pip install pyworkflow-engine[celery]`)
- **Extensibilité** — le pattern s'applique à Kubernetes, Dask, Ray quand ils seront nécessaires

### Négatives

- **Complexité de sérialisation** — les fonctions Python ne se sérialisent pas nativement en JSON ; nécessite une stratégie (référence par nom)
- **Dépendance infrastructure** — les tests d'intégration nécessitent un broker Redis/RabbitMQ local
- **Overlap potentiel** — le retry natif Celery peut entrer en conflit avec le `RetryHandler` du core

### Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Double-retry (Celery + core) | Moyenne | Moyen | Documenter que `CeleryExecutor` désactive le retry Celery natif par défaut ; laisser l'utilisateur activer l'un ou l'autre |
| Sérialisation de handlers complexes (lambdas, closures) | Haute | Moyen | Documenter la contrainte : les handlers doivent être des fonctions top-level importables ; lever une `SerializationError` claire sinon |
| Overhead de configuration pour les débutants | Faible | Faible | Fournir des defaults raisonnables dans `CeleryConfig` + un exemple complet |

---

## Références

- [Celery — Getting Started](https://docs.celeryq.dev/en/stable/getting-started/)
- [Airflow CeleryExecutor](https://airflow.apache.org/docs/apache-airflow-providers-celery/stable/celery_executor.html) — référence d'intégration Celery dans un orchestrateur
- [Prefect Task Runners](https://docs.prefect.io/latest/concepts/task-runners/) — pattern comparable (DaskTaskRunner, RayTaskRunner)
- ADR-006 — Architecture hexagonale : introduction `ports/` et réorganisation `adapters/`
- [Cosmic Python — Ports & Adapters](https://www.cosmicpython.com/) — patterns d'architecture hexagonale en Python
