# ADR-005 — API déclarative par décorateurs (`@step`, `@job`)

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-005                             |
| **Date**    | 11 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-002 (refactoring modulaire), ADR-004 (imports absolus + config) |
| **Version cible** | v0.5.0                         |

---

## Contexte

L'API actuelle de PyWorkflow Engine (v0.4.0) repose sur une **construction impérative** des workflows : l'utilisateur instancie manuellement `Step`, `Job`, et injecte un objet `context` dans chaque handler.

```python
# API actuelle — v0.4.0
def fetch_data(context):
    source = context.get("source")
    return {"records": [1, 2, 3]}

def transform(context):
    records = context.get_step_output("fetch", {}).get("records", [])
    return {"transformed": [r * 10 for r in records]}

job = Job(
    name="ETL Pipeline",
    steps=[
        Step(name="fetch", step_type=StepType.FUNCTION, handler=fetch_data),
        Step(name="transform", step_type=StepType.FUNCTION, handler=transform, dependencies=["fetch"]),
    ],
)
engine = WorkflowEngine()
result = engine.run(job, initial_context={"source": "api"})
```

### Problèmes identifiés

1. **Boilerplate important** : chaque step nécessite l'instanciation explicite d'un `Step(name=..., step_type=..., handler=..., dependencies=...)`.
2. **Couplage fort avec `WorkflowContext`** : chaque handler *doit* accepter `context` et utiliser l'API `context.get()` / `context.get_step_output()`. La logique métier est polluée par la plomberie d'orchestration.
3. **Typage faible** : `context.get("key")` retourne `Any` — aucune vérification statique possible par mypy, aucune autocomplétion IDE.
4. **Testabilité réduite** : tester un handler unitairement nécessite de construire ou mocker un `WorkflowContext` complet.
5. **Écart avec l'écosystème** : les outils modernes d'orchestration (Airflow 3, Prefect 2+, Dagster) ont massivement adopté l'API décorateur. L'absence de décorateurs positionne PyWorkflow Engine comme un outil daté.

### Tendance de l'écosystème

| Outil | Ancienne API | API moderne | Direction |
|-------|-------------|-------------|-----------|
| **Apache Airflow 3** | `PythonOperator(task_id=..., python_callable=...)` | `@task` | ✅ Décorateurs |
| **Prefect 2+** | `Task(fn=...)` | `@task`, `@flow` | ✅ Décorateurs |
| **Dagster** | `SolidDefinition(...)` | `@asset`, `@op`, `@job` | ✅ Décorateurs |
| **Celery** | — | `@app.task` | ✅ Décorateurs depuis v1 |
| **Luigi** | Classe héritée | Classe héritée | ❌ Pas de décorateurs (vieillissant) |

La tendance est **unanime** : les décorateurs sont devenus le standard de facto pour les APIs d'orchestration Python.

---

## Décision

**→ Introduire un module `decorators/`** fournissant les décorateurs `@step` et `@job` comme **API alternative** à la construction impérative existante.

### Principes directeurs

1. **Cohabitation** : les deux APIs (impérative et déclarative) coexistent. Aucun breaking change.
2. **Fonctions pures** : les handlers décorés par `@step` sont des fonctions Python normales, testables en isolation sans le framework.
3. **Injection de paramètres** : le framework résout automatiquement les paramètres des handlers depuis le contexte et les outputs des steps dépendants (par nom de paramètre).
4. **Rétrocompatibilité** : si un handler accepte un unique paramètre `context`, le comportement legacy est conservé.
5. **Zero dépendance** : l'implémentation utilise uniquement `functools`, `inspect`, `dataclasses` (stdlib).

---

## API cible

### Décorateur `@step`

```python
from pyworkflow_engine.decorators import step

@step(name="fetch", timeout=30)
def fetch_data(source: str = "default") -> dict:
    """Fonction pure — aucune dépendance au framework."""
    return {"records": [1, 2, 3], "source": source}

@step(name="transform", dependencies=["fetch"])
def transform_data(records: list[int] | None = None) -> dict:
    """Reçoit `records` injecté automatiquement depuis l'output de 'fetch'."""
    records = records or []
    return {"transformed": [r * 10 for r in records]}
```

