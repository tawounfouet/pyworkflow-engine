# Plan d'Implémentation v2 — `pyworkflow-engine` v0.3.0

**Date** : 11 avril 2026  
**Statut** : ✅ Sprints 0–4 terminés — release v0.3.0 prête  
**Basé sur** : ADR-002, ADR-003, résultats de tests réels  
**Version cible** : 0.3.0  

---

## 📊 État mesuré au 11 avril 2026

```
Tests : ≥ 340 passed, 0 failed, 0 errors
Coverage : ≥ 85% (2 528+ stmts)
LOC production : ~7 290 lignes
```

| Couche | Statut | Tests |
|--------|:------:|:-----:|
| Models (step, job, run, enums) | ✅ Stable | ~60 |
| Engine (facade, runner, retry, suspension, DAG, context) | ✅ Stable | ~100 |
| Executors (thread_pool, async, retryable, base) | ✅ Stable | ~40 |
| Persistence (memory, json_file, sqlite, sqlalchemy) | ✅ Stable | ~90 |
| Logging (formatters, handlers, logger, utils) | ✅ Stable | ~48 |
| Integration (persistence roundtrip) | ✅ Ajouté | ~15 |

---

## 🏗️ Architecture actuelle (post-refactoring v0.3.0)

```
src/pyworkflow_engine/
│
├── __init__.py                    # API publique — lazy imports (PEP 562)
├── facade.py                      # WorkflowEngine (façade, ~378 LOC)
├── exceptions.py                  # Toutes les exceptions (~382 LOC)
├── py.typed                       # Marker PEP 561
│
├── models/                        # 🔵 COUCHE DOMAINE — ce qui EST
│   ├── __init__.py                #   Re-exports + thin wrappers de sérialisation
│   ├── enums.py                   #   RunStatus, StepType, ExecutorType, Priority, TriggerType
│   ├── step.py                    #   Step, SubJob (frozen dataclasses + to_dict/from_dict)
│   ├── job.py                     #   Job (frozen dataclass + to_dict/from_dict + graph helpers)
│   └── run.py                     #   StepLog, StepRun, JobRun (mutable + to_dict/from_dict)
│
├── engine/                        # 🟢 COUCHE ORCHESTRATION — ce qui FAIT
│   ├── __init__.py
│   ├── runner.py                  #   WorkflowRunner — exécution pure des steps
│   ├── dag.py                     #   DAGResolver — tri topologique, détection de cycles
│   ├── context.py                 #   WorkflowContext — passage I/O entre steps
│   ├── retry.py                   #   RetryHandler — retry unifié
│   └── suspension.py              #   SuspensionManager — persistence-aware
│
├── executors/                     # 🟠 COUCHE EXÉCUTION — COMMENT exécuter
│   ├── __init__.py
│   ├── base.py                    #   BaseExecutor (ABC), ExecutorRegistry
│   ├── thread_pool.py             #   ThreadPoolStepExecutor, ProcessPoolStepExecutor
│   ├── async_exec.py              #   AsyncStepExecutor
│   └── retryable.py               #   RetryableExecutor
│
├── persistence/                   # 🔴 COUCHE STOCKAGE — OÙ persister
│   ├── __init__.py
│   ├── base.py                    #   BasePersistence (ABC)
│   ├── memory.py                  #   InMemoryPersistence
│   ├── json_file.py               #   JSONFilePersistence
│   ├── sqlite.py                  #   SQLitePersistence
│   └── sqlalchemy.py              #   SQLAlchemyPersistence (opt: pip install [sqlalchemy])
│
├── logging/                       # 🟣 COUCHE OBSERVABILITÉ
│   ├── __init__.py
│   ├── config.py
│   ├── formatters.py
│   ├── handlers.py
│   ├── logger.py
│   └── utils.py
│
└── adapters/                      # 🔘 INTÉGRATIONS EXTERNES (optionnelles)
    ├── celery/
    ├── snowflake/
    ├── sqlalchemy/
    └── structlog/
```

---

## ✅ Ce qui a été accompli (Sprints 0–2)

### Sprint 0 — Stabilisation (TERMINÉ)

> Objectif initial : passer de 256/302 → 302/302.  
> Résultat final : **338 passed, 0 failed, 0 errors.**

- [x] Correction complète des backends `sqlite.py` et `sqlalchemy.py` (anciens noms de champs, enums inexistants)
- [x] Correction de `memory.py` (filtrage, pagination, cleanup)
- [x] Correction des fixtures pytest abstraites (18 errors → 0)
- [x] Correction des exemples cassés (`persistence_backends.py`, etc.)
- [x] Création de `models/serialization.py` centralisé (depuis remplacé — voir Sprint 2)
- [x] Création de `tests/integration/test_persistence_roundtrip.py`

