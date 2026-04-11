# ADR-003 — Intégration de l'analyse critique dans le plan de refactoring architectural

> **Date :** 10 avril 2026  
> **Statut :** ✅ Implémentée — v0.3.0 (11 avril 2026)  
> **Type :** Architecture Decision Record (ADR)  
> **Dépend de :** ADR-002 (refactoring architectural)

---

## Contexte

L'analyse critique (`docs/architecture_critique.md`) a identifié 8 problèmes architecturaux, 6 dettes techniques secondaires, et formulé 8 recommandations (R1-R8) + 3 décisions à prendre (D1-D3).

Ce document évalue chaque point de l'analyse, confirme ou nuance sa sévérité après vérification du code source réel, et l'intègre au plan de migration de l'ADR-002.

---

## 1. Validation des problèmes critiques

### 🔴 Problème 1 — Backends SQLite / SQLAlchemy désynchronisés

**Verdict : ✅ CONFIRMÉ — critique**

Vérification du code source réel :

| Backend | Méthode | Code cassé | Champ modèle réel |
|---------|---------|-----------|-------------------|
| `sqlite.py:186` | `_serialize_job()` | `job.parameters` | ❌ `Job` n'a pas de `parameters` |
| `sqlite.py:195` | `_serialize_job()` | `step.type`, `step.function`, `step.parameters`, `step.depends_on` | ❌ C'est `step.step_type`, `step.callable`, `step.config`, `step.dependencies` |
| `sqlite.py:255` | `_deserialize_job_run()` | `JobRunStatus(row["status"])` | ❌ `JobRunStatus` n'existe pas, c'est `RunStatus` |
| `sqlite.py:240` | `_serialize_job_run()` | `job_run.id`, `job_run.started_at`, `job_run.completed_at`, `job_run.parameters` | ❌ C'est `job_run.job_run_id`, `job_run.start_time`, `job_run.end_time` ; `parameters` n'existe pas |
| `sqlite.py:307` | `_deserialize_step_run()` | `StepRunStatus(row["status"])` | ❌ `StepRunStatus` n'existe pas |
| `sqlite.py:308` | `_deserialize_step_run()` | `id=`, `started_at=`, `completed_at=`, `error_message=` | ❌ C'est `step_run_id`, `start_time`, `end_time`, `error` |
| `sqlalchemy.py:246` | `_serialize_job()` | Mêmes problèmes que sqlite | ❌ Identique |
| `sqlalchemy.py:296` | `_deserialize_job_run()` | `JobRunStatus`, `id=`, `started_at=`, `completed_at=`, `parameters=` | ❌ Identique |
| `sqlalchemy.py:328` | `_deserialize_step_run()` | `StepRunStatus`, `id=`, `started_at=`, `completed_at=`, `error_message=` | ❌ Identique |

**JSON File** (`json_file.py`) est le **seul backend correctement synchronisé** avec les modèles actuels. Sa sérialisation utilise les bons noms de champs (`step_type`, `callable`, `dependencies`, `start_time`, `end_time`, etc.).

> **Nuance par rapport à l'analyse :** L'analyse critique disait que `JSONFilePersistence` était cassé. En réalité, après vérification, `json_file.py` est **correctement synchronisé** avec les modèles. C'est SQLite et SQLAlchemy qui sont cassés.

**Intégration ADR-002 :** Phase 1, priorité critique.

---

### 🔴 Problème 2 — `InMemoryPersistence.export_data()` / `import_data()` cassés

**Verdict : ⚠️ PARTIELLEMENT CONFIRMÉ**

Après vérification, `memory.py` **ne contient pas** de méthodes `export_data()` ni `import_data()`. Ces méthodes n'existent tout simplement pas dans l'implémentation actuelle.

L'analyse critique faisait probablement référence à une version antérieure du code ou à un plan non implémenté. Le problème réel est donc :

- **Pas de fonctionnalité d'export/import** plutôt que des "méthodes cassées"
- `to_dict()` / `from_dict()` n'existent pas sur les modèles — c'est le vrai manque

**Intégration ADR-002 :** Phase 1 → `models/serialization.py`.

---