La fonction décorée **reste appelable normalement** :

```python
# Test unitaire — aucun mock nécessaire
assert fetch_data(source="test") == {"records": [1, 2, 3], "source": "test"}
assert transform_data(records=[1, 2]) == {"transformed": [10, 20]}
```

Les métadonnées d'orchestration sont stockées dans `fn.__step_spec__` (un `StepSpec` frozen dataclass).

### Décorateur `@job`

```python
from pyworkflow_engine.decorators import step, job

@step(name="fetch")
def fetch_data(source: str = "default") -> dict:
    return {"records": [1, 2, 3], "source": source}

@step(name="transform", dependencies=["fetch"])
def transform_data(records: list[int] | None = None) -> dict:
    return {"transformed": [r * 10 for r in records or []]}

@job(name="ETL Pipeline", version="1.0.0")
def etl_pipeline():
    data = fetch_data()
    transform_data(records=data["records"])
```

Le décorateur `@job` retourne un `JobBuilder` qui permet :

```python
# Construire l'objet Job standard
etl_job = etl_pipeline.build()  # → Job(name="ETL Pipeline", steps=[...])

# Exécuter via le moteur
engine = WorkflowEngine()
result = engine.run(etl_pipeline.build(), initial_context={"source": "api"})
```

### Cohabitation des deux styles

```python
from pyworkflow_engine import WorkflowEngine, Job, Step, StepType
from pyworkflow_engine.decorators import step, job

# ── API impérative (inchangée) ──────────────────────────
def fetch_imperative(context):
    return {"records": [1, 2, 3]}

imperative_job = Job(
    name="ETL Imperative",
    steps=[Step(name="fetch", step_type=StepType.FUNCTION, handler=fetch_imperative)],
)

# ── API déclarative (nouvelle) ──────────────────────────
@step(name="fetch")
def fetch_declarative(source: str = "default") -> dict:
    return {"records": [1, 2, 3]}

@job(name="ETL Declarative")
def declarative_job():
    fetch_declarative()

# ── Exécution identique ────────────────────────────────
engine = WorkflowEngine()
r1 = engine.run(imperative_job)
r2 = engine.run(declarative_job.build())
```

---

## Architecture technique

### Arborescence

```
src/pyworkflow_engine/decorators/
├── __init__.py           # Re-exports : step, job, StepSpec, JobBuilder
├── step_decorator.py     # @step + StepSpec (frozen dataclass)
├── job_decorator.py      # @job + JobBuilder + résolveur context-adapter
└── resolver.py           # Introspection : fonctions @step → objets Step/Job
```

### `StepSpec` — métadonnées d'un step décoré

```python
@dataclass(frozen=True)
class StepSpec:
    """Métadonnées attachées à une fonction décorée par @step."""
    name: str
    step_type: StepType = StepType.FUNCTION
    dependencies: list[str] = field(default_factory=list)
    retry_count: int = 0
    retry_delay: float = 1.0
    timeout: float | None = None
    executor_type: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
```

Attaché à la fonction via `fn.__step_spec__`.

### Résolution des paramètres (injection)

Le mécanisme clé est `_make_context_adapter(fn, spec)` qui crée un wrapper traduisant l'interface `handler(context)` attendue par `WorkflowRunner` en appel de fonction pure avec injection de paramètres :

```
Ordre de résolution pour chaque paramètre du handler :
  1. Outputs des steps dépendants (spec.dependencies) — par clé de dict
  2. Contexte global (initial_context) — par nom de variable
  3. Valeur par défaut du paramètre (inspect.signature)
```

**Exception de rétrocompatibilité** : si la signature est `fn(context)` (un seul paramètre nommé `context`), le handler est passé tel quel à `WorkflowRunner` sans adaptation.

