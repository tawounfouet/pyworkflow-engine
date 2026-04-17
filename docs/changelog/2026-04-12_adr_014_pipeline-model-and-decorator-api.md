# ADR-014 — Modèle de données `Pipeline` et API décorateur `@pipeline` / `@stage`

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-014                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | 🔄 Remplacée par ADR-016            |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-002 (architecture modulaire), ADR-005 (API décorateurs `@step`/`@job`), ADR-006 (hexagonal ports/adapters), ADR-012 (renommage storage) |
| **Version cible** | v0.8.0                         |

---

## Contexte

### Le concept manquant

Le moteur `pyworkflow_engine` dispose de trois niveaux de modélisation :

| Niveau | Design-time (frozen) | Runtime (mutable) | Decorator |
|---|---|---|---|
| **Étape** | `Step` | `StepRun` | `@step` |
| **Job** | `Job` | `JobRun` | `@job` |
| **Pipeline** | ❌ **rien** | ❌ **rien** | ❌ **rien** |

La **Pipeline** — composition séquentielle de Jobs avec propagation de contexte,
conditions d'exécution et stratégies d'erreur — est le concept central
d'orchestration d'un data workflow. C'est l'essence même du moteur :
enchaîner `ingestion → staging → mart → quality check` en une seule
unité traçable et persistable.

### Situation actuelle

Le `PipelineRunner` dans `pipelines/shared/runner.py` est un orchestrateur
**procédural** qui :

- N'a **pas de modèle de données** : pas de `Pipeline` sérialisable
- N'a **pas de traçabilité** : pas de `PipelineRun` persisté en base
- N'a **pas de visibilité** : invisible dans la GUI
- N'a **pas d'API déclarative** : `add_job()` appels impératifs au lieu de décorateurs
- Ne documente **pas sa structure** : quels jobs, dans quel ordre, avec quels mappings

```python
# Situation actuelle — procédural, non traçable
runner = PipelineRunner("weekly-countries-to-dwh")
runner.add_job(ingestion_job, initial_context={"ingest_date": today})
runner.add_job(staging_job, initial_context={"partition": today})
runner.add_job(mart_job)
runner.add_job(quality_job)
result = runner.execute()  # PipelineResult ad-hoc, non persisté
```

### Objectifs

1. **Modèle de données** `Pipeline` + `PipelineStage` (design-time, frozen, sérialisable)
2. **Modèle runtime** `PipelineRun` + `StageRun` (mutable, sérialisable, persistable)
3. **API décorateur** `@pipeline` + `@stage` symétrique à `@job` + `@step`
4. **Persistence** des `PipelineRun` en SQLite (nouvelle table `pipeline_runs`)
5. **Visibilité GUI** : page Pipelines avec DAG de stages, timeline, statut

---

## Analyse architecturale

### Symétrie Step → Job → Pipeline

Le pattern établi par ADR-005 (`@step` / `@job`) se prolonge naturellement :

```
     Design-time (frozen)          Decorator             Runtime (mutable)
     ─────────────────────         ──────────            ─────────────────
     Step                          @step → StepSpec      StepRun
       ↓ compose                     ↓ compose             ↓ produced by
     Job                           @job → JobBuilder     JobRun
       ↓ compose                     ↓ compose             ↓ produced by
     Pipeline                      @pipeline → Builder   PipelineRun
       └─ PipelineStage              └─ @stage → Spec      └─ StageRun
```

Chaque couche suit **exactement le même pattern** :

| Aspect | Step | Job | Pipeline (proposé) |
|---|---|---|---|
| Design-time | `Step` (frozen dataclass) | `Job` (frozen dataclass) | `Pipeline` (frozen dataclass) |
| Decorator | `@step` → `StepSpec` | `@job` → `JobBuilder` | `@pipeline` → `PipelineBuilder` |
| Build | `JobBuilder._spec_to_step()` | `JobBuilder.build() → Job` | `PipelineBuilder.build() → Pipeline` |
| Runtime | `StepRun` (mutable dataclass) | `JobRun` (mutable dataclass) | `PipelineRun` (mutable dataclass) |
| Sérialisation | `to_dict()` / `from_dict()` | `to_dict()` / `from_dict()` | `to_dict()` / `from_dict()` |
| Persistence | table `step_runs` | table `job_runs` | table `pipeline_runs` |
| GUI | Steps table (job detail) | Jobs table, DAG graph | Pipelines table, stages timeline |

### Graphe de composition

