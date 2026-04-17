# ADR-018 — Réorganisation des modèles, namespacing SQL, et persistence unifiée du logging

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-018                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | ✅ Implémentée                      |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (hexagonal), ADR-016 (master plan), ADR-017 (unified persistence) |
| **Version cible** | v0.9.0                         |
| **Complète** | ADR-017 post-implémentation (refactoring structurel + logging) |

---

## Motivation

### Retour d'expérience post-ADR-017

L'implémentation d'ADR-017 (couche de persistence unifiée) a révélé **quatre dettes structurelles** dans l'organisation du projet qui méritent d'être traitées dans une ADR dédiée :

| # | Problème | Impact | Effort |
|---|----------|--------|--------|
| 1 | **Tables AI sans préfixe** — `agents`, `messages`, `executions` sont des noms trop génériques qui risquent de collisionner avec de futures tables core ou des tables applicatives utilisateur | Confusion dans la base SQLite, noms ambigus dans les logs et le `health_check()` | Faible |
| 2 | **`PersistableModel` limité aux modèles AI** — les modèles core (`Job`, `Step`, `JobRun`, `StepRun`, `PipelineRun`, `StageRun`) restent en `dataclass` stdlib avec sérialisation manuelle `to_dict()`/`from_dict()` et DDL écrit à la main. Le dualisme `dataclass` / Pydantic crée une charge cognitive inutile | Double système de persistence, 300+ lignes de DDL manuel dans `SQLiteStorage`, impossibilité d'utiliser `Repository[T]` sur les modèles core | Fort (sprint dédié) |
| 3 | **`models/` est un mélange plat de fichiers et de packages** — `models/ai/` est un sous-package bien organisé, mais les modèles core (`job.py`, `step.py`, `run.py`, `pipeline.py`, `pipeline_run.py`, `connector.py`) sont des fichiers plats à la racine de `models/`, sans cohérence structurelle | Navigation difficile, couplage conceptuel implicite, pas de séparation des domaines | Moyen |
| 4 | **Logging avec SQL brut hors du système unifié** — `SQLiteLogHandler` crée sa propre table avec du DDL codé en dur, sa propre connexion SQLite, et ses propres requêtes manuelles. Il ne bénéficie pas du `Repository[T]`, des indexes auto-générés, ni de la corrélation d'exécution | Table isolée, pas de corrélation logs ↔ exécutions, duplication du pattern éliminé par ADR-017, pas de filtrage dynamique | Moyen |

### L'incohérence structurelle actuelle

```
models/
├── ai/                    # ← Sous-package organisé ✅
│   ├── __init__.py
│   ├── agent.py
│   ├── conversation.py
│   ├── execution.py
│   ├── graph.py
│   ├── knowledge.py
│   ├── memory.py
│   ├── message.py
│   ├── provider.py
│   ├── skill.py
│   ├── tool.py
│   └── types.py
│
├── connector.py           # ← Fichier plat, lié à Step mais pas à Pipeline
├── enums.py               # ← Fichier plat, partagé par tous
├── job.py                 # ← Fichier plat, lié à Step
├── pipeline.py            # ← Fichier plat, lié à Job
├── pipeline_run.py        # ← Fichier plat, lié à pipeline.py + run.py
├── run.py                 # ← Fichier plat, lié à job.py + step.py
├── step.py                # ← Fichier plat, brique de base
└── __init__.py            # ← Re-exports + 20 fonctions wrapper
```

**Observation clé** : la couche AI a été correctement organisée en sous-package dès sa création (ADR-013/016), mais les modèles core n'ont jamais bénéficié du même traitement. Cette asymétrie n'est pas justifiable.

---

## Décision 1 : Préfixe `ai_` sur toutes les tables du domaine AI

### Problème

Les 14 tables actuelles du domaine AI utilisent des noms génériques :

| Table actuelle | Risque de collision |
|---------------|-------------------|
| `agents` | ✅ Terme générique — un agent peut aussi être un agent de pipeline, un agent SNMP, etc. |
| `executions` | ✅ Très générique — `JobRun` pourrait aussi s'appeler "execution" |
| `execution_steps` | ✅ Confusion avec `StepRun` (core) |
| `messages` | ✅ Un système de messaging workflow pourrait avoir sa propre table `messages` |
| `providers` | ✅ Des providers non-IA pourraient exister (cloud providers, storage providers) |
| `tools` | ✅ Des outils non-IA pourraient être enregistrés |
| `skills` | ⚠️ Moyennement générique |
| `conversations` | ⚠️ Moyennement générique |
| `graphs` | ✅ Des graphes de workflow (DAG) pourraient avoir leur propre table |
| `memories` | ⚠️ Spécifique IA, mais ambigu sans contexte |
| `knowledge_sources` | ✅ Correct — mais manque le namespace pour cohérence |
| `documents` | ✅ Très générique — un système de GED aurait aussi une table `documents` |
| `chunks` | ⚠️ Moyennement générique |
| `agent_skill_assignments` | ✅ Préfixer pour cohérence avec les autres tables |

### Convention retenue

**Toutes les tables du domaine AI sont préfixées par `ai_`.**

| Table actuelle | Nouvelle table |
|---------------|---------------|
| `providers` | `ai_providers` |
| `agents` | `ai_agents` |
| `conversations` | `ai_conversations` |
| `messages` | `ai_messages` |
| `tools` | `ai_tools` |
| `skills` | `ai_skills` |
| `agent_skill_assignments` | `ai_agent_skill_assignments` |
| `executions` | `ai_executions` |
| `execution_steps` | `ai_execution_steps` |
| `graphs` | `ai_graphs` |
| `memories` | `ai_memories` |
| `knowledge_sources` | `ai_knowledge_sources` |
| `documents` | `ai_documents` |
| `chunks` | `ai_chunks` |

### Impact sur les clés étrangères

Les FK doivent être mises à jour pour pointer vers les nouvelles tables :

| Table enfant | Colonne FK | Ancienne cible | Nouvelle cible |
|-------------|-----------|---------------|---------------|
| `ai_agents` | `provider_id` | `providers.id` | `ai_providers.id` |
| `ai_conversations` | `agent_id` | `agents.id` | `ai_agents.id` |
| `ai_messages` | `conversation_id` | `conversations.id` | `ai_conversations.id` |
| `ai_executions` | `agent_id` | `agents.id` | `ai_agents.id` |
| `ai_executions` | `conversation_id` | `conversations.id` | `ai_conversations.id` |
| `ai_execution_steps` | `execution_id` | `executions.id` | `ai_executions.id` |
| `ai_graphs` | `agent_id` | `agents.id` | `ai_agents.id` |
| `ai_memories` | `agent_id` | `agents.id` | `ai_agents.id` |
| `ai_agent_skill_assignments` | `agent_id` | `agents.id` | `ai_agents.id` |
| `ai_agent_skill_assignments` | `skill_id` | `skills.id` | `ai_skills.id` |
| `ai_documents` | `source_id` | `knowledge_sources.id` | `ai_knowledge_sources.id` |
| `ai_chunks` | `document_id` | `documents.id` | `ai_documents.id` |

### Convention de nommage future

| Domaine | Préfixe table | Exemples |
|---------|--------------|----------|
| **AI** | `ai_` | `ai_agents`, `ai_providers`, `ai_messages` |
| **Workflow** (futur) | `wf_` | `wf_jobs`, `wf_job_runs`, `wf_step_runs` |
| **Pipeline** (futur) | `pl_` | `pl_pipelines`, `pl_pipeline_runs`, `pl_stage_runs` |