### `JobBuilder` — construction de `Job` depuis `@job`

Le `JobBuilder` analyse les fonctions `@step` référencées dans le corps de la fonction `@job` via :
- `fn.__code__.co_names` — noms référencés dans le bytecode
- `fn.__globals__` — résolution des objets depuis le scope global

Cette approche est **statique** (pas d'exécution du corps de la fonction `@job`) et **suffisante** pour les cas courants (fonctions `@step` définies au module-level).

---

## Analyse des alternatives

### A1 — API classe (`class ETL(Workflow)`)

```python
class ETLPipeline(Workflow):
    @step(name="fetch")
    def fetch_data(self, source: str) -> dict:
        return {"records": [1, 2, 3]}
```

**Rejeté.** Ajoute une indirection (héritage) sans bénéfice clair pour des workflows simples. L'approche fonctionnelle (`@step` + `@job`) est plus légère et plus proche du style Python idiomatique. Peut être envisagé ultérieurement comme sucre syntaxique optionnel.

### A2 — Registre explicite au lieu de l'introspection `co_names`

```python
@job(name="ETL", steps=[fetch_data, transform_data])
def etl():
    pass
```

**Considéré comme alternative complémentaire.** L'introspection via `co_names` peut être fragile si les `@step` sont importés depuis d'autres modules de manière dynamique. Proposer les deux modes :
- Mode implicite (introspection) — pour la simplicité
- Mode explicite (`steps=[...]`) — pour la robustesse dans les cas avancés

### A3 — Décorateur unique `@task` (fusion step + job)

```python
@task
def fetch(): ...

@task(dependencies=[fetch])
def transform(): ...
```

**Rejeté.** Confond deux niveaux d'abstraction. Le modèle `Step` (unité d'exécution) et `Job` (composition de steps) sont des concepts distincts dans l'architecture actuelle (ADR-002). Les fusionner dans un seul décorateur nécessiterait de revoir toute l'architecture.

### A4 — Ne rien faire — conserver uniquement l'API impérative

**Rejeté.** L'écart avec l'écosystème se creuse. L'API impérative est fonctionnelle mais verbeuse. L'absence de décorateurs est un frein à l'adoption pour les utilisateurs familiers d'Airflow 3 ou Prefect.

---

## Conséquences

### Positives

- **Réduction du boilerplate** : ~60% de code en moins pour l'utilisateur final
- **Testabilité accrue** : les handlers sont des fonctions pures, testables avec un simple `assert fn(arg) == expected`
- **Type safety** : mypy peut vérifier les signatures des handlers décorés (vs `context.get("key") → Any`)
- **Adoption facilitée** : API familière pour les utilisateurs d'Airflow 3, Prefect, Dagster
- **Zero breaking change** : l'API impérative existante n'est pas modifiée
- **Zero dépendance** : utilise uniquement `functools`, `inspect`, `dataclasses` (stdlib)
- **Séparation des préoccupations** : la logique métier est découplée de l'orchestration

### Négatives / Risques

- **Résolution implicite** : l'injection par nom de paramètre repose sur des conventions (nom du paramètre = clé dans le dict de sortie). Documenter clairement ces conventions.
- **Introspection `co_names`** : fragile pour les steps importés dynamiquement. Mitiger avec le mode explicite `steps=[...]`.
- **Surface d'API élargie** : deux façons de faire la même chose. Risque de confusion pour les nouveaux utilisateurs. Mitiger avec une documentation claire et des exemples comparatifs.
- **Maintenance** : le context-adapter ajoute une couche d'indirection. Couverture de tests exhaustive nécessaire.

### Fichiers impactés

