# Analyse critique de l'architecture — `pyworkflow-engine`

> **Date :** 10 avril 2026  
> **Portée :** Analyse objective des forces, faiblesses, risques et recommandations architecturales  
> **Périmètre :** Code source v0.2.1, 24 modules, 185+ tests

---

## Préambule

Cette analyse vise à évaluer honnêtement les choix architecturaux du projet, identifier les dettes techniques tangibles, et proposer des améliorations concrètes. Elle distingue les problèmes **bloquants** des problèmes **non urgents** pour guider les priorités.

---

## 1. Ce qui fonctionne bien

### ✅ La séparation Design-Time / Runtime est excellente

L'utilisation de dataclasses `frozen=True` pour les modèles de définition (`Job`, `Step`) et de dataclasses mutables pour les modèles d'exécution (`JobRun`, `StepRun`) est un choix architectural solide. Elle garantit que les définitions de workflows sont immuables, thread-safe à la lecture, et réutilisables entre plusieurs exécutions sans risque d'effets de bord.

### ✅ L'algorithme DAG est correct et bien découplé

Le `DAGResolver` utilise les algorithmes classiques (Kahn pour le tri topologique, DFS coloré pour la détection de cycles), et est proprement découplé de l'engine. Son API est riche : `get_parallel_groups()`, `get_critical_path()`, `get_ready_steps()`, ce qui anticipe de futurs besoins comme l'exécution parallèle.

### ✅ La hiérarchie d'exceptions est bien conçue

La hiérarchie complète (`WorkflowError` → `WorkflowExecutionError` → `StepExecutionError`…) avec des sous-types pour la suspension (`WorkflowSuspended`, `WorkflowSuspendedHuman`, `WorkflowSuspendedExternal`) est un vrai atout. Elle permet une gestion fine des erreurs sans recourir à des codes de retour ou à l'inspection de chaînes.

### ✅ Le système de logging est conforme aux best practices Python

Conforme PEP 282 : NullHandler par défaut, namespace hiérarchique, `configure_logging()` optionnel. La library est silencieuse par défaut, ce qui est impératif pour un package distribué.

### ✅ Le contrat `BaseStorage` est solide

L'interface abstraite est complète (CRUD, filtres, pagination, transactions, health check, statistiques). Elle permet de switcher de backend sans changer le code métier.

---

## 2. Problèmes architecturaux critiques

### 🔴 Problème 1 : Les backends de persistance décrivent un modèle différent de celui du Core

C'est le problème **le plus grave** du projet. En examinant `sqlite.py`, les méthodes de sérialisation/désérialisation référencent des champs qui n'existent **pas** dans les modèles actuels :

```python
# sqlite.py — _serialize_job() — CASSÉ
"parameters": json.dumps(job.parameters),  # Job n'a pas de champ `parameters`
"steps": ..., "type": step.type,  # Step n'a pas de champ `type`
"function": step.function,        # Step n'a pas de champ `function`
"depends_on": list(step.depends_on),  # c'est `dependencies`, pas `depends_on`

# _deserialize_job_run() — CASSÉ
status=JobRunStatus(row["status"]),  # JobRunStatus n'existe pas, c'est RunStatus
started_at=...,  # JobRun n'a pas de champ `started_at`, c'est `start_time`
completed_at=...,  # même chose, c'est `end_time`

# _deserialize_step_run() — CASSÉ
status=StepRunStatus(row["status"]),  # StepRunStatus n'existe pas
```

**Conséquence :** `SQLiteStorage` et `JSONFileStorage` sont **non fonctionnels**. L'appel à n'importe quelle méthode de sérialisation lèvera un `AttributeError`. Seul `InMemoryStorage` fonctionne réellement.

**Origine :** Le code des backends semble avoir été généré ou rédigé à partir d'une version **antérieure** du modèle (pré-migration `ias_workflow_engine`), sans être mis à jour après le renommage et le refactoring des champs.

---

### 🔴 Problème 2 : `InMemoryStorage.export_data()` appelle des méthodes inexistantes