> **Note** : les préfixes `wf_` et `pl_` ne sont pas appliqués dans cette ADR — ils seront implémentés lors de la migration des modèles core vers `PersistableModel` (décision 2).

### Alternatives considérées

| Alternative | Avantage | Inconvénient | Verdict |
|-------------|----------|-------------|---------|
| Pas de préfixe (statu quo) | Aucun changement | Collision inévitable quand les modèles core seront aussi dans SQLite | ❌ Rejeté |
| Préfixe long `ai_engine_` | Plus explicite | Trop verbeux, pénalise les requêtes SQL manuelles | ❌ Rejeté |
| Préfixe `ai_` (retenu) | Court, clair, cohérent avec le nom du sous-package `models/ai/` | — | ✅ Retenu |
| Schéma SQLite séparé | Isolation totale | SQLite ne supporte pas les schémas nativement (pas de `CREATE SCHEMA`) | ❌ Impossible |

---

## Décision 2 : Migration progressive des modèles core vers `PersistableModel`

### Problème

Le projet maintient **deux systèmes de persistence parallèles** pour des raisons historiques :

| Aspect | Modèles core (`dataclass`) | Modèles AI (`PersistableModel`) |
|--------|---------------------------|-------------------------------|
| **Déclaration** | `@dataclass`, champs Python | `PersistableModel(BaseModel)` + `__table_meta__` |
| **DDL** | Manuel — 300+ lignes dans `SQLiteStorage.SCHEMA_SQL` | Auto — `SchemaGenerator.generate_create_table()` |
| **Sérialisation** | Manuelle — `to_dict()` / `from_dict()` par modèle | Auto — `ModelSerializer.to_row()` / `from_row()` |
| **CRUD** | Manuel — méthodes dédiées dans chaque backend | Générique — `Repository[T].create()`, `.filter()`, etc. |
| **Registre** | Aucun — tables codées en dur | `ModelRegistry` avec auto-discovery |
| **Requêtage** | Méthodes `list_*` écrites à la main | `Repository.filter()` style Django |

Ce dualisme signifie que chaque ajout de champ ou nouveau modèle core nécessite :
1. Modifier le modèle `dataclass`
2. Modifier le DDL SQL dans `SQLiteStorage.SCHEMA_SQL`
3. Modifier `_serialize_*` / `_deserialize_*` dans chaque backend
4. Modifier les méthodes CRUD dans chaque backend
5. Modifier `to_dict()` / `from_dict()` sur le modèle

Avec `PersistableModel`, les étapes 2–5 **disparaissent**.

### Décision

Migrer **progressivement** les modèles core de `dataclass` stdlib vers `PersistableModel` (Pydantic `BaseModel`).

### Stratégie de migration

La migration se fait en **3 vagues**, du plus isolé au plus connecté :

#### Vague 1 — Modèles sans dépendances entrantes (faible risque)

| Modèle | Fichier actuel | Raison de priorité |
|--------|---------------|-------------------|
| `ConnectorRef` | `models/connector.py` | Embedded dans `Step`, jamais persisté seul |
| `ConnectorOutcome` | `models/connector.py` | Embedded dans `StepRun`, jamais persisté seul |
| `StepLog` | `models/run.py` | Embedded dans `StepRun`, jamais persisté seul |

> Ces modèles sont embedded — la migration vers Pydantic améliore la validation sans impact sur la persistence.

#### Vague 2 — Modèles runtime (impact modéré)

| Modèle | Fichier actuel | Table | Clé primaire |
|--------|---------------|-------|-------------|
| `StepRun` | `models/run.py` | `wf_step_runs` | `step_run_id` |
| `JobRun` | `models/run.py` | `wf_job_runs` | `job_run_id` |
| `StageRun` | `models/pipeline_run.py` | `pl_stage_runs` | `stage_run_id` |
| `PipelineRun` | `models/pipeline_run.py` | `pl_pipeline_runs` | `pipeline_run_id` |

> Ces modèles sont mutables (mise à jour des statuts). La migration permet de les gérer via `Repository[T]` au lieu de méthodes dédiées dans chaque backend.

#### Vague 3 — Modèles design-time (impact élevé)

| Modèle | Fichier actuel | Table | Clé primaire |
|--------|---------------|-------|-------------|
| `Step` | `models/step.py` | — (embedded dans Job) | `name` |
| `SubJob` | `models/step.py` | — (embedded dans Job) | `name` |
| `Job` | `models/job.py` | `wf_jobs` | `name` |
| `PipelineStage` | `models/pipeline.py` | — (embedded dans Pipeline) | `job_name` |
| `Pipeline` | `models/pipeline.py` | `pl_pipelines` | `name` |

> Ces modèles sont `frozen=True` et ont des champs non-sérialisables (`handler: Callable`, `condition: Callable`). La migration nécessite une attention particulière pour gérer les callables (exclus de la persistence, reconstitués via `_restore_handler()`).

### Contraintes

1. **Compatibilité ascendante** : tous les `to_dict()` / `from_dict()` doivent continuer à fonctionner pendant la migration (Pydantic offre `model_dump()` / `model_validate()` qui les remplacent)
2. **Pas de big-bang** : les vagues sont indépendantes et livrables séparément
3. **Tests existants** : les 1120+ tests doivent rester verts entre chaque vague
4. **Callables** : les champs `handler`, `condition` sont marqués `exclude=True` dans Pydantic et reconstitués séparément

### Alternatives considérées

| Alternative | Avantage | Inconvénient | Verdict |
|-------------|----------|-------------|---------|
| Garder le dualisme (statu quo) | Aucun changement | Double maintenance permanente, 300+ lignes de DDL manuel | ❌ Rejeté |
| Adapter `PersistableModel` pour `dataclass` | Compatible avec l'existant | Complexité d'implémentation élevée (inspection de champs `dataclass` ≠ Pydantic) | ❌ Rejeté |
| Migrer tout vers Pydantic (retenu) | Système unique, `Repository[T]` pour tout | Migration progressive nécessaire | ✅ Retenu |
| SQLAlchemy ORM complet | Très puissant | Dépendance lourde, incohérent avec l'architecture stdlib-first | ❌ Rejeté |

---

## Décision 3 : Réorganisation `models/` en trois sous-packages par domaine

### Problème

L'analyse des dépendances entre modèles révèle **trois domaines distincts** :

```
┌─────────────────────────────────────────────────────────────────┐
│  models/                                                        │
│                                                                 │
│  ┌──────────────────────────┐                                   │
│  │ enums.py (partagé)       │◄──────────────────────────────┐   │
│  │ TriggerType, StepType,   │                               │   │
│  │ ExecutorType, RunStatus,  │                               │   │
│  │ Priority                  │                               │   │
│  └──────┬───────┬───────┬───┘                               │   │
│         │       │       │                                    │   │
│         ▼       │       ▼                                    │   │
│  ┌──────────┐   │  ┌──────────────┐   ┌──────────────────┐  │   │
│  │ step.py  │   │  │ pipeline.py  │   │ ai/agent.py      │  │   │
│  │ job.py   │   │  │ pipeline_    │   │ ai/provider.py   │  │   │
│  │ run.py   │◄──┘  │ run.py       │   │ ai/...           │  │   │
│  │connector.│      │              │   │                   │──┘   │
│  │  py      │◄─────│ (dépend de   │   │ (indépendant     │      │
│  │          │      │  Job, JobRun) │   │  du workflow)    │      │
│  └──────────┘      └──────────────┘   └──────────────────┘      │
│   WORKFLOW           PIPELINE               AI                   │
│   (briques           (orchestration         (agents,             │
│    de base)           de Jobs)               LLM, etc.)          │
└─────────────────────────────────────────────────────────────────┘
```