| Action | Fichiers |
|--------|----------|
| **Créer** | `src/pyworkflow_engine/decorators/__init__.py` |
| **Créer** | `src/pyworkflow_engine/decorators/step_decorator.py` |
| **Créer** | `src/pyworkflow_engine/decorators/job_decorator.py` |
| **Créer** | `src/pyworkflow_engine/decorators/resolver.py` |
| **Modifier** | `src/pyworkflow_engine/__init__.py` — ajouter les exports `step`, `job` |
| **Créer** | `tests/unit/test_decorators.py` |
| **Créer** | `tests/integration/test_decorator_workflow.py` |
| **Créer** | `examples/decorator_api.py` — exemples comparatifs |
| **Mettre à jour** | `README.md` — section décorateurs |
| **Mettre à jour** | `docs/` — guide utilisateur décorateurs |

---

## Plan d'implémentation

### Sprint 1 — Core décorateurs (v0.5.0-alpha)

```
1. Créer src/pyworkflow_engine/decorators/step_decorator.py
   - StepSpec (frozen dataclass)
   - @step decorator avec __step_spec__ et __wrapped_fn__
   - Préservation de la signature originale (functools.wraps)

2. Créer src/pyworkflow_engine/decorators/job_decorator.py
   - @job decorator retournant un JobBuilder
   - _collect_steps_from_function() — introspection co_names + __globals__
   - _make_context_adapter() — injection des paramètres depuis context/outputs
   - Support du mode explicite : @job(steps=[...])

3. Créer src/pyworkflow_engine/decorators/__init__.py
   - Re-exports : step, job, StepSpec, JobBuilder

4. Tests unitaires (tests/unit/test_decorators.py)
   - @step : métadonnées, signature préservée, appel direct
   - @job.build() : construction Job correct depuis fonctions décorées
   - Context adapter : injection paramètres, fallback defaults, mode legacy
   - Edge cases : step sans dépendances, dépendances multiples, paramètres manquants
```

### Sprint 2 — Intégration et exemples

```
5. Modifier src/pyworkflow_engine/__init__.py
   - Ajouter step, job aux lazy imports

6. Tests d'intégration (tests/integration/test_decorator_workflow.py)
   - Workflow complet @step + @job → engine.run()
   - Cohabitation impérative + déclarative dans le même job
   - Décorateurs + ParallelRunner
   - Décorateurs + persistence (run_with_persistence)

7. Créer examples/decorator_api.py
   - Exemple minimal
   - Comparaison impérative vs déclarative
   - Test unitaire des handlers décorés
   - Intégration avec WorkflowConfig

8. Documentation
   - docs/concepts/decorators.md — guide conceptuel
   - README.md — section décorateurs avec exemple
```

### Sprint 3 — Polish et release

```
9.  Enrichir @step : support de executor_type, condition, metadata
10. Enrichir @job : support de tags, description, mode steps=[...]
11. Valider couverture ≥ 85% sur le module decorators/
12. Release v0.5.0
```

---

## Critères de validation

- [ ] `@step` préserve la signature et le docstring de la fonction décorée
- [ ] Les fonctions décorées sont appelables normalement (sans le framework)
- [ ] `@job(...).build()` produit un `Job` valide exécutable par `WorkflowEngine.run()`
- [ ] Le mode legacy `handler(context)` fonctionne sans régression
- [ ] Les deux APIs cohabitent sans conflit
- [ ] Tests unitaires ≥ 95% de couverture sur `decorators/`
- [ ] Suite de tests existante (338 tests) passe sans régression
- [ ] Zero dépendance externe ajoutée
- [ ] mypy valide les signatures des handlers décorés

---

## Références

- [PEP 318 — Decorators for Functions and Methods](https://peps.python.org/pep-0318/)
- [Apache Airflow — TaskFlow API](https://airflow.apache.org/docs/apache-airflow/stable/tutorial/taskflow.html)
- [Prefect — Tasks and Flows](https://docs.prefect.io/latest/concepts/tasks/)
- [Dagster — Software-defined Assets](https://docs.dagster.io/concepts/assets/software-defined-assets)
- ADR-002 — Refactoring architectural (`core/` → couches modulaires)
- ADR-004 — Imports absolus + module `config/`