```python
# memory.py — export_data()
"jobs": [job.to_dict() for job in self._jobs.values()],       # to_dict() n'existe pas sur Job
"job_runs": [run.to_dict() for run in self._job_runs.values()],  # idem sur JobRun
```

Et dans `import_data()` :
```python
job = Job.from_dict(job_data)    # from_dict() n'existe pas sur Job
job_run = JobRun.from_dict(...)  # idem
```

Ces méthodes de sérialisation ne sont ni définies sur les dataclasses, ni dans les modules de sérialisation (qui sont vides). La fonctionnalité d'import/export de `InMemoryStorage` est donc également **cassée**.

---

### 🔴 Problème 3 : L'engine n'est pas intégré à la persistance lors de `run()`

La méthode principale `engine.run()` ne sauvegarde **jamais** le `JobRun` dans la persistance. La seule façon de persister est via `run_with_storage()` (mentionnée dans le CHANGELOG mais absente du code de `engine.py` analysé). Le développeur doit appeler manuellement `engine.save_job_run(job_run)` après chaque exécution — ce qui n'est pas documenté et très facile à oublier.

```python
# engine.py — run() — pas de sauvegarde automatique
job_run.complete_success()
# ← ICI : aucun appel à self._persistence.save_job_run(job_run)
return job_run
```

**Conséquence attendue :** Un utilisateur qui configure un backend SQLite pensera que ses runs sont persistés — ils ne le seront pas.

---

### 🔴 Problème 4 : La suspension ne permet pas de reprise réelle sans état en mémoire

Le mécanisme de suspension stocke les workflows suspendus dans `self._suspended_workflows` — **un dictionnaire en mémoire de l'instance de l'engine**. Cela signifie que :

1. La persistance n'est pas utilisée pour sauvegarder l'état suspendu
2. Si l'application redémarre, tous les workflows suspendus sont **perdus**
3. Il est **impossible** de reprendre un workflow suspendu depuis une autre instance de l'engine (pas de distribution possible)