```
Pipeline("weekly-countries-to-dwh")
│
├─ PipelineStage(job_name="ingestion-restcountries")
│  └─ Job("ingestion-restcountries")
│     ├─ Step("fetch_raw")
│     ├─ Step("validate_raw")
│     ├─ Step("normalize_countries")
│     └─ Step("load_to_datalake")
│
├─ PipelineStage(job_name="transform-stg-restcountries")
│  └─ Job("transform-stg-restcountries")
│     ├─ Step("read_raw")
│     ├─ Step("clean_types")
│     └─ Step("write_staging")
│
├─ PipelineStage(job_name="transform-mart-catalog-countries")
│  └─ Job("transform-mart-catalog-countries")
│     ├─ Step("read_staging")
│     ├─ Step("aggregate_by_region")
│     └─ Step("write_mart")
│
└─ PipelineStage(job_name="quality-check-completeness", continue_on_failure=True)
   └─ Job("quality-check-completeness")
      └─ Step("check_row_counts")
```

---

## Décision

**→ Créer un modèle de données `Pipeline` à trois niveaux (design-time, decorator, runtime) en suivant la symétrie architecturale établie par `Step` / `Job`.**

---

## Architecture détaillée

### 1. Modèle design-time : `Pipeline` + `PipelineStage`

**Fichier** : `src/pyworkflow_engine/models/pipeline.py`

```python
@dataclass(frozen=True)
class PipelineStage:
    """Définition d'une étape dans une Pipeline = un Job à exécuter."""

    job_name: str                                     # Clé de résolution
    job: Job | None = None                            # Référence directe (non sérialisée)
    initial_context: dict[str, Any] = {}              # Contexte statique injecté au job
    context_mapping: dict[str, str] = {}              # {clé_job: clé_pipeline} propagation dynamique
    continue_on_failure: bool = False                  # Pipeline continue si ce stage échoue
    condition: Callable | None = None                  # (ctx) → bool, skip si False
    enabled: bool = True                               # Si False, toujours skippé
    metadata: dict[str, Any] = {}                     # Métadonnées libres


@dataclass(frozen=True)
class Pipeline:
    """Définition d'une pipeline complète — composition séquentielle de Jobs."""

    name: str                                         # Nom unique
    description: str = ""
    stages: list[PipelineStage] = []                  # Séquence ordonnée
    triggers: list[TriggerType] = [MANUAL]
    schedule: str | None = None                        # Expression cron
    priority: Priority = Priority.NORMAL
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    version: str = "1.0.0"
    enabled: bool = True
    owner: str = ""
    on_success: Callable | None = None                 # Callback (non sérialisé)
    on_failure: Callable | None = None                 # Callback (non sérialisé)
```

**Propriétés utilitaires** :

| Propriété | Type | Description |
|---|---|---|
| `stage_count` | `int` | Nombre de stages |
| `job_names` | `list[str]` | Noms de jobs ordonnés |
| `get_stage(job_name)` | `PipelineStage \| None` | Lookup par nom |
| `get_stage_index(job_name)` | `int \| None` | Index du stage |

**Sérialisation** : `to_dict()` / `from_dict()`. Les champs `job`, `condition`,
`on_success`, `on_failure` (callables) sont exclus de la sérialisation.

**Validation** (`__post_init__`) :
- `name` non vide
- Unicité des `job_name` dans les stages

### 2. Modèle runtime : `PipelineRun` + `StageRun`

**Fichier** : `src/pyworkflow_engine/models/pipeline_run.py`

```python
@dataclass
class StageRun:
    """Instance d'exécution d'un stage = un Job dans la pipeline."""

    stage_run_id: str                    # UUID4
    pipeline_run_id: str                 # Référence parent
    job_name: str
    stage_index: int                     # Position dans la pipeline (0-based)
    status: RunStatus = PENDING
    job_run: JobRun | None = None        # JobRun sous-jacent
    skipped: bool = False
    skip_reason: str = ""
    error: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = {}


@dataclass
class PipelineRun:
    """Instance d'exécution d'une pipeline complète."""

    pipeline_run_id: str                 # UUID4
    pipeline_name: str
    pipeline_version: str = "1.0.0"
    status: RunStatus = PENDING
    stage_runs: list[StageRun] = []
    context: dict[str, Any] = {}         # Contexte accumulé (propagé entre stages)
    error: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    triggered_by: str = "manual"
    trigger_data: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    created_at: datetime = utc_now()
    updated_at: datetime = utc_now()
```

