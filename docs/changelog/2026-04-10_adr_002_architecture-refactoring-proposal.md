# ADR-002 — Proposition de refactoring architectural : de `core/` monolithique vers une architecture modulaire en couches

> **Date :** 10 avril 2026  
> **Statut :** ✅ Implémentée — v0.3.0 (11 avril 2026)  
> **Type :** Architecture Decision Record (ADR)  
> **Scope :** Reorganisation interne du package — API publique inchangée

---

## Contexte

La revue architecturale du 10 avril 2026 (`docs/architecture_critique.md`) a identifié un problème central :  
**[`WorkflowEngine`](../../src/pyworkflow_engine/core/engine.py) est un God Object** (~600 lignes, ~12 responsabilités distinctes).

Structure actuelle :

```
src/pyworkflow_engine/
├── core/
│   ├── models/
│   │   ├── design_time.py   # Job + Step + SubJob
│   │   ├── runtime.py       # JobRun + StepRun + StepLog
│   │   └── enums.py
│   ├── engine.py            # ← God Object (orchestration + retry + suspension + persistence + validation + logging)
│   ├── dag.py
│   ├── context.py
│   ├── executors.py         # BaseExecutor + ThreadPool + RetryableExecutor + Timeout — tout ensemble
│   └── exceptions.py
├── persistence/
│   ├── base.py
│   ├── memory.py
│   ├── json_file.py         # ⚠️ cassé — modèle désynchronisé
│   └── sqlite.py            # ⚠️ cassé — modèle désynchronisé
└── logging/
```

---

## Problèmes identifiés

### 🔴 Critiques (bloquants)

| # | Problème | Fichier | Impact |
|---|----------|---------|--------|
| 1 | `WorkflowEngine` a ~12 responsabilités | `engine.py` | Maintenabilité, testabilité, SRP violé |
| 2 | Suspension stockée en mémoire uniquement | `engine.py` | Workflows suspendus perdus au redémarrage |
| 3 | Backends `json_file.py` et `sqlite.py` cassés | `persistence/` | `AttributeError` à l'exécution |
| 4 | `models/` sans `serialization.py` | `core/models/` | `to_dict()`/`from_dict()` inexistants |

### 🟡 Secondaires

| # | Problème | Impact |
|---|----------|--------|
| 5 | Retry implémenté deux fois (`engine.py` + `RetryableExecutor`) | Comportement non déterministe |
| 6 | Détection de signature via `co_argcount` | Casse avec `partial`, méthodes de classe, `*args` |
| 7 | `ExecutorType` déclaré mais non routé | Métadonnée sans effet |
| 8 | `executors.py` mélange base, thread, retry, timeout | SRP violé |

---

## Architecture proposée

### Principe retenu : **Modular Layered Architecture**

> Ni DDD (sur-architecturé pour une base de code < 10K lignes, 1 développeur),  
> ni monolithe `core/` (sous-architecturé, God Object).  
> Une architecture en **couches fonctionnelles** à responsabilité unique.

### Structure cible

```
src/pyworkflow_engine/
│
├── models/                        # 🔵 COUCHE DOMAINE — ce qui EST
│   ├── __init__.py
│   ├── enums.py                   # RunStatus, StepType, ExecutorType (inchangé)
│   ├── step.py                    # Step (design-time, frozen dataclass)
│   ├── job.py                     # Job, SubJob (design-time, frozen dataclass)
│   ├── step_run.py                # StepRun, StepLog (runtime, mutable dataclass)
│   ├── job_run.py                 # JobRun (runtime, mutable dataclass)
│   └── serialization.py           # ← NOUVEAU : to_dict / from_dict (corrige les backends)
│
├── engine/                        # 🟢 COUCHE ORCHESTRATION — ce qui FAIT
│   ├── __init__.py
│   ├── runner.py                  # ← EXTRAIT : WorkflowRunner (exécution pure, sans retry ni persistence)
│   ├── dag.py                     # DAGResolver (déplacé de core/, API inchangée)
│   ├── context.py                 # WorkflowContext (déplacé de core/, API inchangée)
│   ├── retry.py                   # ← EXTRAIT : RetryHandler (unifie les 2 implémentations actuelles)
│   └── suspension.py              # ← EXTRAIT : SuspensionManager (persistence-aware)
│
├── executors/                     # 🟠 COUCHE EXÉCUTION — COMMENT exécuter
│   ├── __init__.py
│   ├── base.py                    # BaseExecutor, ExecutorRegistry (extrait de core/executors.py)
│   ├── function.py                # FunctionStepExecutor (logique de _execute_function_step)
│   ├── thread_pool.py             # ThreadPoolStepExecutor
│   ├── timeout.py                 # TimeoutExecutor (extrait de engine.py._execute_with_timeout)
│   └── subprocess.py             # SubprocessExecutor (futur)
│
├── persistence/                   # 🔴 COUCHE STOCKAGE — OÙ persister (inchangé structurellement)
│   ├── __init__.py
│   ├── base.py                    # BasePersistence (ABC)
│   ├── memory.py                  # InMemoryPersistence ✅ fonctionnel
│   ├── json_file.py               # ← À CORRIGER : resynchroniser avec models/
│   └── sqlite.py                  # ← À CORRIGER : resynchroniser avec models/
│
├── triggers/                      # 🟣 COUCHE DÉCLENCHEMENT — QUAND lancer (futur)
│   ├── __init__.py
│   └── base.py                    # BaseTrigger (interface)
│
├── exceptions.py                  # Toutes les exceptions (flat, inchangé)
├── logging/                       # Logging (inchangé)
├── facade.py                      # ← NOUVEAU : WorkflowEngine (façade unifiée, API publique inchangée)
└── __init__.py                    # Exports publics (inchangé côté utilisateur)
```