Pour un vrai workflow de type "human approval" (cas d'usage central du projet), c'est une limitation fondamentale qui rend la feature inutilisable en production.

---

### 🟡 Problème 5 : L'exécution parallèle est calculée mais jamais utilisée

Le `DAGResolver` est capable de calculer les groupes de steps pouvant s'exécuter en parallèle (`get_parallel_groups()`), mais le `WorkflowEngine` les **ignore complètement**. Il exécute toujours les steps strictly séquentiellement dans l'ordre topologique :

```python
# engine.py — _execute_steps() — toujours séquentiel
for step_name in execution_order:       # ordre linéaire
    ...
    result = self._execute_step(step, context)  # bloquant
```

La promesse d'exécution concurrente via `ThreadPoolStepExecutor` ou `ProcessPoolStepExecutor` ne peut donc être tenue que manuellement, pas au niveau du DAG.

---

### 🟡 Problème 6 : La détection de signature par `co_argcount` est fragile

L'engine utilise `step.callable.__code__.co_argcount` pour détecter si une fonction attend un contexte en argument. C'est une introspection de bas niveau qui casse dans au moins 4 cas courants :

```python
# Cas 1 : méthodes de classe (self est compté)
class MyTask:
    def run(self):  # co_argcount == 1 → l'engine passe le contexte → TypeError

# Cas 2 : fonctions avec *args/**kwargs
def my_step(*args, **kwargs):  # co_argcount == 0 → pas de contexte → ok mais trompeur

# Cas 3 : lambdas
step_fn = lambda: {"result": 42}  # co_argcount == 0 → ok

# Cas 4 : partial ou functools.wraps
from functools import partial
step_fn = partial(my_func, extra_arg)  # AttributeError: partial n'a pas __code__
```

L'approche correcte serait d'utiliser `inspect.signature()` ou de définir un protocole explicite (par exemple, un paramètre optionnel nommé `context`).

---

### 🟡 Problème 7 : L'`ExecutorType` est défini mais jamais routé

L'enum `ExecutorType` (LOCAL, THREAD, PROCESS, ASYNC, CELERY…) est déclaré sur chaque `Step`, mais l'engine ne l'utilise jamais pour sélectionner automatiquement l'executor correspondant. Le seul routing se fait via `step.executor_name` (chaîne libre) vers le `ExecutorRegistry`. L'enum sert donc uniquement de métadonnée sans effet opérationnel.

---

### 🟡 Problème 8 : Retry implémenté deux fois de manière différente

La logique de retry existe à **deux niveaux distincts**, sans coordination :

1. **Dans `engine.py` (`_retry_step_execution`)** — retry simple basé sur `step.retry_count` et `step.retry_delay`, implémenté avec une boucle `for` et `time.sleep`
2. **Dans `executors.py` (`RetryableExecutor`)** — retry avancé avec backoff exponentiel, jitter, et liste d'exceptions filtrables

Si un step utilise un `RetryableExecutor` ET a `retry_count > 0`, les deux mécanismes s'activent en cascade, ce qui peut provoquer jusqu'à `(executor_retries + 1) * engine_retries` tentatives — un comportement non documenté et difficile à déboguer.

---

## 3. Dettes techniques secondaires

### 🟡 `demo_rejection_flow()` accède à des attributs privés non existants

```python
# examples/human_approval.py — ligne 282
except:  # bare except — mauvaise pratique
    suspended_runs = [
        run for run in engine._job_runs.values()  # _job_runs n'existe pas sur WorkflowEngine
        ...
    ]
    ...
    resumed_job_run = engine.resume_workflow(...)  # resume_workflow() n'existe pas
    final_result = engine.get_step_output(...)     # get_step_output() n'existe pas
```

Cet exemple en production serait immédiatement en erreur — il teste un API fantôme.

### 🟡 Aucun système de versioning des jobs lors de la persistance

`Job.version` existe en tant que champ, mais il n'est pas utilisé pour permettre de référencer la version exacte d'un job lors de la reconstruction d'un `JobRun`. Si la définition d'un job évolue entre deux exécutions, il n'y a aucun moyen de retrouver la définition originale associée à un run historique.

### 🟡 `cleanup_old_runs` a une signature incohérente entre backends

- `BaseStorage.cleanup_old_runs(older_than, dry_run=True)` → 2 paramètres
- `SQLiteStorage.cleanup_old_runs(older_than)` → 1 paramètre (override sans `dry_run`)

La LSP (Liskov Substitution Principle) est violée : le backend SQLite ne respecte pas le contrat de la classe abstraite.

### 🟡 `step.callable` est un nom réservé Python

`callable` est une builtin Python (`callable(obj)` retourne True si l'objet est appelable). Utiliser ce nom comme attribut de dataclass est légal mais confusant et peut créer des bugs subtils dans des context d'introspection ou de métaprogrammation.

### 🟢 Absence totale de tests d'intégration formels

Le répertoire `tests/integration/` est vide. Les quelques scénarios de bout-en-bout (ETL, human approval) sont dans `tests/unit/test_workflow_engine.py` — ce qui mélange la notion de tests unitaires et d'intégration. Aucun test ne couvre le cycle complet `engine.run() → persister → relancer → vérifier état`.

### 🟢 `sys.getsizeof` sous-estime massivement la mémoire réelle

`InMemoryStorage._estimate_memory_usage()` utilise `sys.getsizeof()` qui retourne la taille *superficielle* des objets, sans récursion dans leurs attributs. Pour des `JobRun` contenant des listes de `StepRun`, l'estimation peut être sous-estimée d'un facteur 10 à 100.

---

## 4. Analyse des risques

| Risque | Probabilité | Impact | Niveau |
|--------|:-----------:|:------:|:------:|
| Backend SQLite/JSON non fonctionnels découverts à la première utilisation réelle | Certaine | Critique | 🔴 Critique |
| Workflows suspendus perdus au redémarrage | Certaine en prod | Critique | 🔴 Critique |
| Double retry silencieux → comportement imprévisible | Probable | Élevé | 🟠 Élevé |
| Introspection `co_argcount` → TypeError silencieux | Probable | Élevé | 🟠 Élevé |
| Pas de persistance automatique dans `run()` → perte de données | Certaine | Élevé | 🟠 Élevé |
| LSP violée sur `cleanup_old_runs` → bug si appelé polymorphiquement | Faible | Moyen | 🟡 Moyen |
| Croissance mémoire illimitée (`_suspended_workflows`) | Probable à long terme | Moyen | 🟡 Moyen |

---

## 5. Recommandations concrètes

### R1 — Corriger immédiatement les backends SQLite et JSON *(priorité critique)*

Auditer et réécrire entièrement `_serialize_job()`, `_deserialize_job()`, `_serialize_job_run()`, `_deserialize_job_run()` dans `sqlite.py` et `json_file.py` pour aligner les noms de champs sur les modèles actuels (`dependencies` au lieu de `depends_on`, `start_time` au lieu de `started_at`, `RunStatus` au lieu de `JobRunStatus`, etc.).

Ajouter un test d'intégration minimal par backend :

```python
def test_sqlite_round_trip():
    persistence = SQLiteStorage(":memory:")
    engine = WorkflowEngine(persistence=persistence)
    job_run = engine.run(job)
    retrieved = persistence.get_job_run(job_run.job_run_id)
    assert retrieved.status == job_run.status
```

### R2 — Implémenter la sérialisation des modèles *(priorité critique)*

Ajouter `to_dict()` / `from_dict()` ou utiliser `dataclasses.asdict()` de manière explicite dans le module `serialization/`. Les callables ne peuvent pas être sérialisés — décider d'une stratégie : soit les ignorer (jobs reconstruits sans callable, pour l'affichage seulement), soit stocker le chemin de la fonction sous forme de chaîne (`module.function`).

### R3 — Persister automatiquement dans `run()` *(priorité haute)*

```python
def run(self, job, initial_context=None, run_id=None):
    ...
    job_run.complete_success()
    if self._persistence:                          # ← ajouter
        self._persistence.save_job_run(job_run)    # ← ajouter
    return job_run
```

### R4 — Durable suspension via la persistance *(priorité haute)*

Au lieu de stocker les workflows suspendus uniquement en mémoire (`self._suspended_workflows`), les persister immédiatement :

```python
except WorkflowSuspended:
    job_run.suspend("...")
    if self._persistence:
        self._persistence.save_job_run(job_run)
    self._suspended_workflows[job_run.job_run_id] = job_run
```

Et dans `resume()`, chercher d'abord en mémoire puis dans la persistance si absent.

### R5 — Remplacer `co_argcount` par `inspect.signature()` *(priorité moyenne)*

```python
import inspect

def _execute_function_step(self, step, context):
    sig = inspect.signature(step.callable)
    params = list(sig.parameters.values())
    
    # Exclure `self` pour les méthodes liées
    if params and params[0].name in ("self", "cls"):
        params = params[1:]
    
    if params:
        return step.callable(context)
    else:
        return step.callable()
```

### R6 — Unifier la stratégie de retry *(priorité moyenne)*

Choisir une seule approche :
- Soit `Step.retry_count` + `Step.retry_delay` gérés par l'engine (approche actuelle simple)
- Soit tout déléguer au `RetryableExecutor` (approche avancée)

Documenter explicitement que les deux mécanismes ne doivent pas être combinés, ou ajouter une validation qui lève une `WorkflowValidationError` si les deux sont définis simultanément.

### R7 — Corriger `cleanup_old_runs` dans `SQLiteStorage` *(priorité basse)*

```python
def cleanup_old_runs(self, older_than: datetime, dry_run: bool = True) -> int:
    # Respecter le contrat BaseStorage
    if dry_run:
        # Compter seulement
        ...
    else:
        # Supprimer
        ...
```

### R8 — Renommer `Step.callable` *(priorité basse)*

```python
# Avant
Step(name="...", callable=my_func)

# Après  
Step(name="...", fn=my_func)
# ou
Step(name="...", handler=my_func)
```

Avec un alias déprécié `callable` pour la compatibilité.

---

## 6. Points d'architecture à décider

Ces décisions ont un impact structurel et méritent une réflexion avant implémentation :

### D1 — Stratégie de sérialisation des callables

**Problème :** Les fonctions Python ne sont pas sérialisables nativement. Comment persister un `Job` contenant des callables ?

**Options :**
- A) Ne pas persister les callables — stocker uniquement les données (statut, résultats). Le job doit être rechargé depuis le code à la reprise. *(approche Airflow)*
- B) Stocker le chemin de la fonction (`"mymodule.tasks.extract"`) et la résoudre dynamiquement. *(approche simple mais fragile si renommage)*
- C) Exiger que les steps soient identifiés par un `str` et enregistrés dans un registry. *(approche Celery)*