### 🔴 Problème 3 — `engine.run()` ne persiste pas automatiquement

**Verdict : ✅ CONFIRMÉ mais nuancé**

Le code actuel de `engine.py` montre que :
- `run()` ne sauvegarde **jamais** dans la persistence — confirmé
- `run_with_persistence()` **existe et fonctionne** — il sauvegarde après exécution
- Le pattern est donc : `run()` = sans persistence, `run_with_persistence()` = avec

C'est un choix de design valable (explicite > implicite), mais :
1. Il n'est **pas documenté** que `run()` ne persiste pas
2. Il est **contre-intuitif** de configurer un backend de persistence et que `run()` l'ignore
3. Les **checkpoints intermédiaires** ne sont pas sauvegardés même dans `run_with_persistence()` — seul l'état final est persisté

**Recommandation :** Plutôt que de modifier `run()`, documenter clairement le contrat et ajouter des checkpoints dans `run_with_persistence()`.

**Intégration ADR-002 :** Phase 2 → `engine/runner.py` avec callback de checkpoint.

---

### 🔴 Problème 4 — Suspension en mémoire uniquement

**Verdict : ✅ CONFIRMÉ — critique**

```python
# engine.py — confirmé
self._suspended_workflows: Dict[str, JobRun] = {}  # ← dict in-memory
```

La suspension n'utilise jamais la persistence. C'est incompatible avec les use cases de human approval.

**Intégration ADR-002 :** Phase 2 → `engine/suspension.py` avec `SuspensionManager` persistence-aware.

---

### 🟡 Problème 5 — Exécution parallèle calculée mais non utilisée

**Verdict : ✅ CONFIRMÉ**

`DAGResolver.get_parallel_groups()` existe et est testé, mais `engine.py` utilise uniquement `get_execution_order()` (linéaire).

**Intégration ADR-002 :** Phase 3 (pas bloquant). L'ADR-002 propose de garder l'exécution séquentielle dans `runner.py` et d'ajouter un `ParallelRunner` optionnel plus tard.

---

### 🟡 Problème 6 — `co_argcount` fragile

**Verdict : ✅ CONFIRMÉ**

```python
# engine.py:409 — confirmé
if step.callable.__code__.co_argcount > 0:
```

Casse avec `partial`, méthodes de classe, `*args/**kwargs`.

**Intégration ADR-002 :** Phase 3 → `executors/function.py` avec `inspect.signature()`.

---

### 🟡 Problème 7 — `ExecutorType` non routé

**Verdict : ✅ CONFIRMÉ**

`ExecutorType` est déclaré dans les enums et sur chaque `Step`, mais le routing dans `engine.py` se fait via `step_type` (pour les callables standard) ou `executor_name` (pour le registry). L'enum `ExecutorType` n'influence aucune décision.

**Intégration ADR-002 :** Phase 4 → routing dans `facade.py`.

---

### 🟡 Problème 8 — Retry implémenté deux fois

**Verdict : ✅ CONFIRMÉ**

- `engine.py:_retry_step_execution()` — retry simple avec `time.sleep`
- `executors.py:RetryableExecutor` — retry avec backoff exponentiel et jitter

Les deux peuvent s'activer en cascade.

**Intégration ADR-002 :** Phase 2 → `engine/retry.py` unifie les deux.

---

## 2. Validation des dettes techniques secondaires

| # | Problème | Verdict | Commentaire |
|---|----------|---------|-------------|
| `demo_rejection_flow()` accède à des attributs privés inexistants | ⚠️ **À re-vérifier** — `_job_runs`, `resume_workflow()`, `get_step_output()` non trouvés dans `human_approval.py` actuel. Le fichier a peut-être été corrigé depuis l'analyse. |
| Pas de versioning des jobs à la persistence | ✅ Confirmé — `Job.version` existe mais n'est pas utilisé lors du save |
| `cleanup_old_runs` signature incohérente (LSP) | ✅ Confirmé — `SQLitePersistence.cleanup_old_runs(older_than)` manque `dry_run` |
| `step.callable` nom réservé | ✅ Confirmé — collision avec builtin `callable()` |
| Pas de tests d'intégration formels | ✅ Confirmé — `tests/integration/` est vide |
| `sys.getsizeof` sous-estime la mémoire | ⚠️ Non applicable — `_estimate_memory_usage()` non trouvé dans `memory.py` actuel |
| `JobRunStatus` référencé dans exemples | ✅ **NOUVEAU** — `examples/persistence_backends.py:265` importe `JobRunStatus` qui n'existe pas |