---

## Détail des nouveaux composants

### `engine/runner.py` — Responsabilité unique : exécuter des steps

```python
class WorkflowRunner:
    """Exécute les steps d'un workflow dans l'ordre topologique.

    Responsabilité unique : orchestrer l'appel aux executors.
    Pas de retry, pas de persistence, pas de suspension.
    """
    def execute(
        self,
        job: Job,
        job_run: JobRun,
        context: WorkflowContext,
        execution_order: list[str],
    ) -> None: ...
```

### `engine/retry.py` — Unification des 2 implémentations actuelles

```python
class RetryHandler:
    """Gère les tentatives de réexécution.

    Remplace à la fois engine._retry_step_execution() et RetryableExecutor,
    évitant les cascades de retry non documentées.
    """
    def attempt(
        self,
        step: Step,
        step_run: StepRun,
        context: WorkflowContext,
        execute_fn: Callable,
    ) -> bool: ...
```

### `engine/suspension.py` — Suspension persistence-aware

```python
class SuspensionManager:
    """Gère la suspension et reprise des workflows.

    Si un backend de persistence est fourni, l'état suspendu
    est sauvegardé — permettant la reprise après redémarrage.
    Sinon, fallback sur un dict en mémoire (comportement actuel).
    """
    def suspend(self, job_run: JobRun, reason: str) -> None: ...
    def get_suspended(self, run_id: str) -> JobRun | None: ...
    def remove(self, run_id: str) -> None: ...
```

### `facade.py` — API publique inchangée

```python
class WorkflowEngine:
    """Façade unifiée — point d'entrée unique pour l'utilisateur.

    Compose WorkflowRunner + RetryHandler + SuspensionManager.
    L'utilisateur ne voit aucun changement dans son code.
    """
    def __init__(self, persistence=None): ...
    def run(self, job, initial_context=None, run_id=None) -> JobRun: ...
    def resume(self, run_id, step_outputs=None) -> JobRun: ...
    def cancel(self, run_id) -> bool: ...
    # ... (API identique à aujourd'hui)
```

---

## Pourquoi pas DDD ?

| Critère DDD | État du projet |
|-------------|---------------|
| Équipe multi-développeurs | Non — 1 développeur |
| Bounded contexts indépendants | Non — `Job`/`Step`/`DAG` sont intrinsèquement couplés |
| > 20K lignes de code | Non — 7K lignes |
| Domaines métier distincts | Non — le domaine est unique : orchestration |
| Post-v1.0 stable | Non — v0.2, pré-alpha |

Un découpage DDD avec `jobs/`, `steps/`, `dag/` comme bounded contexts séparés **forcerait des imports croisés** entre domaines et ajouterait de la complexité sans gain de maintenabilité.

---

## Plan de migration

> ⚠️ **Règle d'or** : l'API publique (`__init__.py`) reste **strictement identique** tout au long de la migration. L'utilisateur ne change rien.

### Phase 1 — Fondations (priorité haute, ~2j)

- [ ] Créer `models/serialization.py` avec `to_dict` / `from_dict` pour `Job`, `Step`, `JobRun`, `StepRun`
- [ ] Corriger `persistence/json_file.py` et `persistence/sqlite.py` (resynchroniser avec les models actuels)
- [ ] Corriger `persistence/memory.py` — `export_data()` / `import_data()` (appels à des méthodes inexistantes)

### Phase 2 — Découpage du God Object (priorité haute, ~3j)

- [ ] Créer `engine/runner.py` — extraire `_execute_steps()` et `_execute_step()` de `engine.py`
- [ ] Créer `engine/retry.py` — extraire `_retry_step_execution()` et supprimer le doublon dans `RetryableExecutor`
- [ ] Créer `engine/suspension.py` — extraire `_suspended_workflows` + logique resume
- [ ] Réduire `engine.py` à une façade de ~100 lignes (`facade.py`)

### Phase 3 — Refactoring executors (priorité moyenne, ~1j)

- [ ] Éclater `core/executors.py` → `executors/base.py`, `executors/function.py`, `executors/thread_pool.py`, `executors/timeout.py`
- [ ] Corriger la détection de signature (`co_argcount` → `inspect.signature()`)

### Phase 4 — Cleanup (priorité basse, ~0.5j)

- [ ] Renommer `step.callable` → `step.handler` (évite la collision avec la builtin `callable()`)
- [ ] Implémenter le routing de `ExecutorType` dans `facade.py`
- [ ] Corriger `cleanup_old_runs` dans `SQLitePersistence` (LSP violation)

---

## Métriques de succès

| Métrique | Avant | Cible |
|----------|:-----:|:-----:|
| Lignes dans `engine.py` | ~600 | < 120 (façade) |
| Responsabilités de `WorkflowEngine` | ~12 | 1 (composition) |
| Backends persistence fonctionnels | 1/4 | 4/4 |
| Workflows suspendus survivent au redémarrage | ❌ | ✅ (si persistence configurée) |
| Tests passants | 185 | ≥ 185 (0 régression) |

---

## Conséquences

- **Aucun changement d'API publique** — code utilisateur 100% compatible.
- **Meilleure testabilité** — chaque composant peut être testé en isolation.
- **Backends de persistence réparés** — SQLite et JSON File deviennent fonctionnels.
- **Suspension durable** — les workflows suspendus survivent aux redémarrages si un backend est configuré.
- **Retry déterministe** — une seule implémentation, comportement prévisible.