**Transitions d'état de `StageRun`** :

```
PENDING ──start_execution()──→ RUNNING ──complete_success()──→ SUCCESS
                                       ──complete_failure()──→ FAILED
PENDING ──mark_skipped()─────→ CANCELLED (skipped=True)
```

**Transitions d'état de `PipelineRun`** :

```
PENDING ──start_execution()──→ RUNNING ──complete_success()──→ SUCCESS
                                       ──complete_failure()──→ FAILED
```

**Propriétés utilitaires de `PipelineRun`** :

| Propriété | Type | Description |
|---|---|---|
| `success` | `bool` | `status == SUCCESS` |
| `duration_s` | `float` | Durée en secondes |
| `progress_percentage` | `float` | `% stages terminaux / total` |
| `summary` | `str` | Résumé textuel multi-ligne avec icônes |

**Exemple de `summary`** :

```
Pipeline 'weekly-countries-to-dwh' — ✓ SUCCESS (24.31s)
  ✓ ingestion-restcountries: success (18.42s)
  ✓ transform-stg-restcountries: success (3.11s)
  ✓ transform-mart-catalog-countries: success (1.89s)
  ✓ quality-check-completeness: success (0.89s)
```

### 3. API décorateur : `@pipeline` + `@stage`

**Fichier** : `src/pyworkflow_engine/decorators/pipeline_decorator.py`

#### `@stage` — marque un Job comme étape de pipeline

```python
@dataclass(frozen=True)
class StageSpec:
    """Métadonnées d'orchestration stockées dans fn.__stage_spec__."""

    job_ref: Any = None            # Job | JobBuilder
    initial_context: dict = {}
    context_mapping: dict = {}
    continue_on_failure: bool = False
    condition: Callable | None = None
    enabled: bool = True
    metadata: dict = {}
```

```python
def stage(
    job: Any | None = None,
    *,
    initial_context: dict | None = None,
    context_mapping: dict | None = None,
    continue_on_failure: bool = False,
    condition: Callable | None = None,
    enabled: bool = True,
    metadata: dict | None = None,
) -> Callable:
    """Décorateur qui marque une fonction comme stage de pipeline.

    Attache un StageSpec dans fn.__stage_spec__, lu par PipelineBuilder.build().
    """
```

#### `@pipeline` — compose des `@stage` en `Pipeline`

```python
def pipeline(
    name: str | None = None,
    *,
    version: str = "1.0.0",
    description: str = "",
    schedule: str | None = None,
    owner: str = "",
    tags: list[str] | None = None,
    priority: Priority = Priority.NORMAL,
    stages: list[Callable] | None = None,
    metadata: dict | None = None,
) -> Callable:
    """Décorateur qui compose des fonctions @stage en Pipeline.

    Retourne un PipelineBuilder avec méthode build() → Pipeline.
    """
```

#### `PipelineBuilder` — retourné par `@pipeline`

```python
class PipelineBuilder:
    """Objet retourné par @pipeline. Expose build() → Pipeline."""

    def build(self) -> Pipeline:
        """Construit un Pipeline depuis les @stage associés.

        Résolution (même logique que JobBuilder) :
        1. stages=[...] explicite → utilisé directement
        2. Sinon → introspection bytecode co_names + __globals__
        """
```

#### Collecte des stages — résolution du `job_name`

```python
def _resolve_job_name(spec: StageSpec) -> str:
    """Résout le nom du job depuis le job_ref du StageSpec.

    - Si job_ref a un attribut .job_name → JobBuilder (décorateur @job)
    - Si job_ref a un attribut .name → Job model direct
    """

def _resolve_job(spec: StageSpec) -> Job | None:
    """Résout le Job — appelle build() si c'est un JobBuilder."""
```

### 4. Usage concret

#### Avant (procédural, non traçable)

```python
from pipelines.shared.runner import PipelineRunner

runner = PipelineRunner("weekly-countries-to-dwh")
runner.add_job(ingestion_job_builder.build(), initial_context={"ingest_date": today})
runner.add_job(staging_job, initial_context={"partition": today})
runner.add_job(mart_job)
runner.add_job(quality_job)
result = runner.execute()
```

#### Après (déclaratif, traçable, sérialisable)