**Un `Job` peut exister sans `Pipeline`** (exécution standalone). Un `Step` est une unité atomique. Un `ConnectorRef` est un pont vers `pyconnectors` qui n'a rien à voir avec le concept de pipeline. Les regrouper tous dans `pipeline/` serait une erreur conceptuelle.

### Analyse des domaines

| Concept | Dépend de Pipeline ? | Dépend de Workflow ? | Domaine réel |
|---------|---------------------|---------------------|-------------|
| `Step`, `SubJob` | ❌ Non — unité atomique | ❌ Non — brique de base | **workflow** |
| `Job` | ❌ Non — composition de Steps, exécutable seul | ✅ Oui (contient des Steps) | **workflow** |
| `StepRun`, `StepLog` | ❌ Non | ✅ Oui (instance d'un Step) | **workflow** |
| `JobRun` | ❌ Non | ✅ Oui (instance d'un Job) | **workflow** |
| `ConnectorRef` | ❌ Non — pont vers pyconnectors | ⚠️ Optionnel (champ de Step) | **workflow** |
| `ConnectorOutcome` | ❌ Non | ⚠️ Optionnel (champ de StepRun) | **workflow** |
| `Pipeline`, `PipelineStage` | ✅ Oui — est la Pipeline | ✅ Oui (compose des Jobs) | **pipeline** |
| `PipelineRun`, `StageRun` | ✅ Oui — instance de Pipeline | ✅ Oui (contient des JobRuns) | **pipeline** |
| `Agent`, `Provider`, `Tool`, … | ❌ Non | ❌ Non | **ai** |
| Enums (`RunStatus`, `StepType`…) | ❌ Non — partagés par tous | ❌ Non | **shared** |

### Graphe de dépendances entre domaines

```
    enums.py (shared)
        │
        ├──────────────────┐
        │                  │
        ▼                  ▼
    workflow/           ai/
    (Step, Job,         (Agent, Provider,
     JobRun, ...)        Conversation, ...)
        │
        │ Pipeline dépend de Job, JobRun
        ▼
    pipeline/
    (Pipeline, PipelineRun, ...)
```

**Règle : les dépendances vont dans un seul sens.**
- `pipeline/` → `workflow/` → `enums.py` ✅
- `ai/` → `enums.py` ✅
- `ai/` ↛ `workflow/` ✅ (aucune dépendance)
- `workflow/` ↛ `pipeline/` ✅ (aucune dépendance)
- `workflow/` ↛ `ai/` ✅ (aucune dépendance)

Aucune circularité possible.

### Structure cible

```
models/
├── enums.py                    # Enums partagés (inchangé, PAS deprecated)
│
├── workflow/                   # Domaine Workflow — briques de base
│   ├── __init__.py             # Re-exports: Step, SubJob, Job, JobRun, StepRun, ...
│   ├── step.py                 # Step, SubJob (design-time)
│   ├── job.py                  # Job (design-time)
│   ├── run.py                  # JobRun, StepRun, StepLog (runtime)
│   └── connector.py            # ConnectorRef, ConnectorOutcome (bridge pyconnectors)
│
├── pipeline/                   # Domaine Pipeline — orchestration séquentielle de Jobs
│   ├── __init__.py             # Re-exports: Pipeline, PipelineStage, PipelineRun, StageRun
│   ├── pipeline.py             # Pipeline, PipelineStage (design-time)
│   └── pipeline_run.py         # PipelineRun, StageRun (runtime)
│
├── ai/                         # Domaine AI — agents, LLM, knowledge (inchangé)
│   ├── __init__.py
│   ├── agent.py
│   ├── provider.py
│   ├── conversation.py
│   ├── message.py
│   ├── tool.py
│   ├── skill.py
│   ├── execution.py
│   ├── graph.py
│   ├── memory.py
│   ├── knowledge.py
│   └── types.py
│
├── logging/                    # Domaine Logging — transversal (NEW)
│   ├── __init__.py             # Re-exports: WorkflowLog, WorkflowLogQuery
│   └── log_entry.py            # WorkflowLog (PersistableModel), WorkflowLogQuery (DTO)
│
├── __init__.py                 # Re-exports everything (compatibilité ascendante)
│
│   # Shims de compatibilité (DEPRECATED — supprimés en v1.0.0)
├── step.py                     # → re-export from workflow.step
├── job.py                      # → re-export from workflow.job
├── run.py                      # → re-export from workflow.run
├── connector.py                # → re-export from workflow.connector
├── pipeline.py                 # → re-export from pipeline.pipeline
└── pipeline_run.py             # → re-export from pipeline.pipeline_run
```

### Pourquoi NE PAS tout mettre dans `pipeline/`

Une proposition initiale était de regrouper `Job`, `Step`, `ConnectorRef`, `Pipeline`, `PipelineRun`, etc. dans un seul sous-package `pipeline/`. Cette approche est **incorrecte** pour 4 raisons :

| # | Raison | Détail |
|---|--------|--------|
| 1 | **Un `Job` ≠ une Pipeline** | Un `Job` est exécutable seul via `WorkflowRunner.run()`. Il n'a pas besoin de `Pipeline`. |
| 2 | **Un `Step` est atomique** | Un `Step` est la brique de base du workflow. Il peut exister sans `Job` ni `Pipeline` (exécution directe via un executor). |
| 3 | **`ConnectorRef` est un bridge** | `ConnectorRef` est un pont vers `pyconnectors`. Il est lié au concept de `Step` (un step peut utiliser un connecteur), pas au concept de `Pipeline`. |
| 4 | **Couplage artificiel** | Mettre `Step` dans `pipeline/` forcerait `pipeline/` à être importé même pour exécuter un simple Job sans pipeline. |

### Shims de compatibilité

Chaque fichier racine (`models/step.py`, `models/job.py`, etc.) devient un **shim de redirection** :

```python
# models/step.py — DEPRECATED
"""
DEPRECATED — Importez depuis ``models.workflow.step``.

    from pyworkflow_engine.models.workflow.step import Step, SubJob
    # ou
    from pyworkflow_engine.models import Step, SubJob
"""

from pyworkflow_engine.models.workflow.step import Step, SubJob  # noqa: F401

__all__ = ["Step", "SubJob"]
```

**Tous les imports existants continuent de fonctionner** :

```python
# ✅ Ancien import — fonctionne via le shim
from pyworkflow_engine.models.step import Step

# ✅ Import via __init__ — fonctionne via re-export
from pyworkflow_engine.models import Step

# ✅ Nouvel import recommandé
from pyworkflow_engine.models.workflow.step import Step
```

Les shims seront supprimés en **v1.0.0** (breaking change majeur).

### Impact sur `models/__init__.py`

Le module `__init__.py` est mis à jour pour importer depuis les nouveaux sous-packages :

```python
# models/__init__.py

# ── Re-exports depuis models.workflow ───────────────────────────────────
from pyworkflow_engine.models.workflow import (
    ConnectorOutcome, ConnectorRef,
    Job, JobRun, Step, StepLog, StepRun, SubJob,
    generate_id, utc_now,
)

# ── Re-exports depuis models.pipeline ───────────────────────────────────
from pyworkflow_engine.models.pipeline import (
    Pipeline, PipelineRun, PipelineStage, StageRun,
)

# ── Enums (restent dans models/enums.py — partagés par tous) ────────────
from pyworkflow_engine.models.enums import (
    ACTIVE_STATUSES, SUSPENDED_STATUSES, TERMINAL_STATUSES,
    ExecutorType, Priority, RunStatus, StepType, TriggerType,
    can_cancel, can_resume, is_active, is_suspended, is_terminal,
)
```

---

## Décision 4 : Intégration du logging dans le système de persistence unifié (ADR-017)

### Problème

Le module `logging/handlers.py` contient un `SQLiteLogHandler` qui **réinvente tout ce qu'ADR-017 élimine** :

| Aspect | `SQLiteLogHandler` (actuel) | Pattern ADR-017 (cible) |
|--------|---------------------------|------------------------|
| **DDL** | `CREATE TABLE workflow_logs (...)` codé en dur | Auto via `SchemaGenerator.generate_create_table()` |
| **Connexion** | Crée sa propre `sqlite3.connect()` | Partage la connexion de `UnifiedStorage` |
| **Indexes** | 2 index codés en dur | Auto via `SchemaGenerator.generate_indexes()` |
| **CRUD** | `executemany()` + SQL brut | `Repository[WorkflowLog].create()` |
| **Requêtage** | `query_logs()` avec SQL brut, 4 filtres max | `Repository.filter()` avec 8 opérateurs Django-style |
| **Corrélation** | Aucune — le log ne sait pas à quelle exécution il appartient | FK optionnelles vers `job_run_id`, `step_run_id`, `execution_id`, `pipeline_run_id`, `agent_id` |
| **Sérialisation** | Manuelle (`json.dumps(extras)`) | Auto via `ModelSerializer` |

### Analyse de l'existant

Le `SQLiteLogHandler` actuel :

```python
class SQLiteLogHandler(logging.Handler):
    def __init__(self, db_path="workflow_logs.db"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                logger TEXT NOT NULL,
                message TEXT NOT NULL,
                extra TEXT,              -- JSON blob, pas de colonnes indexables
                exception TEXT,
                module TEXT,
                func_name TEXT,
                line_no INTEGER
            )
        """)
```

**Problèmes concrets** :

1. **Pas de corrélation** : un log `"Step failed"` ne sait pas quel `job_run_id` ou `step_run_id` l'a émis. Pour investiguer un incident, il faut croiser manuellement les timestamps avec les tables de `StepRun`.

2. **Connexion isolée** : le handler crée sa propre connexion SQLite vers un fichier séparé (`workflow_logs.db`), alors que les données d'exécution sont dans `workflow.db`. Impossible de faire un `JOIN` logs ↔ exécutions.

3. **Filtrage limité** : `query_logs()` offre 4 filtres (`level`, `logger_name`, `since`, `limit`). Pas de filtre par `job_run_id`, `agent_id`, `correlation_id`, pas de `LIKE` sur message, pas de plage temporelle `until`.

4. **Extra opaque** : les données extra sont un blob JSON non indexé. Chercher tous les logs d'un agent spécifique nécessite un `json_extract()` SQLite, plus lent et non-portable.

### Décision

Créer un modèle `WorkflowLog` dans `models/logging/` qui hérite de `PersistableModel` et s'intègre dans le `ModelRegistry`. Le `SQLiteLogHandler` est remplacé par un `RepositoryLogHandler` qui délègue au `Repository[WorkflowLog]`.

### Architecture cible

```
  logging.getLogger("pyworkflow_engine.engine.runner")
      │
      │ logger.info("Step started", extra={"job_run_id": "run-123"})
      │
      ▼
  ┌────────────────────────┐
  │  RepositoryLogHandler  │  ← Nouveau handler ADR-017
  │                        │
  │  • Convertit LogRecord │
  │    → WorkflowLog       │
  │  • Extrait les clés de │
  │    corrélation auto    │
  │  • Buffer + batch      │
  └──────────┬─────────────┘
             │ repo.create(WorkflowLog(...))
             ▼
  ┌────────────────────────┐
  │  Repository[WorkflowLog]│  ← CRUD unifié ADR-017
  │                        │
  │  .create()             │
  │  .filter(level="ERROR")│
  │  .filter(job_run_id=   │
  │    "run-123")          │
  │  .count(agent_id=      │
  │    "agent-research")   │
  └──────────┬─────────────┘
             │
             ▼
  ┌────────────────────────┐
  │  Table: log_entries    │  ← Auto-generated DDL
  │                        │
  │  • 10 indexes auto     │
  │  • Corrélation FK      │
  │  • Même base que les   │
  │    modèles AI/workflow  │
  └────────────────────────┘
```

### Modèle `WorkflowLog`

```python
# models/logging/log_entry.py

@ModelRegistry.register
class WorkflowLog(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="log_entries",
        columns=[
            # Identité
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("timestamp", ColumnType.TIMESTAMP, nullable=False),
            ColumnDef("level", ColumnType.TEXT, nullable=False),
            ColumnDef("logger_name", ColumnType.TEXT, nullable=False),
            ColumnDef("message", ColumnType.TEXT, nullable=False),
            # Corrélation (toutes optionnelles)
            ColumnDef("correlation_id", ColumnType.TEXT),
            ColumnDef("job_run_id", ColumnType.TEXT),
            ColumnDef("step_run_id", ColumnType.TEXT),
            ColumnDef("execution_id", ColumnType.TEXT),
            ColumnDef("pipeline_run_id", ColumnType.TEXT),
            ColumnDef("agent_id", ColumnType.TEXT),
            # Technique
            ColumnDef("module", ColumnType.TEXT),
            ColumnDef("func_name", ColumnType.TEXT),
            ColumnDef("line_no", ColumnType.INTEGER),
            ColumnDef("exception", ColumnType.TEXT),
            ColumnDef("extra", ColumnType.JSON),
            # Metadata
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[
            ("timestamp",),
            ("level",),
            ("logger_name",),
            ("correlation_id",),
            ("job_run_id",),
            ("step_run_id",),
            ("execution_id",),
            ("pipeline_run_id",),
            ("agent_id",),
            ("level", "timestamp"),  # Composite pour les requêtes fréquentes
        ],
    )

    id: str                           # UUID
    timestamp: datetime               # UTC
    level: str = "INFO"               # DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger_name: str = ""             # ex: "pyworkflow_engine.engine.runner"
    message: str = ""

    # Corrélation — chaque log peut être relié à une exécution
    correlation_id: str | None = None     # ID libre pour regrouper des logs transversaux
    job_run_id: str | None = None         # → JobRun (futur FK vers wf_job_runs)
    step_run_id: str | None = None        # → StepRun (futur FK vers wf_step_runs)
    execution_id: str | None = None       # → Execution AI (FK vers ai_executions)
    pipeline_run_id: str | None = None    # → PipelineRun (futur FK vers pl_pipeline_runs)
    agent_id: str | None = None           # → Agent AI (FK vers ai_agents)

    # Technique
    module: str | None = None
    func_name: str | None = None
    line_no: int | None = None
    exception: str | None = None      # Traceback complet si applicable
    extra: dict[str, Any] = {}        # Champs extra du LogRecord

    created_at: datetime              # Auto
```

> **Note** : les FK vers `job_run_id`, `step_run_id`, `pipeline_run_id` ne sont pas des FK SQL strictes (les tables core n'existent pas encore dans le `ModelRegistry`). Elles deviennent des FK réelles après la migration des modèles core (décision 2, vague 2).

### Champs de corrélation

La corrélation est le **principal gain** de cette migration. Chaque log est automatiquement enrichi avec le contexte d'exécution :

| Champ | Source | Usage |
|-------|--------|-------|
| `correlation_id` | Défini au niveau handler ou passé dans `extra` | Regrouper des logs transversaux (trace distribuée) |
| `job_run_id` | `extra={"job_run_id": "..."}` ou `handler.set_context()` | Tous les logs d'un JobRun |
| `step_run_id` | `extra={"step_run_id": "..."}` ou `handler.set_context()` | Tous les logs d'un StepRun |
| `execution_id` | `extra={"execution_id": "..."}` ou `handler.set_context()` | Tous les logs d'une Execution AI |
| `pipeline_run_id` | `extra={"pipeline_run_id": "..."}` ou `handler.set_context()` | Tous les logs d'un PipelineRun |
| `agent_id` | `extra={"agent_id": "..."}` ou `handler.set_context()` | Tous les logs d'un Agent AI |

**Priorité d'extraction** : `LogRecord.extra` > `handler.default_context` > `handler.correlation_id`.

### `RepositoryLogHandler` — nouveau handler

```python
# logging/handlers.py

class RepositoryLogHandler(logging.Handler):
    """Persiste les logs via Repository[WorkflowLog] (ADR-017).

    S'intègre dans le système de persistence unifié.
    Thread-safe grâce à un buffer interne et un lock.
    """

    _CORRELATION_KEYS = frozenset({
        "correlation_id", "job_run_id", "step_run_id",
        "execution_id", "pipeline_run_id", "agent_id",
    })

    def __init__(
        self,
        repository: Repository[WorkflowLog],
        batch_size: int = 1,
        correlation_id: str | None = None,
        default_context: dict[str, str] | None = None,
    ): ...

    def emit(self, record: LogRecord) -> None:
        """Convertit LogRecord → WorkflowLog, buffer, flush."""
        # 1. Extraire les extras non-standard
        # 2. Extraire les clés de corrélation (auto)
        # 3. Construire WorkflowLog avec corrélation
        # 4. Buffer + flush si batch atteint

    def set_context(self, **kwargs) -> None:
        """Met à jour le contexte de corrélation par défaut.

        Utile quand on entre dans un nouveau step/job :
            handler.set_context(job_run_id="run-123", step_run_id="step-456")
        """
```

### `WorkflowLogQuery` — read-model de requêtage

```python
# models/logging/log_entry.py

class WorkflowLogQuery:
    """DTO pour construire des requêtes Repository.filter() type-safe.

    Usage:
        query = WorkflowLogQuery(level="ERROR", job_run_id="run-123", limit=50)
        logs = storage.logs.filter(**query.to_filter_kwargs())
    """

    def __init__(
        self,
        *,
        level: str | None = None,
        logger_name: str | None = None,
        correlation_id: str | None = None,
        job_run_id: str | None = None,
        step_run_id: str | None = None,
        execution_id: str | None = None,
        pipeline_run_id: str | None = None,
        agent_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        message_like: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "timestamp DESC",
    ): ...

    def to_filter_kwargs(self) -> dict[str, Any]:
        """Convertit en kwargs pour Repository.filter()."""
```

### `UnifiedStorage.logs` — raccourci nommé

```python
class UnifiedStorage(BaseAIStorage):
    # ...existing named repos...

    @property
    def logs(self) -> Repository[WorkflowLog]:
        """Repository des WorkflowLog."""
        from pyworkflow_engine.models.logging.log_entry import WorkflowLog
        return self.repository(WorkflowLog)
```

### `SQLiteLogHandler` — deprecated

Le `SQLiteLogHandler` existant est marqué `DEPRECATED` avec un `warnings.warn()` orientant vers `RepositoryLogHandler`. Il reste fonctionnel pour la compatibilité ascendante mais sera supprimé en v1.0.0.

### Structure fichiers

```
models/
├── logging/                    # Domaine Logging (NEW)
│   ├── __init__.py             # Re-exports: WorkflowLog, WorkflowLogQuery
│   └── log_entry.py            # WorkflowLog (PersistableModel), WorkflowLogQuery

logging/
├── handlers.py                 # RepositoryLogHandler (NEW) + SQLiteLogHandler (DEPRECATED)
├── ...                         # Inchangé
```

### Comparaison avant/après

| Aspect | Avant (`SQLiteLogHandler`) | Après (`RepositoryLogHandler`) |
|--------|---------------------------|-------------------------------|
| **DDL** | SQL codé en dur (15 lignes) | Auto via `SchemaGenerator` |
| **Connexion** | Séparée (`workflow_logs.db`) | Partagée (`workflow.db`) |
| **Indexes** | 2 (timestamp, level) | 10 (tous les champs de corrélation + composites) |
| **Filtrage** | 4 filtres codés en dur | 8 opérateurs Django-style + tous les champs |
| **Corrélation** | Aucune | 6 champs de corrélation automatiques |
| **Requêtage** | `query_logs()` SQL brut | `storage.logs.filter(job_run_id="run-123", level="ERROR")` |
| **Join possible** | ❌ (base séparée) | ✅ (même base que les exécutions) |
| **Batch** | ✅ (`executemany`) | ✅ (buffer interne + `repo.create()`) |
| **Thread-safe** | ✅ (lock) | ✅ (lock) |

### Scénarios d'usage

#### Investigation d'un incident

```python
# Tous les logs ERROR d'un job_run spécifique
errors = storage.logs.filter(
    job_run_id="run-123",
    level="ERROR",
    order_by="timestamp ASC",
)

# Logs d'un agent AI avec trace d'exception
agent_errors = storage.logs.filter(
    agent_id="agent-research",
    exception__isnull=False,
)

# Timeline complète d'un pipeline_run
timeline = storage.logs.filter(
    pipeline_run_id="pipe-001",
    order_by="timestamp ASC",
)
```

#### Monitoring avec `WorkflowLogQuery`

```python
from pyworkflow_engine.models.logging import WorkflowLogQuery

query = WorkflowLogQuery(
    level="ERROR",
    since=datetime(2026, 4, 12, tzinfo=UTC),
    message_like="%timeout%",
    limit=50,
)
recent_errors = storage.logs.filter(**query.to_filter_kwargs())
```

#### Corrélation contextuelle automatique

```python
# Le handler propage automatiquement le contexte
handler = RepositoryLogHandler(storage.logs, batch_size=10)
handler.set_context(pipeline_run_id="pipe-001")

# Pendant l'exécution d'un job
handler.set_context(job_run_id="run-123", step_run_id="step-456")
logger.info("Processing data")  # → log corrélé à pipe-001 + run-123 + step-456

# Step suivant
handler.set_context(step_run_id="step-789")
logger.info("Transform complete")  # → log corrélé à pipe-001 + run-123 + step-789
```

### Convention de nommage de la table

La table s'appelle `log_entries` (sans préfixe de domaine) car :
- Les logs sont **transversaux** — ils couvrent les domaines AI, workflow, et pipeline
- Un préfixe `ai_` ou `wf_` serait incorrect
- Le nom `log_entries` est suffisamment explicite et non-ambigu

### Alternatives considérées

| Alternative | Avantage | Inconvénient | Verdict |
|-------------|----------|-------------|---------|
| Garder `SQLiteLogHandler` (statu quo) | Aucun changement | SQL brut, pas de corrélation, base séparée | ❌ Rejeté |
| Logger structlog avec sink SQLite | Puissant, intégré | Dépendance externe, pas de corrélation native | ❌ Rejeté |
| `WorkflowLog` dans `models/ai/` | Cohérent avec ADR-017 | Les logs ne sont pas spécifiques à l'AI | ❌ Rejeté |
| `WorkflowLog` dans `models/logging/` (retenu) | Transversal, propre, intégré au `ModelRegistry` | Nouveau sous-package | ✅ Retenu |
| Table avec préfixe `log_` | Cohérent avec les autres préfixes | Les logs n'ont pas de domaine unique | ❌ Rejeté |

---

## Diagramme d'architecture cible

```
┌───────────────────────────────────────────────────────────────────────────┐
│  models/                                                                  │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  enums.py                                                           │  │
│  │  TriggerType · StepType · ExecutorType · RunStatus · Priority       │  │
│  └───────────┬──────────────────────┬──────────────────┬────────────── ┘  │
│              │                      │                  │                  │
│  ┌───────────▼──────────┐  ┌───────▼───────────┐  ┌───▼────────────┐    │
│  │  workflow/            │  │  ai/               │  │ pipeline/      │    │
│  │                       │  │                    │  │                │    │
│  │  Step, SubJob         │  │  Agent             │  │ Pipeline       │    │
│  │  Job                  │  │  LLMProviderConfig │  │ PipelineStage  │    │
│  │  StepLog, StepRun     │  │  Conversation      │  │ PipelineRun    │    │
│  │  JobRun               │  │  Message            │  │ StageRun       │    │
│  │  ConnectorRef         │  │  ToolDefinition    │  │                │    │
│  │  ConnectorOutcome     │  │  Skill             │  │ Tables: pl_*   │    │
│  │                       │  │  Execution         │  │ (futur)        │    │
│  │  Tables: wf_*         │  │  Graph             │  │                │    │
│  │  (futur — décision 2) │  │  AgentMemory       │  └──────┬─────── ┘    │
│  │                       │  │  KnowledgeSource   │         │             │
│  │                       │  │  Document, Chunk   │  dépend de            │
│  │                       │  │                    │  workflow/             │
│  │                       │  │  Tables: ai_*      │                       │
│  └───────────────────────┘  └────────────────────┘                       │
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────── ┐  │
│  │  logging/                                                           │  │
│  │                                                                     │  │
│  │  WorkflowLog                                                        │  │
│  │  WorkflowLogQuery                                                   │  │
│  │                                                                     │  │
│  │  Table: log_entries (transversal — corrèle AI + workflow + pipeline) │  │
│  │  Corrélation: job_run_id · step_run_id · execution_id ·             │  │
│  │               pipeline_run_id · agent_id · correlation_id           │  │
│  └─────────────────────────────────────────────────────────────────── ┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Impact sur `UnifiedStorage`, le logging, et les tests

### `UnifiedStorage`

Aucun changement structurel — le `UnifiedStorage` continue d'importer les modèles AI depuis `models.ai.*` et utilise les `Repository[T]` nommés. Le seul changement est que les noms de tables changent dans les `__table_meta__` (préfixe `ai_`), ce qui impacte :

- Les instructions DDL générées par `SchemaGenerator`
- Les requêtes SQL dans `Repository`
- Les index dans `health_check()`

Tout cela est **transparent** car le code ne contient jamais de noms de tables en dur — il les lit depuis `__table_meta__.table_name`.

Un nouveau raccourci nommé `storage.logs` est ajouté pour accéder au `Repository[WorkflowLog]`. L'import chain dans `UnifiedStorage.__init__` est étendu pour enregistrer `models.logging` en plus de `models.ai`.

### Module logging

| Composant | Changement |
|-----------|-----------|
| `logging/__init__.py` | Exporte `RepositoryLogHandler` |
| `logging/handlers.py` | Ajoute `RepositoryLogHandler`, marque `SQLiteLogHandler` comme `DEPRECATED` |
| `models/logging/__init__.py` | Nouveau sous-package |
| `models/logging/log_entry.py` | `WorkflowLog` + `WorkflowLogQuery` |

### Tests storage

Les 82 tests storage existants doivent être vérifiés après le renommage des tables. Les tests qui vérifient des noms de tables en dur (ex: `test_unified_storage.py` qui pourrait vérifier `health_check()`) devront être mis à jour.

### Migration de base existante

Pour les bases SQLite existantes, un script de migration sera fourni :

```sql
-- scripts/migrate_ai_table_prefix.sql
ALTER TABLE "agents" RENAME TO "ai_agents";
ALTER TABLE "providers" RENAME TO "ai_providers";
ALTER TABLE "conversations" RENAME TO "ai_conversations";
ALTER TABLE "messages" RENAME TO "ai_messages";
ALTER TABLE "tools" RENAME TO "ai_tools";
ALTER TABLE "skills" RENAME TO "ai_skills";
ALTER TABLE "agent_skill_assignments" RENAME TO "ai_agent_skill_assignments";
ALTER TABLE "executions" RENAME TO "ai_executions";
ALTER TABLE "execution_steps" RENAME TO "ai_execution_steps";
ALTER TABLE "graphs" RENAME TO "ai_graphs";
ALTER TABLE "memories" RENAME TO "ai_memories";
ALTER TABLE "knowledge_sources" RENAME TO "ai_knowledge_sources";
ALTER TABLE "documents" RENAME TO "ai_documents";
ALTER TABLE "chunks" RENAME TO "ai_chunks";
```

---

## Plan d'implémentation

### Phase 1 — Préfixe `ai_` sur les tables + modèle de logging (sprint courant)

| Tâche | Fichiers impactés | Effort |
|-------|------------------|--------|
| Renommer `table_name` dans tous les `__table_meta__` AI | `models/ai/*.py` (14 fichiers) | S |
| Mettre à jour les `foreign_key` pour pointer vers `ai_*` | `models/ai/*.py` (12 FK) | S |
| Créer `models/logging/__init__.py` et `log_entry.py` | Nouveaux fichiers | M |
| Créer `WorkflowLog` avec `__table_meta__` et 10 indexes | `models/logging/log_entry.py` | M |
| Créer `WorkflowLogQuery` read-model | `models/logging/log_entry.py` | S |
| Créer `RepositoryLogHandler` dans `logging/handlers.py` | `logging/handlers.py` | M |
| Marquer `SQLiteLogHandler` comme DEPRECATED | `logging/handlers.py` | XS |
| Ajouter `storage.logs` raccourci nommé dans `UnifiedStorage` | `adapters/storage/unified.py` | XS |
| Ajouter `import models.logging` dans la chaîne d'import de `UnifiedStorage` | `adapters/storage/unified.py` | XS |
| Mettre à jour `logging/__init__.py` pour exporter `RepositoryLogHandler` | `logging/__init__.py` | XS |
| Mettre à jour les tests storage qui vérifient des noms de tables | `tests/storage/*.py` | S |
| Créer les tests `test_logging_persistence.py` | `tests/storage/test_logging_persistence.py` | M |
| Vérifier `health_check()` et `get_table_names()` | `adapters/storage/unified.py` | XS |
| Créer le script SQL de migration | `scripts/migrate_ai_table_prefix.sql` | XS |

**Critère de validation** : tous les 82+ tests storage (incluant les nouveaux tests logging) + les 1120 tests globaux passent. La table `log_entries` est créée par `storage.migrate()`. Le `RepositoryLogHandler` persiste et filtre les logs avec corrélation.

### Phase 2 — Réorganisation `models/` en sous-packages (sprint suivant)

| Tâche | Fichiers impactés | Effort |
|-------|------------------|--------|
| Créer `models/workflow/__init__.py` | Nouveau fichier | XS |
| Copier `step.py`, `job.py`, `run.py`, `connector.py` dans `models/workflow/` | 4 fichiers copiés | S |
| Créer `models/pipeline/__init__.py` | Nouveau fichier | XS |
| Copier `pipeline.py`, `pipeline_run.py` dans `models/pipeline/` | 2 fichiers copiés | S |
| Vérifier que `models/logging/` (créé en phase 1) est cohérent | 1 fichier | XS |
| Convertir les fichiers racine en shims DEPRECATED | 6 fichiers modifiés | S |
| Mettre à jour `models/__init__.py` pour importer depuis les sous-packages | 1 fichier | S |
| Mettre à jour les imports internes (`pipeline_run.py` importe `run.py`) | 2-3 fichiers | S |
| Vérifier tous les tests | Tests existants | M |

**Critère de validation** : tous les tests passent, `mypy` clean, aucun import cassé.

### Phase 3 — Migration des modèles core vers `PersistableModel` (sprint dédié)

| Tâche | Fichiers impactés | Effort |
|-------|------------------|--------|
| Vague 1 : `ConnectorRef`, `ConnectorOutcome`, `StepLog` → Pydantic | `models/workflow/connector.py`, `models/workflow/run.py` | M |
| Vague 2 : `StepRun`, `JobRun`, `StageRun`, `PipelineRun` → Pydantic | `models/workflow/run.py`, `models/pipeline/pipeline_run.py` | L |
| Vague 3 : `Step`, `SubJob`, `Job`, `Pipeline`, `PipelineStage` → Pydantic | `models/workflow/step.py`, `models/workflow/job.py`, `models/pipeline/pipeline.py` | L |
| Ajouter `__table_meta__` avec préfixe `wf_`/`pl_` | Tous les modèles convertis | M |
| Supprimer `SQLiteStorage.SCHEMA_SQL` (DDL manuel) | `adapters/storage/sqlite.py` | M |
| Migrer les backends existants vers `Repository[T]` | `adapters/storage/*.py` | L |
| Supprimer les méthodes CRUD manuelles dans les backends | `adapters/storage/*.py` | M |
| Tests : vérifier `to_dict()` / `from_dict()` rétrocompatibilité | `tests/` | L |

**Critère de validation** : un seul système de persistence (`Repository[T]`), zéro DDL manuel, tous les tests verts.

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|--------|------------|--------|-----------|
| **Imports cassés** par la réorganisation `models/` | Moyenne | Élevé | Shims de compatibilité + `models/__init__.py` re-export |
| **Tests rouges** après renommage des tables | Faible | Moyen | Le code ne contient pas de noms de tables en dur (lu depuis `__table_meta__`) |
| **Migration dataclass → Pydantic** casse `frozen=True` | Moyenne | Élevé | Pydantic `model_config = ConfigDict(frozen=True)` — équivalent exact |
| **Callables non-sérialisables** (`handler`, `condition`) | Connue | Moyen | Exclusion via `Field(exclude=True)` + reconstitution via `_restore_handler()` |
| **Performance** Pydantic vs dataclass sur modèles simples | Faible | Faible | Négligeable — Pydantic v2 est comparable en perf à dataclass pour la construction |
| **Volume de logs** dans la même base SQLite | Moyenne | Moyen | Batch writes (buffer), `delete_where(timestamp__lt=...)` pour purge, WAL mode activé |
| **Contention SQLite** si logging intense + CRUD concurrent | Faible | Moyen | WAL mode (déjà activé par `UnifiedStorage`), buffer avec batch_size configurable, possibilité d'utiliser `QueueHandler` pour du logging async |

---

## Résumé des décisions

| # | Décision | Statut | Phase |
|---|----------|--------|-------|
| **D1** | Préfixer toutes les tables AI par `ai_` | ✅ Implémentée | Phase 1 |
| **D2** | Migrer progressivement les modèles core vers `PersistableModel` + nettoyage DB | ✅ Implémentée | Phase 3 |
| **D3** | Réorganiser `models/` en `workflow/`, `pipeline/`, `ai/`, `logging/` | ✅ Implémentée | Phase 2 |
| **D4** | Intégrer le logging dans le système de persistence unifié (`WorkflowLog` + `RepositoryLogHandler`) | ✅ Implémentée | Phase 1 |

### Ce que cette ADR NE fait PAS

- ❌ **Ne modifie pas** l'architecture hexagonale (ports/adapters)
- ❌ **Ne supprime pas** les backends existants (`SQLiteStorage`, `InMemoryStorage`)
- ❌ **Ne casse pas** les imports existants (shims de compatibilité)
- ❌ **Ne modifie pas** le module `enums.py` (reste partagé à la racine de `models/`)
- ❌ **Ne supprime pas** `SQLiteLogHandler` — il est marqué DEPRECATED mais reste fonctionnel
- ❌ **N'introduit pas** de dépendance externe nouvelle

---

## Note d'implémentation (12 avril 2026)

ADR-018 a été **intégralement implémentée** au cours du sprint du 12 avril 2026. Voici le résumé des changements livrés.

### D1 — Préfixe `ai_` sur toutes les tables AI ✅

- 14 `table_name` renommés dans `models/ai/*.py` (agent, conversation, execution, execution_steps, graphs, memories, knowledge_sources, documents, chunks, messages, providers, tools, skills, agent_skill_assignments)
- 12 clés étrangères (`foreign_key`) mises à jour pour pointer vers les nouvelles tables `ai_*`
- Script de migration créé : `scripts/migrate_ai_table_prefix.sql`

### D2 — Migration progressive des modèles core vers `PersistableModel` ✅

Implémentée en 3 vagues dans le sprint du 12 avril 2026.

**Vague 1 — Modèles embedded** (`connector.py`) :
- `ConnectorRef` : `@dataclass(frozen=True)` → `BaseModel` avec `model_config = {"frozen": True}`, `@model_validator(mode="after")` pour dériver `connector_type`
- `ConnectorOutcome` : `@dataclass` → `BaseModel` mutable
- `from pydantic import BaseModel, Field, model_validator` ; suppression de `from dataclasses import dataclass, field`

**Vague 2 — Modèles runtime** (`run.py`, `pipeline_run.py`) :
- `StepLog` → `PersistableModel` avec `__table_meta__` (table `wf_step_logs`, usage embedded)
- `StepRun` → `@ModelRegistry.register class StepRun(PersistableModel)` (table `wf_step_runs`, 4 indexes, FK → `wf_job_runs`)
- `JobRun` → `@ModelRegistry.register class JobRun(PersistableModel)` (table `wf_job_runs`, 4 indexes)
- `StageRun` → `@ModelRegistry.register class StageRun(PersistableModel)` (table `pl_stage_runs`, 3 indexes, FK → `pl_pipeline_runs`)
- `PipelineRun` → `@ModelRegistry.register class PipelineRun(PersistableModel)` (table `pl_pipeline_runs`, 4 indexes)

**Vague 3 — Modèles design-time** (`step.py`, `job.py`, `pipeline.py`) :
- `Step` : `@dataclass(frozen=True)` → `BaseModel` avec `model_config = {"frozen": True, "arbitrary_types_allowed": True}`, `handler` et `condition` : `Field(exclude=True)`
- `SubJob` : `@dataclass(frozen=True)` → `BaseModel` avec `model_config = {"frozen": True}`
- `Job` → `@ModelRegistry.register class Job(PersistableModel)` (table `wf_jobs`, 2 indexes), `model_config = {"frozen": True}`
- `PipelineStage` → `@ModelRegistry.register class PipelineStage(PersistableModel)` (table `pl_pipeline_stages`, composite PK `job_name`+`pipeline_name`, 2 indexes)
- `Pipeline` → `@ModelRegistry.register class Pipeline(PersistableModel)` (table `pl_pipelines`, 3 indexes)

**Corrections collatérales** :
- `SchemaGenerator.generate_create_table()` — support des clés primaires composites (table-level `PRIMARY KEY (col1, col2)` quand plusieurs colonnes ont `primary_key=True`)
- `job_decorator.py` — `tags: dict[str, str]` → `tags: list[str]` pour correspondre au champ `Job.tags: list[str]`
- Tests mis à jour : `FrozenInstanceError` (dataclasses) → `pydantic.ValidationError`, `dataclasses.replace(job, ...)` → `job.model_copy(update={...})`, constructions positionnelles `Step("name", StepType.X)` → `Step(name="name", step_type=StepType.X)` dans `test_core_models.py`
- `Callable` sorti du bloc `TYPE_CHECKING` dans `step.py` et `pipeline.py` (requis par Pydantic pour la résolution des annotations)

### D3 — Réorganisation `models/` en sous-packages ✅

Nouveaux fichiers créés :
- `models/workflow/__init__.py` — re-exports : `Step`, `SubJob`, `Job`, `JobRun`, `StepRun`, `StepLog`, `ConnectorRef`, `ConnectorOutcome`, `generate_id`, `utc_now`
- `models/workflow/connector.py` — `ConnectorRef`, `ConnectorOutcome`
- `models/workflow/step.py` — `Step`, `SubJob`
- `models/workflow/job.py` — `Job`
- `models/workflow/run.py` — `StepLog`, `StepRun`, `JobRun`, `generate_id`, `utc_now`
- `models/pipeline/__init__.py` — re-exports : `Pipeline`, `PipelineStage`, `PipelineRun`, `StageRun`
- `models/pipeline/pipeline.py` — `Pipeline`, `PipelineStage`
- `models/pipeline/pipeline_run.py` — `PipelineRun`, `StageRun`

Fichiers plats racine supprimés directement (pas de shims — décision explicite de l'équipe pour forcer la mise à jour des imports dès v0.9.0) :
`models/connector.py`, `models/step.py`, `models/job.py`, `models/run.py`, `models/pipeline.py`, `models/pipeline_run.py`

Tous les consommateurs dans `src/` et `tests/` mis à jour vers les imports canoniques (`models.workflow.*`, `models.pipeline.*`). `models/__init__.py` et `pyworkflow_engine/__init__.py` (`_LAZY_IMPORTS`) mis à jour.

### D4 — Intégration logging dans le système de persistence unifié ✅

Nouveaux fichiers :
- `models/logging/__init__.py` — re-exports : `WorkflowLog`, `WorkflowLogQuery`
- `models/logging/log_entry.py` — `WorkflowLog` (`PersistableModel`, table `log_entries`, 10 indexes) + `WorkflowLogQuery` (DTO read-model)

Fichiers modifiés :
- `logging/handlers.py` — `RepositoryLogHandler` ajouté, `SQLiteLogHandler` marqué `DEPRECATED` avec `warnings.warn()`
- `logging/__init__.py` — `RepositoryLogHandler` exporté
- `adapters/storage/unified.py` — propriété `logs` ajoutée, `import pyworkflow_engine.models.logging` ajouté à la chaîne d'import

Tests ajoutés : `tests/storage/test_logging_persistence.py` (33 tests couvrant création, filtrage, corrélation, `WorkflowLogQuery`, `RepositoryLogHandler`).

### Nettoyage base de données — Suppression des anciennes tables ✅

Après l'application de la migration `python -m scripts.python.migrate`, la base `workflow.db` contenait **44 tables** : les nouvelles tables préfixées (`ai_*`, `wf_*`, `pl_*`, `log_entries`) coexistaient avec les 21 anciennes tables non-préfixées (artefacts pre-ADR-018).

**Script créé** : `scripts/cleanup_old_tables.sql`

**Tables supprimées (21)** :
- Domaine AI (remplacées par `ai_*`) : `agents`, `agent_skill_assignments`, `chunks`, `conversations`, `documents`, `execution_steps`, `executions`, `graphs`, `knowledge_sources`, `memories`, `messages`, `providers`, `skills`, `tools`
- Domaine Workflow (remplacées par `wf_*`) : `job_runs`, `jobs`, `step_runs`, `workflow_logs`
- Domaine Pipeline (remplacées par `pl_*`) : `pipeline_runs`, `stage_runs`
- Infrastructure (obsolète) : `schema_version`

**Application** :
```bash
cp workflow.db workflow.db.bak   # backup préventif
sqlite3 workflow.db < scripts/cleanup_old_tables.sql
# ✅ Toutes les anciennes tables ont été supprimées.
```

**Résultat** : `workflow.db` passe de **44 → 23 tables** (14 `ai_*` + 3 `wf_*` + 4 `pl_*` + `log_entries` + `sqlite_sequence`).

> **Note** : Les données dans les anciennes tables (`job_runs`×58, `jobs`×16, `step_runs`×192, `workflow_logs`×1060) étaient des artefacts de tests précédents. Les nouvelles tables ont un schéma étendu incompatible — aucune migration de données n'était nécessaire ni pertinente.

### Résultat final

```
1120 passed, 21 skipped, 4 failed (pre-existing — test_ingestion_imf.py uniquement)
workflow.db : 23 tables (ai_* × 14, wf_* × 3, pl_* × 4, log_entries × 1, sqlite_sequence × 1)
```

Tous les tests ADR-018 passent. Les 4 échecs pré-existants (`test_ingestion_imf.py`) sont indépendants de cette ADR.

---

## Références

- ADR-006 — Architecture hexagonale (`ports/` + `adapters/`)
- ADR-012 — Renommage `persistence` → `storage`
- ADR-013 — Intégration AI Engine (modèles Pydantic dans `models/ai/`)
- ADR-016 — Plan maître d'intégration
- ADR-017 — Couche de persistence unifiée (ModelRegistry + Repository CRUD)
- [Django Model Meta options](https://docs.djangoproject.com/en/5.0/ref/models/options/)
- [Repository Pattern (Martin Fowler)](https://martinfowler.com/eaaCatalog/repository.html)
- [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html)