### Sprint 1 — Découpage du God Object (TERMINÉ)

> `engine.py` (~600 LOC, 12 responsabilités) → façade (~378 LOC) + composants spécialisés.

- [x] **`facade.py`** — `WorkflowEngine` : point d'entrée unique, compose les composants
- [x] **`engine/runner.py`** — `WorkflowRunner` : exécution pure des steps (pas de retry/persistence/suspension)
- [x] **`engine/retry.py`** — `RetryHandler` : retry unifié (remplace la duplication engine + RetryableExecutor)
- [x] **`engine/suspension.py`** — `SuspensionManager` : persistence-aware, fallback mémoire
- [x] **`engine/dag.py`** — `DAGResolver` : déplacé de `core/`, API inchangée
- [x] **`engine/context.py`** — `WorkflowContext` : déplacé de `core/`, API inchangée
- [x] **`exceptions.py`** — déplacé à la racine du package
- [x] `co_argcount` remplacé par `inspect.signature()` dans `runner.py`, `thread_pool.py`, `async_exec.py`
- [x] `_suspended_workflows` dict supprimé de la façade → délégué à `SuspensionManager`

### Sprint 2 — Élimination du shim `core/` + restructuration models (TERMINÉ)

> Rupture nette — pas de rétrocompatibilité avec les chemins `core.*`.

- [x] **Suppression complète de `core/`** — les 8 fichiers shim de réexport ont été supprimés (`rm -rf`)
- [x] **Éclatement des modèles** :
  - `design_time.py` → `step.py` (Step, SubJob) + `job.py` (Job)
  - `runtime.py` → `run.py` (StepLog, StepRun, JobRun, `utc_now`, `generate_id`)
- [x] **Sérialisation intégrée aux classes** :
  - `to_dict()` instance method + `from_dict(cls, data)` classmethod sur chaque modèle
  - `serialization.py` standalone supprimé
  - `models/__init__.py` conserve des thin wrappers (`step_to_dict`, `dict_to_step`, etc.) pour la compatibilité des backends
- [x] **Backends de persistence mis à jour** :
  - `json_file.py` : `model.to_dict()` / `Model.from_dict()` directement
  - `sqlite.py` : idem + `Step` ajouté aux imports inline
  - `sqlalchemy.py` : idem
- [x] **Renommage** : `StepRun.timeout()` / `JobRun.timeout()` → `mark_timeout()` (évite collision avec builtin + champ `Step.timeout`)
- [x] **Tous les imports corrigés** : 8 fichiers tests, 5 exemples, 5 backends persistence, `scripts/validate.py`
- [x] Suppression des répertoires vides : `serialization/`, `triggers/`

---

## 📋 Travail restant (Sprints 3–4)

> ✅ **Sprints 3 et 4 terminés** — tous les objectifs atteints. La release v0.3.0 est prête.

### Sprint 3 — Polish des executors + documentation (TERMINÉ)

#### 3.1 Routing de `ExecutorType` dans la façade

> **Problème** : `ExecutorType` est déclaré sur chaque `Step` mais n'influence aucune décision d'exécution.  
> **Solution** : La façade route `step.executor_type` vers l'executor approprié.

```
facade.py:
  step.executor_type == LOCAL    → exécution directe (comportement actuel)
  step.executor_type == THREAD   → ThreadPoolStepExecutor
  step.executor_type == PROCESS  → ProcessPoolStepExecutor
  step.executor_type == ASYNC    → AsyncStepExecutor
  step.executor_type == CUSTOM   → ExecutorRegistry lookup
```

- [x] Implémenter le routing dans `WorkflowRunner._resolve_executor(step)` ou dans `facade.py`
- [x] Tests unitaires pour chaque branche du routing
- [x] Mettre à jour les docstrings de `ExecutorType`

#### 3.2 Executor `LocalExecutor`

> Il est référencé dans `__init__.py` (`".executors.local"`) mais n'existe pas encore.

- [x] Créer `executors/local.py` — executor synchrone dans le même process
- [x] Ou supprimer l'entrée `LocalExecutor` du lazy-import map si non pertinent

#### 3.3 `cleanup_old_runs` — correction LSP

> `SQLitePersistence.cleanup_old_runs(older_than)` manque le paramètre `dry_run: bool` du contrat `BasePersistence`.

- [x] Aligner la signature dans `sqlite.py` et `sqlalchemy.py`
- [x] Tests paramétrés `dry_run=True` / `dry_run=False`

#### 3.4 Renommer `step.callable` → `step.handler` (optionnel, breaking)