```python
from pyworkflow_engine.decorators import pipeline, stage

@stage(
    job=ingestion_job_builder,
    context_mapping={"ingest_date": "target_date"},
)
def ingestion():
    """REST Countries API → Data Lake (raw JSON)."""

@stage(
    job=staging_job,
    context_mapping={"partition": "target_date"},
)
def staging():
    """Data Lake → DWH staging (typage, normalisation)."""

@stage(job=mart_job)
def mart():
    """Staging → Mart catalog agrégé par région."""

@stage(
    job=quality_job,
    continue_on_failure=True,
    metadata={"severity": "warning"},
)
def quality_check():
    """Vérification de complétude post-pipeline (non bloquant)."""

@pipeline(
    name="weekly-countries-to-dwh",
    description="REST Countries API → Data Lake → Staging → Mart Catalog",
    schedule="0 1 * * 0",
    owner="data-team@company.com",
    tags=["weekly", "countries", "dwh"],
)
def countries_to_dwh():
    """Pipeline complète REST Countries → Data Warehouse."""
    ingestion()
    staging()
    mart()
    quality_check()

# Utilisation
p = countries_to_dwh.build()
# p.name == "weekly-countries-to-dwh"
# p.stage_count == 4
# p.job_names == ["ingestion-restcountries", "transform-stg-restcountries", ...]
```

### 5. Exports

**`src/pyworkflow_engine/models/__init__.py`** :

```python
from pyworkflow_engine.models.pipeline import Pipeline, PipelineStage
from pyworkflow_engine.models.pipeline_run import PipelineRun, StageRun
```

**`src/pyworkflow_engine/decorators/__init__.py`** :

```python
from pyworkflow_engine.decorators.pipeline_decorator import (
    PipelineBuilder, StageSpec, pipeline, stage,
)
```

---

## Fichiers à créer

| Fichier | Contenu | Dépendances |
|---|---|---|
| `src/pyworkflow_engine/models/pipeline.py` | `Pipeline`, `PipelineStage` | `models/enums.py` |
| `src/pyworkflow_engine/models/pipeline_run.py` | `PipelineRun`, `StageRun` | `models/enums.py`, `models/run.py` |
| `src/pyworkflow_engine/decorators/pipeline_decorator.py` | `@pipeline`, `@stage`, `PipelineBuilder`, `StageSpec` | `models/pipeline.py` |
| `tests/unit/test_pipeline_model.py` | Tests `Pipeline`, `PipelineStage` | — |
| `tests/unit/test_pipeline_run.py` | Tests `PipelineRun`, `StageRun` | — |
| `tests/unit/test_pipeline_decorator.py` | Tests `@pipeline`, `@stage`, `PipelineBuilder` | — |

## Fichiers à modifier

| Fichier | Modification |
|---|---|
| `src/pyworkflow_engine/models/__init__.py` | Ajouter exports `Pipeline`, `PipelineStage`, `PipelineRun`, `StageRun` |
| `src/pyworkflow_engine/decorators/__init__.py` | Ajouter exports `pipeline`, `stage`, `PipelineBuilder`, `StageSpec` |
| `pipelines/shared/runner.py` | Refactorer pour accepter `Pipeline` et produire `PipelineRun` |
| `pipelines/weekly/countries_to_dwh.py` | Réécrire avec `@pipeline` / `@stage` |
| `pipelines/daily/books_to_dwh.py` | Réécrire avec `@pipeline` / `@stage` |

---

## Plan d'implémentation

### Phase 1 — Modèles de données (sans breaking change)

1. Créer `models/pipeline.py` (`Pipeline`, `PipelineStage`) avec `to_dict()` / `from_dict()`
2. Créer `models/pipeline_run.py` (`PipelineRun`, `StageRun`) avec transitions d'état
3. Ajouter les exports dans `models/__init__.py`
4. Écrire les tests unitaires (`test_pipeline_model.py`, `test_pipeline_run.py`)

### Phase 2 — API décorateur

5. Créer `decorators/pipeline_decorator.py` (`@pipeline`, `@stage`, `PipelineBuilder`, `StageSpec`)
6. Ajouter les exports dans `decorators/__init__.py`
7. Écrire les tests (`test_pipeline_decorator.py`)

### Phase 3 — Refactor du `PipelineRunner`