---

## 3. Consolidation des exemples cassés

Les exemples suivants utilisent l'ancien modèle et sont **non fonctionnels** :

| Fichier | Problème | Priorité |
|---------|----------|----------|
| `examples/persistence_backends.py:168-239` | `Job(parameters=..., steps=[Step(type=..., function=..., depends_on=set())])` — ancienne API | 🔴 Critique |
| `examples/persistence_backends.py:265` | `JobRunStatus.COMPLETED` → n'existe pas, c'est `RunStatus.SUCCESS` | 🔴 Critique |
| `examples/persistence_backends.py:330` | `Step(type=..., function=..., depends_on=set())` — ancienne API | 🔴 Critique |
| `examples/persistence_backends.py:421` | Même problème avec SQLAlchemy demo | 🔴 Critique |

---

## 4. Mapping : Recommandations R1-R8 → Phases ADR-002

| Recommandation | Description | Phase ADR-002 | Composant cible |
|:-:|-------------|:---:|----------------|
| R1 | Corriger backends SQLite/SQLAlchemy | **Phase 1** | `persistence/sqlite.py`, `persistence/sqlalchemy.py` |
| R2 | Implémenter `serialization.py` | **Phase 1** | `models/serialization.py` (nouveau) |
| R3 | Persister automatiquement dans `run()` | **Phase 2** | `engine/runner.py` — callback checkpoint |
| R4 | Suspension durable via persistence | **Phase 2** | `engine/suspension.py` (nouveau) |
| R5 | Remplacer `co_argcount` par `inspect.signature()` | **Phase 3** | `executors/function.py` (nouveau) |
| R6 | Unifier la stratégie de retry | **Phase 2** | `engine/retry.py` (nouveau) |
| R7 | Corriger `cleanup_old_runs` LSP | **Phase 4** | `persistence/sqlite.py` |
| R8 | Renommer `step.callable` → `step.handler` | **Phase 4** | `models/step.py` |

---

## 5. Mapping : Décisions D1-D3 → Position recommandée

### D1 — Stratégie de sérialisation des callables

**Position recommandée : Option A (ne pas persister les callables)**

Justification :
- Le callable n'est pas sérialisable de manière portable
- L'option B (chemin `module.function`) est fragile et crée un couplage au refactoring
- L'option C (registry Celery-style) est une sur-architecture pour ce stade du projet
- Le `json_file.py` actuel fait déjà `"callable": str(step.callable) if step.callable else None` — une approche raisonnable pour le debug mais pas pour la reconstruction

**Implémentation dans l'ADR-002 :**
- `models/serialization.py` sérialise tout sauf les callables
- À la désérialisation, `Step.callable` est `None` — le job doit être reconstruit depuis le code
- Documenter cette limitation dans les guides de persistence

---

### D2 — Exécution parallèle : à quel niveau ?

**Position recommandée : Option B (documentée) → puis Option A (automatique) en v0.4**

Justification :
- L'exécution parallèle automatique introduit des complexités de contexte (thread-safety du `WorkflowContext`, ordering des résultats)
- Le `DAGResolver.get_parallel_groups()` est prêt côté calcul
- Mieux vaut stabiliser le runner séquentiel d'abord (Phase 2), puis ajouter un `ParallelRunner` dans une release ultérieure

**Implémentation dans l'ADR-002 :**
- Phase 2 : `engine/runner.py` — `SequentialRunner` (comportement actuel)
- Futur v0.4 : `engine/parallel_runner.py` — `ParallelRunner` utilisant `get_parallel_groups()` + `concurrent.futures`

---

### D3 — Scope de l'engine : singleton ou instance ?

**Position recommandée : Option B (état entièrement dans la persistence)**