### D2 — Exécution parallèle : à quel niveau ?

**Problème :** Le DAG sait quels steps peuvent s'exécuter en parallèle, mais l'engine les exécute séquentiellement.

**Options :**
- A) Ajouter un mode `parallel=True` sur `WorkflowEngine` qui utilise `get_parallel_groups()` + `ThreadPoolExecutor`
- B) Laisser la parallélisation à l'utilisateur via des executors nommés (approche actuelle, documentée)
- C) Implémenter un `AsyncWorkflowEngine` séparé pour les workflows 100% async

### D3 — Scope de l'engine : singleton ou instance ?

Actuellement, chaque `WorkflowEngine` est une instance indépendante avec son propre `_suspended_workflows`. Pour une application web, cela pose problème : chaque requête crée potentiellement un engine distinct. 

**Options :**
- A) Documenter explicitement que l'engine doit être un singleton applicatif
- B) Déporter tout l'état vers la persistance (suppression de `_suspended_workflows` en mémoire)
- C) Fournir une factory ou un gestionnaire de contexte applicatif (`WorkflowEngineContext`)

---

## 7. Score architectural global

| Critère                    | Score | Commentaire |
|----------------------------|:-----:|-------------|
| Design des modèles core    | 8/10  | Excellent découplage design-time/runtime |
| Algorithme DAG             | 9/10  | Solide, bien testé, API riche |
| Gestion des exceptions     | 8/10  | Hiérarchie claire et expressive |
| Cohérence de l'API publique| 5/10  | Incohérences entre Core et backends |
| Complétude fonctionnelle   | 4/10  | Backends cassés, parallélisme non activé |
| Testabilité                | 7/10  | Bonne couverture unitaire, 0 intégration |
| Sécurité des types         | 6/10  | mypy configuré mais violations LSP |
| Documentation interne      | 7/10  | Docstrings bien écrits |
| Production-readiness       | 3/10  | Suspension éphémère, persistance non fiable |
| **Moyenne**                | **6.3/10** | Bases solides, dette technique significative |

---

## Conclusion

L'architecture de `pyworkflow-engine` **repose sur des fondations conceptuelles saines** : la séparation design-time/runtime, le DAG résolveur, la hiérarchie d'exceptions, et le contrat de persistance sont des choix réfléchis et bien exécutés.

Cependant, le projet souffre d'une **dette technique critique** née d'une migration de package incomplète : les backends de persistance autre qu'`InMemoryStorage` sont non fonctionnels car jamais mis à jour pour refléter les nouveaux modèles. Le mécanisme de suspension — pourtant central pour les workflows humains — n'est pas durable.

La priorité immédiate devrait être de **corriger les backends** et d'**ajouter des tests d'intégration** qui valident le cycle complet de persistance. Les optimisations architecturales (exécution parallèle, sérialisation des callables, unification du retry) peuvent être traitées dans un second temps, une fois les bases stabilisées.