8. Refactorer `pipelines/shared/runner.py` pour :
   - Accepter un `Pipeline` en entrée (en plus de l'API `add_job()` existante)
   - Produire un `PipelineRun` au lieu de `PipelineResult`
   - Créer des `StageRun` pour chaque stage
   - Évaluer `condition`, `enabled`, `continue_on_failure`
   - Propager le `context_mapping` entre stages
9. Réécrire `pipelines/weekly/countries_to_dwh.py` avec `@pipeline` / `@stage`
10. Réécrire `pipelines/daily/books_to_dwh.py` avec `@pipeline` / `@stage`

### Phase 4 — Persistence

11. Ajouter les tables SQLite `pipelines` et `pipeline_runs` + `stage_runs`
12. Étendre `BaseStorage` avec les méthodes Pipeline (défaut `NotImplementedError`)
13. Implémenter dans `SQLiteStorage`
14. Exposer sur la facade `WorkflowEngine` (`save_pipeline`, `list_pipelines`, `run_pipeline_with_storage`, etc.)

### Phase 5 — GUI (optionnelle, post-v0.8)

15. Page `/pipelines` : liste des pipelines avec nombre de stages, schedule, owner
16. Page `/pipeline/{name}` : détail avec DAG de stages (Mermaid), metadata
17. Page `/pipeline-run/{id}` : suivi avec timeline des stages, logs agrégés
18. KPI Dashboard : ajouter "Pipelines" dans les cartes

---

## Comparaison avant / après

| Aspect | Avant (`PipelineRunner`) | Après (`Pipeline` + `@pipeline`) |
|---|---|---|
| Définition | `add_job()` procédural | `@pipeline(stages=[...])` déclaratif |
| Traçabilité | `PipelineResult` ad-hoc en mémoire | `PipelineRun` sérialisable et persistable |
| Conditions | Aucune | `condition`, `enabled`, `continue_on_failure` par stage |
| Propagation contexte | Manuelle | `context_mapping` automatique |
| Sérialisation | Non | `to_dict()` / `from_dict()` |
| Persistence | Non | SQLite (`pipeline_runs`, `stage_runs`) |
| GUI | Invisible | Page Pipelines + DAG + timeline |
| Schedule | Non documenté | `schedule: str` (cron) sur `Pipeline` |
| Owner | Non documenté | `owner: str` sur `Pipeline` |
| Metadata | Non | `tags`, `metadata`, `version` |

---

## Alternatives rejetées

### Garder `PipelineRunner` tel quel

- ✅ Aucun travail de développement
- ❌ Pas de modèle de données → impossible de persister, afficher, sérialiser
- ❌ Pas de traçabilité → les pipelines sont des boîtes noires
- ❌ Asymétrie avec `@step` / `@job` → incohérence de l'API

### Utiliser uniquement des `Job` imbriqués (SubJob)

- ✅ Pas de nouveau modèle — réutilise `Job` + `SubJob` existants
- ❌ Un `Job` imbriqué n'a pas de `schedule`, `owner`, `context_mapping`
- ❌ Le DAG de steps d'un Job n'est pas un DAG de Jobs — sémantique différente
- ❌ `SubJob` est conçu pour des sous-workflows inline, pas pour orchestrer des jobs autonomes

### Pipeline comme config YAML uniquement (pas de decorator)

- ✅ Déclaratif sans code Python
- ❌ Perd le typage statique (mypy)
- ❌ Pas de `condition` dynamique (callable)
- ❌ Incohérent avec l'API existante (`@step` / `@job` sont des décorateurs Python)
- ❌ Nécessiterait un parser YAML + résolution de références de jobs

---

## Conséquences

### Positives

- **Symétrie architecturale complète** : Step → Job → Pipeline à tous les niveaux (model, decorator, runtime, persistence, GUI)
- **Traçabilité** : chaque exécution de pipeline est un `PipelineRun` persisté avec ses `StageRun`
- **API déclarative cohérente** : `@stage` / `@pipeline` suit le même pattern que `@step` / `@job`
- **Sérialisation** : `Pipeline.to_dict()` permet l'export/import, le versioning, et l'affichage GUI
- **Extensibilité** : `condition`, `context_mapping`, `continue_on_failure` couvrent les cas d'usage avancés
- **Rétrocompatibilité** : `PipelineRunner.add_job()` reste fonctionnel pendant la transition

### Négatives / risques

- **Effort de développement** : 3 nouveaux fichiers modèles + 1 décorateur + tests + refactor runner
- **Complexité accrue** : un niveau d'abstraction supplémentaire dans le moteur
- **Migration des pipelines existantes** : `countries_to_dwh.py` et `books_to_dwh.py` à réécrire (mitigé par le fait qu'elles sont incomplètes aujourd'hui)

---

## Statut

🔵 Proposition — en attente de validation avant implémentation Phase 1.