Justification :
- L'ADR-002 crée déjà `SuspensionManager` qui est persistence-aware
- Si toute la state est dans la persistence, l'engine devient stateless → naturellement scalable
- Pas besoin de singleton ni de factory complexe
- Pour le fallback sans persistence (dev/tests), le dict in-memory dans `SuspensionManager` suffit

**Implémentation dans l'ADR-002 :**
- Phase 2 : `engine/suspension.py` — persistence-first, mémoire en fallback
- `facade.py` (`WorkflowEngine`) n'a plus de `_suspended_workflows` propre

---

## 6. Problèmes identifiés par l'analyse critique mais ABSENTS de l'ADR-002

Les éléments suivants manquent dans le plan de migration actuel et doivent être ajoutés :

### 6.1 Corriger les exemples cassés (Phase 1)

```
- [ ] Réécrire examples/persistence_backends.py avec les modèles actuels
- [ ] Remplacer JobRunStatus → RunStatus
- [ ] Remplacer Step(type=, function=, depends_on=set()) → Step(step_type=, callable=, dependencies=[])
- [ ] Remplacer Job(parameters=...) → Job(metadata=...) ou supprimer
```

### 6.2 Ajouter des tests d'intégration round-trip (Phase 1)

```python
# tests/integration/test_persistence_roundtrip.py

@pytest.mark.parametrize("backend", [
    InMemoryPersistence(),
    JSONFilePersistence(tmp_path),
    SQLitePersistence(":memory:"),
])
def test_save_and_retrieve_job(backend, sample_job):
    """Vérifie que save → get produit un job équivalent."""
    backend.save_job(sample_job)
    retrieved = backend.get_job(sample_job.name)
    assert retrieved.name == sample_job.name
    assert len(retrieved.steps) == len(sample_job.steps)

def test_full_lifecycle(backend, sample_job):
    """Vérifie le cycle engine.run → persist → retrieve → vérifier."""
    engine = WorkflowEngine(persistence=backend)
    job_run = engine.run_with_persistence(sample_job)
    retrieved = backend.get_job_run(job_run.job_run_id)
    assert retrieved.status == job_run.status
```

### 6.3 Documenter le contrat `run()` vs `run_with_persistence()` (Phase 2)

Le comportement actuel (non documenté) est en fait un bon design :
- `run()` = exécution pure, sans side-effect de persistence — idéal pour tests et scripts
- `run_with_persistence()` = exécution + sauvegarde — pour production

Mais cela doit être **explicitement documenté** dans les docstrings et les guides.

---

## 7. Score architectural post-correction (projection)

| Critère | Avant | Après Phase 1 | Après Phase 2 | Après Phase 4 |
|---------|:-----:|:-------------:|:-------------:|:-------------:|
| Cohérence API | 5/10 | **8/10** | 8/10 | 9/10 |
| Complétude fonctionnelle | 4/10 | **7/10** | 8/10 | 9/10 |
| Testabilité | 7/10 | **8/10** | 9/10 | 9/10 |
| Production-readiness | 3/10 | **5/10** | **7/10** | **8/10** |
| **Moyenne** | **6.3/10** | **7.0/10** | **8.0/10** | **8.5/10** |

---

## 8. Conclusion

L'analyse critique est **rigoureuse et précise à ~90%**. Les nuances identifiées :

1. **`json_file.py` n'est PAS cassé** — contrairement à ce que l'analyse indiquait. Il est correctement synchronisé avec les modèles actuels. Seuls `sqlite.py` et `sqlalchemy.py` sont cassés.

2. **`export_data()`/`import_data()` n'existent pas** dans `memory.py` actuel — le problème est l'absence de fonctionnalité, pas des méthodes cassées.

3. **`demo_rejection_flow()`** — les attributs fantômes mentionnés n'ont pas été retrouvés dans le fichier actuel. Le fichier a possiblement été corrigé entre l'analyse et cette revue.

4. **`_estimate_memory_usage()`** — non trouvé dans `memory.py` actuel.

Toutes les recommandations R1-R8 s'intègrent naturellement dans les 4 phases de l'ADR-002. Les décisions D1-D3 sont tranchées ci-dessus. Le plan de migration est complet et prêt à être exécuté.