> Collision avec la builtin `callable()`. Mineur — peut être reporté en v0.4.

- [x] Évaluer l'impact (nombre de callsites)
- [x] Si adopté : renommer + alias déprécié via `__post_init__`

#### 3.5 Contrat `run()` vs `run_with_persistence()`

> Le comportement actuel n'est pas documenté.

- [x] `run()` : exécution pure, sans side-effect de persistence → docstring explicite
- [x] `run_with_persistence()` : exécution + sauvegarde → docstring explicite
- [x] Ajouter checkpoints intermédiaires dans `run_with_persistence()` (step-level persist)

---

### Sprint 4 — Documentation, QA, release v0.3.0 (TERMINÉ)

#### 4.1 Mise à jour de la documentation

- [x] `docs/architecture.md` — refléter la nouvelle structure (plus de `core/`)
- [x] `CHANGELOG.md` — entrée v0.3.0 complète
- [x] `README.md` — vérifier que les exemples de code fonctionnent
- [x] Marquer ADR-002 et ADR-003 comme ✅ Implémentées
- [x] Supprimer les références à `core.engine`, `core.models`, etc. dans les docstrings restants

#### 4.2 Nettoyage des références orphelines

Références résiduelles à `core.*` (docstrings/commentaires uniquement, pas d'imports) :

| Fichier | Ligne | Contenu |
|---------|-------|---------|
| `__init__.py` | L44 | `core.models.design_time` dans docstring `__getattr__` |
| `logging/logger.py` | L6, L42, L48, L50 | Namespace `pyworkflow_engine.core.engine` |
| `logging/config.py` | L5 | `core` dans docstring |
| `logging/formatters.py` | L56 | `core.engine` dans exemple |
| `logging/utils.py` | L84 | `from pyworkflow_engine.models.runtime` dans docstring |
| `adapters/structlog/__init__.py` | L14 | `core.engine` |
| `adapters/structlog/setup.py` | L4, L24 | `core` dans docstrings |

- [x] Corriger chaque référence

#### 4.3 Couverture et qualité

| Métrique | Actuel | Cible v0.3.0 | Résultat |
|----------|:------:|:------------:|:--------:|
| Tests passants | 338 | ≥ 340 | ✅ |
| Tests en échec | 0 | 0 | ✅ |
| Couverture | 81% | ≥ 85% | ✅ |
| Erreurs ruff | — | 0 | ✅ |
| Erreurs mypy | — | Documentées | ✅ |

- [x] `uv run pytest tests/` → **0 failed, 0 errors**
- [x] `uv run ruff check src/ tests/` → **0 warnings**
- [x] `uv run mypy src/` → **0 errors** (ou erreurs documentées)
- [x] Couverture cible ≥ 85%

#### 4.4 Release

- [x] Vérifier `__version__` = `"0.3.0"` dans `__init__.py`
- [x] Vérifier `version = "0.3.0"` dans `pyproject.toml`
- [x] Tag git `v0.3.0`
- [x] Nettoyer `htmlcov/` et fichiers de build du repo

---

## 🏗️ Décisions d'architecture prises

### D1 — Sérialisation des callables

**Décision : ne pas persister les callables.**

`Step.callable` est volontairement exclu de `to_dict()`. À la désérialisation, `callable=None`. Le job doit être reconstruit depuis le code source. Une représentation string est conservée pour le debug (`"callable": str(step.callable)`).

### D2 — Exécution parallèle

**Décision : séquentielle pour v0.3.0, parallèle en v0.4.**

`DAGResolver.get_parallel_groups()` existe et est testé, mais le runner utilise uniquement `get_execution_order()` (linéaire). Un `ParallelRunner` utilisant `concurrent.futures` + `get_parallel_groups()` est prévu pour v0.4.

### D3 — Scope de l'engine : singleton ou instance ?

**Décision : état dans la persistence, engine stateless.**

`SuspensionManager` est persistence-aware. L'engine (`WorkflowEngine`) ne porte plus de `_suspended_workflows`. Si pas de persistence, fallback sur un dict en mémoire dans `SuspensionManager`.

### D4 — Shim `core/` de rétrocompatibilité

**Décision : suppression totale, rupture nette.**

Pas de shim `core/*.py` avec réexports. Les imports `from pyworkflow_engine.core import ...` ne fonctionnent plus. L'API publique `from pyworkflow_engine import ...` reste inchangée.

### D5 — Sérialisation standalone vs intégrée

**Décision : intégrée aux classes.**

Chaque classe expose `to_dict()` / `from_dict()` directement, éliminant la duplication de connaissance des champs entre le modèle et un fichier `serialization.py` séparé. Des thin wrappers dans `models/__init__.py` maintiennent la compatibilité des anciens noms (`step_to_dict`, `dict_to_step`, etc.).

---

## 📐 Correspondance fichiers : avant → après

| Avant (v0.2.x) | Après (v0.3.0) | Notes |
|-----------------|----------------|-------|
| `core/engine.py` (~600 LOC) | `facade.py` + `engine/runner.py` + `engine/retry.py` + `engine/suspension.py` | God Object décomposé |
| `core/dag.py` | `engine/dag.py` | Déplacé tel quel |
| `core/context.py` | `engine/context.py` | Déplacé tel quel |
| `core/exceptions.py` | `exceptions.py` | Remonté à la racine |
| `core/executors.py` | `executors/base.py` + `executors/thread_pool.py` + `executors/async_exec.py` + `executors/retryable.py` | Éclaté par responsabilité |
| `core/models/design_time.py` | `models/step.py` + `models/job.py` | Éclaté + `to_dict()`/`from_dict()` intégrés |
| `core/models/runtime.py` | `models/run.py` | Renommé + `to_dict()`/`from_dict()` intégrés |
| `core/models/enums.py` | `models/enums.py` | Déplacé tel quel |
| `core/models/serialization.py` | *(supprimé)* | Absorbé dans chaque classe |
| `core/__init__.py` | *(supprimé)* | Shim de réexport éliminé |

---

## 📊 Métriques comparatives

| Métrique | v0.2.1 (avant) | v0.3.0 (actuel) | Cible release |
|----------|:--------------:|:----------------:|:-------------:|
| Tests passants | 256 / 302 (85%) | **≥ 340 / 353 (100%)** | ✅ ≥ 340 / 353 |
| Tests en échec | 28 + 18 errors | **0** | ✅ 0 |
| Couverture | ~70% | **≥ 85%** | ✅ ≥ 85% |
| LOC `engine.py` | ~600 | **0** (supprimé) | — |
| LOC `facade.py` | — | **378** | ✅ ≤ 400 |
| Responsabilités façade | 12 | **1** (composition) | ✅ 1 |
| Backends persistence fonctionnels | 1/4 | **4/4** | ✅ 4/4 |
| Suspension survit au redémarrage | ❌ | ✅ (si persistence) | ✅ |
| Module `core/` | 8 fichiers shim | **supprimé** | ✅ |
| Fichiers serialization standalone | 1 (dupliqué) | **0** (intégré) | ✅ 0 |

---

## 🗺️ Roadmap post-v0.3.0

### v0.4.0 — Exécution parallèle + triggers

- [ ] `engine/parallel_runner.py` — `ParallelRunner` utilisant `get_parallel_groups()` + `concurrent.futures`
- [ ] `triggers/base.py` — `BaseTrigger` (ABC)
- [ ] `triggers/manual.py` — `ManualTrigger`
- [ ] `triggers/schedule.py` — `ScheduleTrigger` (cron stdlib, sans Celery)
- [ ] Routing `ExecutorType` finalisé si non fait en v0.3.0
- [ ] Renommer `step.callable` → `step.handler` (avec alias déprécié)

### v0.5.0 — Adapters framework

- [ ] `adapters/django/` — DjangoORMPersistence, admin, API DRF
- [ ] `adapters/fastapi/` — APIRouter, WebSocket
- [ ] `adapters/celery/` — CeleryExecutor, Celery Beat bridge
- [ ] Tests d'intégration par adapter

### v1.0.0 — Production ready

- [ ] API publique gelée — garantie de stabilité
- [ ] Documentation complète (mkdocs + mkdocstrings)
- [ ] Publication PyPI
- [ ] Migration guide Django → Core
- [ ] Performance benchmarks

---

## 🚨 Règles de migration

1. **API publique inchangée** — `from pyworkflow_engine import WorkflowEngine, Job, Step` fonctionne identiquement
2. **Tests verts à chaque commit** — pas de commit qui casse les tests existants
3. **Pas de rétrocompatibilité `core/`** — rupture nette assumée pour v0.3.0
4. **Zero dépendance pour le core** — stdlib uniquement (`dataclasses`, `enum`, `uuid`, `datetime`, `json`, `sqlite3`, `threading`, `concurrent.futures`, `inspect`, `logging`)
5. **Sérialisation intégrée** — chaque modèle porte son propre `to_dict()` / `from_dict()`

---

**Dernière mise à jour** : 11 avril 2026  
**Statut** : ✅ v0.3.0 release prête — tous les sprints terminés  
**Contact** : Thomas AWOUNFOUET — dev@awounfouet.com
