# ADR-015 — Plan d'implémentation unifié : intégration AI Engine + modèle Pipeline

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-015                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | 🔄 Remplacée par ADR-016            |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-013 (intégration ai_engine), ADR-014 (modèle Pipeline + @pipeline/@stage), ADR-005 (décorateurs), ADR-006 (hexagonal) |
| **Version cible** | v0.8.0                         |
| **Fusionne** | ADR-013 + ADR-014                  |

---

## Motivation

ADR-013 (intégration `ai_engine`) et ADR-014 (modèle `Pipeline` + `@pipeline`/`@stage`) ciblent tous les deux la v0.8.0 et touchent les **mêmes fichiers et couches**. Les implémenter séparément créerait des conflits de fusion, des incohérences de nommage et du travail doublé.

Cette ADR-015 fusionne les deux en un **plan d'implémentation unique et ordonné**.

---

## Analyse de cohérence ADR-013 ↔ ADR-014

### Ce qui s'intègre bien naturellement

| Aspect | Cohérence | Détails |
|---|---|---|
| **Hiérarchie Step → Job → Pipeline** | ✅ Parfait | ADR-014 ajoute le 3ᵉ niveau. ADR-013 ajoute l'IA transversalement à chaque niveau. Pas de conflit. |
| **Modèle runtime** | ✅ Parfait | `PipelineRun` contient des `StageRun` qui contiennent des `JobRun` qui contiennent des `StepRun`. Les champs IA optionnels d'ADR-013 s'ajoutent à `StepRun`/`JobRun` sans impacter `PipelineRun`/`StageRun`. |
| **Decorators** | ✅ Parfait | `@step` → `@job` → `@pipeline` forme une hiérarchie symétrique. Les steps IA sont des `@step` ordinaires avec `step_type=StepType.LLM_CALL`. |
| **Storage** | ✅ Compatible | ADR-014 ajoute les tables `pipelines`/`pipeline_runs`/`stage_runs`. ADR-013 ajoute les tables IA (agents, providers, etc.). Pas de collision. |
| **Facade** | ✅ Compatible | `WorkflowEngine` gagne `run_pipeline()` (ADR-014) et les méthodes IA (ADR-013) indépendamment. |
| **`pyproject.toml`** | ✅ Compatible | ADR-014 n'ajoute aucune dépendance. ADR-013 ajoute des extras optionnels `[ai]`. |

### Les frictions détectées — et leurs résolutions

#### Friction 1 : `StepType` doit être fusionné en une seule passe

ADR-013 propose de fusionner `StepType` (workflow) + `StepType` (ai_engine). ADR-014 ne touche pas `StepType` mais y fait référence. **Résolution** : fusionner `StepType` une seule fois, dès la Phase 1, avec toutes les valeurs des deux sources.

```python
class StepType(Enum):
    """Types de steps dans un workflow — classiques ET IA."""

    # ── Workflow classique (existant) ──
    FUNCTION = "function"
    SUBPROCESS = "subprocess"
    HTTP_REQUEST = "http_request"
    SQL_QUERY = "sql_query"
    HUMAN_TASK = "human_task"
    EXTERNAL_TASK = "external_task"
    SUB_WORKFLOW = "sub_workflow"

    # ── IA (depuis ai_engine/types.py) ──
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AI_DECISION = "ai_decision"
    SKILL_EXECUTION = "skill_execution"
```

#### Friction 2 : `RunStatus` — ADR-013 veut fusionner, il a déjà `CANCELLED`

Bonne nouvelle : `RunStatus` de `pyworkflow_engine` contient **déjà** `CANCELLED` + `WAITING_HUMAN`, `WAITING_EXTERNAL`, `SUSPENDED`, `TIMEOUT` — il est **plus riche** que `ExecutionStatus` d'`ai_engine`. Aucune modification nécessaire. `ExecutionStatus` est simplement un sous-ensemble de `RunStatus`.

**Résolution** : `RunStatus` existant est conservé tel quel. On ajoute uniquement un alias pour la rétrocompatibilité `ai_engine` :

```python
# Dans models/ai/types.py
ExecutionStatus = RunStatus  # Alias de rétrocompatibilité
```

#### Friction 3 : `PipelineRun.context` vs `JobRun.context` — propagation dans les workflows IA

ADR-014 propage le contexte entre stages via `context_mapping`. ADR-013 enrichit le contexte avec des données IA (`token_usage`, `ai_result`, etc.). **Pas de conflit réel** : les données IA sont injectées dans le contexte d'un `StepRun`/`JobRun`, et la propagation inter-stages de `PipelineRun` les transporte naturellement.

Cependant, il faut **documenter** que les clés de contexte IA sont préfixées pour éviter les collisions :

```python
# Convention de nommage dans le contexte partagé
context = {
    # Données métier (stages classiques)
    "raw_data": [...],
    "kpi_results": {...},

    # Données IA (préfixées _ai_)
    "_ai_classification": {"content": "...", "token_usage": {...}},
    "_ai_summary": "...",
    "_ai_agent_id": "agent-uuid",
}
```

#### Friction 4 : `dataclass` (workflow) vs `Pydantic BaseModel` (ai_engine)

`pyworkflow_engine` utilise des **dataclasses stdlib** (zéro dépendance). `ai_engine` utilise **Pydantic BaseModel** (dépendance). ADR-013 propose de garder les modèles IA en Pydantic dans `models/ai/`.

**Résolution** : les deux cohabitent. La frontière est claire :

| Couche | Technologie | Raison |
|---|---|---|
| `models/enums.py`, `models/job.py`, `models/step.py`, `models/run.py`, `models/pipeline.py`, `models/pipeline_run.py` | `dataclass` (stdlib) | Zéro dépendance pour le core |
| `models/ai/*.py` | Pydantic `BaseModel` | Validation riche, sérialisation JSON, compat API providers LLM |

**Contrainte** : les modèles `dataclass` ne doivent **jamais** importer depuis `models/ai/`. L'inverse est autorisé (les modèles IA peuvent référencer `RunStatus`, `StepType`, etc.).

#### Friction 5 : `TriggerType` — ADR-013 veut ajouter `AI`, ADR-014 veut ajouter un `schedule` sur Pipeline

Pas de conflit : `TriggerType.AI` est ajouté dans l'enum. `Pipeline.schedule` est une expression cron string — le `ScheduleTrigger` existant la consomme. Un futur `AITrigger` utilisera `TriggerType.AI`.

```python
class TriggerType(Enum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    SIGNAL = "signal"
    WEBHOOK = "webhook"
    FILE_WATCHER = "file_watcher"
    AI = "ai"  # 🆕 ADR-013
```

#### Friction 6 : double EventBus — `ai_engine/events/` et rien côté workflow

`pyworkflow_engine` n'a pas d'EventBus. `ai_engine` en a un riche (sync/async, wildcard, middleware). ADR-014 n'en a pas besoin directement, mais un `PipelineRun` pourrait émettre des événements (`pipeline.started`, `stage.completed`, etc.).

**Résolution** : l'EventBus est promu au niveau top-level dans `events/` dès la Phase 2. ADR-014 peut optionnellement émettre des événements `pipeline.*` si l'EventBus est disponible.

#### Friction 7 : `BaseStorage` — deux extensions indépendantes

ADR-014 ajoute : `save_pipeline()`, `get_pipeline()`, `save_pipeline_run()`, `list_pipeline_runs()`.
ADR-013 ajoute : `save_agent()`, `get_agent()`, `save_provider()`, `save_execution()`.

**Résolution** : les deux sets de méthodes sont ajoutés à `BaseStorage` avec une implémentation par défaut `NotImplementedError`. Pas de conflit — ce sont des méthodes sur des entités différentes.

```python
class BaseStorage(ABC):
    # ── Existant ──
    def save_job(self, job: Job) -> None: ...
    def save_run(self, run: JobRun) -> None: ...

    # ── ADR-014 (Pipeline) ──
    def save_pipeline(self, pipeline: Pipeline) -> None:
        raise NotImplementedError("Pipeline storage not implemented")
    def save_pipeline_run(self, run: PipelineRun) -> None:
        raise NotImplementedError("PipelineRun storage not implemented")

    # ── ADR-013 (IA) ──
    def save_agent(self, agent: Agent) -> Agent:
        raise NotImplementedError("AI storage not implemented")
    def save_provider(self, provider: LLMProviderConfig) -> LLMProviderConfig:
        raise NotImplementedError("AI storage not implemented")
```

---

## Architecture cible unifiée

### Structure des dossiers

```
src/pyworkflow_engine/
│
├── models/                              # Modèles de domaine
│   ├── __init__.py                      # Re-exports publics
│   ├── enums.py                         # ✅ Existant — enrichi (StepType IA + TriggerType.AI)
│   ├── job.py                           # ✅ Existant
│   ├── step.py                          # ✅ Existant
│   ├── run.py                           # ✅ Existant — étendu (champs IA optionnels)
│   ├── pipeline.py                      # 🆕 ADR-014 — Pipeline, PipelineStage
│   ├── pipeline_run.py                  # 🆕 ADR-014 — PipelineRun, StageRun
│   │
│   └── ai/                              # 🆕 ADR-013 — Modèles IA (Pydantic)
│       ├── __init__.py
│       ├── types.py                     # Enums exclusifs IA (ProviderType, AgentRole, ...)
│       ├── agent.py                     # Agent, AgentConfig
│       ├── provider.py                  # LLMProviderConfig, ProviderSettings
│       ├── conversation.py              # Conversation
│       ├── message.py                   # Message, ToolCall, ToolResult, TokenUsage
│       ├── tool.py                      # ToolDefinition
│       ├── skill.py                     # Skill, AgentSkillAssignment
│       ├── memory.py                    # AgentMemory
│       ├── knowledge.py                 # KnowledgeSource, Document, Chunk
│       └── graph.py                     # Graph, GraphNode, GraphEdge
│
├── ports/                               # Interfaces (contrats abstraits)
│   ├── __init__.py
│   ├── executor.py                      # ✅ Existant
│   ├── storage.py                       # ✅ Existant → étendu (Pipeline + IA)
│   ├── trigger.py                       # ✅ Existant
│   │
│   └── ai/                              # 🆕 ADR-013 — Ports IA
│       ├── __init__.py
│       ├── llm.py                       # BaseLLMClient
│       ├── tool.py                      # BaseTool
│       ├── skill.py                     # BaseSkill
│       └── storage.py                   # BaseAIStorage
│
├── adapters/                            # Implémentations concrètes
│   ├── api/                             # ✅ Existant
│   ├── celery/                          # ✅ Existant
│   ├── cli/                             # ✅ Existant → enrichi (commandes pipeline + IA)
│   ├── executors/                       # ✅ Existant
│   ├── gui/                             # ✅ Existant → enrichi (page Pipelines)
│   ├── mcp/                             # ✅ Existant
│   ├── snowflake/                       # ✅ Existant
│   ├── sqlalchemy/                      # ✅ Existant
│   ├── storage/                         # ✅ Existant → enrichi (tables pipeline + IA)
│   ├── structlog/                       # ✅ Existant
│   ├── triggers/                        # ✅ Existant
│   ├── tui/                             # ✅ Existant
│   │
│   └── ai/                              # 🆕 ADR-013 — Adapters IA
│       ├── __init__.py
│       ├── llm/                         # Factory LLM (openai, anthropic, ollama, ...)
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── factory.py
│       │   ├── openai.py
│       │   ├── anthropic.py
│       │   ├── ollama.py
│       │   ├── gemini.py
│       │   └── groq.py
│       ├── tools/                       # Tools concrets (calculator, search, http)
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── registry.py
│       │   ├── executor.py
│       │   ├── calculator.py
│       │   ├── web_search.py
│       │   └── http_client.py
│       ├── skills/                      # Skills
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── registry.py
│       ├── storage/                     # Storage entités IA
│       │   ├── __init__.py
│       │   ├── memory.py
│       │   └── sqlite.py
│       ├── triggers/                    # Triggers IA
│       │   ├── __init__.py
│       │   └── ai_trigger.py
│       ├── steps/                       # Steps IA
│       │   ├── __init__.py
│       │   └── ai_step.py
│       ├── executors/                   # Executors IA
│       │   ├── __init__.py
│       │   └── agent_executor.py
│       ├── bridges/                     # Ponts workflow ↔ IA
│       │   ├── __init__.py
│       │   └── job_as_tool.py
│       ├── django/                      # Adapter Django IA
│       │   ├── __init__.py
│       │   ├── orm_models.py
│       │   ├── admin.py
│       │   ├── serializers.py
│       │   └── views.py
│       └── fastapi/                     # Adapter FastAPI IA
│           ├── __init__.py
│           ├── routers/
│           ├── schemas.py
│           └── dependencies.py
│
├── engine/                              # Orchestration / logique métier
│   ├── __init__.py
│   ├── context.py                       # ✅ Existant
│   ├── dag.py                           # ✅ Existant
│   ├── parallel_runner.py               # ✅ Existant
│   ├── retry.py                         # ✅ Existant
│   ├── runner.py                        # ✅ Existant
│   ├── suspension.py                    # ✅ Existant
│   ├── pipeline_runner.py               # 🆕 ADR-014 — PipelineRunner (promu depuis pipelines/shared/)
│   │
│   └── ai/                              # 🆕 ADR-013 — Services IA
│       ├── __init__.py
│       ├── agent_service.py
│       ├── conversation_service.py
│       └── skill_registry.py
│
├── events/                              # 🆕 ADR-013 — EventBus unifié
│   ├── __init__.py
│   ├── bus.py                           # EventBus (thread-safe, sync/async)
│   └── events.py                        # Événements workflow + pipeline + IA
│
├── config/                              # ✅ Existant
│   ├── __init__.py
│   ├── base.py
│   ├── engine.py
│   ├── executor.py
│   ├── logging.py
│   ├── settings.py
│   ├── storage.py
│   └── ai.py                           # 🆕 ADR-013 — AISettings
│
├── decorators/                          # ✅ Existant
│   ├── __init__.py
│   ├── step_decorator.py               # ✅ @step
│   ├── job_decorator.py                # ✅ @job
│   └── pipeline_decorator.py           # 🆕 ADR-014 — @pipeline, @stage
│
├── logging/                             # ✅ Existant
├── exceptions.py                        # ✅ Existant → enrichi (exceptions IA)
├── facade.py                            # ✅ Existant → enrichi (run_pipeline + API IA)
└── py.typed
```

### Diagramme de composition

```
Pipeline("weekly-countries-to-dwh")          ← ADR-014
│   triggered_by: TriggerType.SCHEDULE
│   schedule: "0 1 * * 0"
│
├─ PipelineStage("ingestion")               ← ADR-014
│  └─ Job("ingestion-restcountries")
│     ├─ Step("fetch_raw")                   ← classique
│     ├─ Step("validate_raw")                ← classique
│     └─ Step("ai_classify_sources")         ← 🧠 ADR-013 (AIStep, StepType.LLM_CALL)
│
├─ PipelineStage("transformation")          ← ADR-014
│  └─ Job("transform-stg-restcountries")
│     ├─ Step("clean_types")                 ← classique
│     └─ Step("write_staging")               ← classique
│
├─ PipelineStage("enrichment")              ← ADR-014
│  └─ Job("ai-enrich-countries")
│     └─ Step("ai_enrich")                   ← 🧠 ADR-013 (agent enrichit les données)
│
└─ PipelineStage("quality", continue_on_failure=True)  ← ADR-014
   └─ Job("quality-check")
      └─ Step("check_completeness")          ← classique
```

Runtime :

```
PipelineRun                                  ← ADR-014
├─ StageRun("ingestion")                     ← ADR-014
│  └─ JobRun("ingestion-restcountries")      ← existant
│     ├─ StepRun("fetch_raw")                ← existant
│     ├─ StepRun("validate_raw")             ← existant
│     └─ StepRun("ai_classify_sources")      ← existant + champs IA (ADR-013)
│        ├─ agent_id: "analyst-uuid"
│        └─ token_usage: {prompt: 450, completion: 120}
├─ StageRun("transformation")
│  └─ JobRun → StepRun(s)
├─ StageRun("enrichment")
│  └─ JobRun → StepRun(s) avec token_usage
└─ StageRun("quality")
   └─ JobRun → StepRun(s)
```

---

## Scénarios d'usage combinés

### Scénario 1 : Pipeline classique avec une étape IA (ADR-014 + ADR-013)

```python
from pyworkflow_engine.decorators import step, job, stage, pipeline
from pyworkflow_engine.models.enums import StepType

@step(name="extract", timeout=30)
def extract_data(source: str = "api") -> dict:
    return {"records": fetch_from_api(source)}

@step(name="ai_classify", step_type=StepType.LLM_CALL)
def ai_classify_anomalies(records: list = None) -> dict:
    """Step IA — classifie les anomalies via un agent LLM."""
    # Exécuté par l'AIStep adapter dans engine/runner.py
    return {"prompt": f"Classify anomalies: {records}"}

@step(name="load")
def load_to_warehouse(records: list = None, ai_result: dict = None) -> dict:
    return {"loaded": len(records or [])}

@job(name="etl-with-ai")
def etl_job():
    data = extract_data()
    classified = ai_classify_anomalies(records=data["records"])
    load_to_warehouse(records=data["records"], ai_result=classified)

@stage(job=etl_job)
def etl_stage():
    """ETL avec classification IA."""

@stage(job=quality_job, continue_on_failure=True)
def quality_stage():
    """Vérification post-ETL."""

@pipeline(
    name="daily-etl-with-ai",
    schedule="0 2 * * *",
    owner="data-team@company.com",
)
def daily_pipeline():
    etl_stage()
    quality_stage()

# Exécution
p = daily_pipeline.build()
engine = WorkflowEngine()
pipeline_run = engine.run_pipeline(p, initial_context={"date": "2026-04-12"})
print(pipeline_run.summary)
```

### Scénario 2 : Agent IA orchestre une pipeline entière (ADR-013)

```python
from pyworkflow_engine.adapters.ai.bridges import JobAsTool
from pyworkflow_engine.adapters.ai.executors import AgentExecutor

# Exposer la pipeline comme tool pour un agent superviseur
pipeline_tool = PipelineAsTool(engine, daily_pipeline.build())
agent_service.register_tool(supervisor_agent, pipeline_tool.to_tool_definition())

# L'agent décide quand et comment lancer la pipeline
response = agent_service.chat(
    agent=supervisor_agent,
    user_message="Run the daily ETL pipeline for yesterday.",
)
```

### Scénario 3 : Pipeline déclarée avec stages mixtes (classiques + IA)

```python
@pipeline(
    name="monthly-reporting",
    schedule="0 6 1 * *",
    tags=["monthly", "reporting"],
)
def monthly_report():
    data_extraction()        # Stage classique
    kpi_computation()        # Stage classique
    ai_analysis()            # Stage IA — agent analyse les KPIs
    report_generation()      # Stage classique — génère le PDF
    ai_executive_summary()   # Stage IA — agent rédige le résumé exécutif
```

---

## Dépendances optionnelles (`pyproject.toml`)

```toml
[project]
name = "pyworkflow-engine"
version = "0.8.0"

# ⚠️ ZÉRO dépendance obligatoire pour le core
# (Step, Job, Pipeline, StepRun, JobRun, PipelineRun, @step, @job, @pipeline)
dependencies = []

[project.optional-dependencies]
# ── Existants (inchangés) ──
django = ["django>=4.2", "djangorestframework>=3.14"]
fastapi = ["fastapi>=0.100", "uvicorn>=0.20"]
celery = ["celery>=5.3", "redis>=5.0"]
sqlalchemy = ["sqlalchemy>=2.0"]
cli = ["typer>=0.9", "rich>=13.0"]
tui = ["textual>=1.0", "rich>=13.0"]
gui = ["nicegui>=2.0"]
structlog = ["structlog>=24.0"]
api = ["fastapi>=0.100", "uvicorn[standard]>=0.20", "sse-starlette>=2.0"]
dataplatform = ["duckdb>=1.0", "pyarrow>=15.0"]

# ── Nouveaux (IA) — ADR-013 ──
pydantic = ["pydantic>=2.0", "pydantic-settings>=2.0"]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.30"]
ollama = ["ollama>=0.2"]
gemini = ["google-generativeai>=0.5"]
groq = ["groq>=0.5"]
llm = [
    "pyworkflow-engine[pydantic]",
    "pyworkflow-engine[openai]",
    "pyworkflow-engine[anthropic]",
    "pyworkflow-engine[ollama]",
    "pyworkflow-engine[gemini]",
    "pyworkflow-engine[groq]",
]
ai-tools = ["duckduckgo-search>=5.0", "httpx>=0.27"]
ai = ["pyworkflow-engine[llm,ai-tools]"]

# ── Combinaisons ──
ai-django = ["pyworkflow-engine[ai,django]"]
ai-fastapi = ["pyworkflow-engine[ai,fastapi]"]

# ── Dev (inchangé) ──
dev = ["pytest>=8.0", "pytest-cov>=4.0", "ruff>=0.4", "mypy>=1.10"]

# ── Tout ──
all = [
    "pyworkflow-engine[ai,django,fastapi,celery,sqlalchemy,cli,tui,gui,api,structlog,dataplatform]",
]
```

---

## Plan d'implémentation — 6 phases ordonnées

### Phase 1 — Fondations : enums unifiés et modèle Pipeline (semaine 1)

> **Objectif** : poser les bases sans casser l'existant.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 1.1 | Ajouter `StepType.LLM_CALL`, `.TOOL_CALL`, `.TOOL_RESULT`, `.AI_DECISION`, `.SKILL_EXECUTION` | `models/enums.py` | 013 |
| 1.2 | Ajouter `TriggerType.AI` | `models/enums.py` | 013 |
| 1.3 | Créer `models/pipeline.py` (`Pipeline`, `PipelineStage`) avec `to_dict()`/`from_dict()` | `models/pipeline.py` 🆕 | 014 |
| 1.4 | Créer `models/pipeline_run.py` (`PipelineRun`, `StageRun`) avec transitions d'état | `models/pipeline_run.py` 🆕 | 014 |
| 1.5 | Exporter dans `models/__init__.py` | `models/__init__.py` | 014 |
| 1.6 | Tests unitaires | `tests/unit/test_pipeline_model.py`, `tests/unit/test_pipeline_run.py` 🆕 | 014 |

**Validations** : `pytest tests/unit/`, `mypy`, `ruff`. Aucun test existant ne casse.

### Phase 2 — Decorators Pipeline + EventBus (semaine 2)

> **Objectif** : API déclarative `@pipeline`/`@stage` + EventBus unifié.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 2.1 | Créer `decorators/pipeline_decorator.py` (`@pipeline`, `@stage`, `PipelineBuilder`, `StageSpec`) | `decorators/pipeline_decorator.py` 🆕 | 014 |
| 2.2 | Exporter dans `decorators/__init__.py` | `decorators/__init__.py` | 014 |
| 2.3 | Promouvoir `ai_engine/events/` dans `events/` (EventBus unifié) | `events/bus.py`, `events/events.py` 🆕 | 013 |
| 2.4 | Ajouter les événements Pipeline (`pipeline.started`, `pipeline.completed`, `stage.started`, etc.) | `events/events.py` | 014+013 |
| 2.5 | Tests | `tests/unit/test_pipeline_decorator.py`, `tests/unit/test_event_bus.py` 🆕 | 014+013 |

### Phase 3 — Modèles IA + config (semaine 3)

> **Objectif** : migrer tous les modèles `ai_engine` dans `models/ai/`.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 3.1 | Créer `models/ai/types.py` (enums IA : `ProviderType`, `AgentRole`, `NodeType`, `MemoryType`, etc.) | `models/ai/types.py` 🆕 | 013 |
| 3.2 | Copier et adapter `ai_engine/models/*.py` → `models/ai/*.py` (adapter imports) | `models/ai/agent.py`, `provider.py`, `conversation.py`, `message.py`, `tool.py`, `skill.py`, `memory.py`, `knowledge.py`, `graph.py` 🆕 | 013 |
| 3.3 | Ajouter les champs IA optionnels sur `StepRun` (`agent_id`, `tool_id`, `token_usage`) | `models/run.py` | 013 |
| 3.4 | Créer `config/ai.py` (`AISettings`) | `config/ai.py` 🆕 | 013 |
| 3.5 | Fusionner les exceptions IA dans `exceptions.py` | `exceptions.py` | 013 |
| 3.6 | Exporter dans `models/ai/__init__.py` | `models/ai/__init__.py` 🆕 | 013 |
| 3.7 | Tests | `tests/unit/models/ai/` 🆕 | 013 |

### Phase 4 — Ports IA + Adapters IA + Engine IA (semaine 4-5)

> **Objectif** : migrer la logique métier et les adapters `ai_engine`.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 4.1 | Créer `ports/ai/` (BaseLLMClient, BaseTool, BaseSkill, BaseAIStorage) | `ports/ai/*.py` 🆕 | 013 |
| 4.2 | Migrer `ai_engine/services/llm/` → `adapters/ai/llm/` | `adapters/ai/llm/*.py` 🆕 | 013 |
| 4.3 | Migrer `ai_engine/tools/` → `adapters/ai/tools/` | `adapters/ai/tools/*.py` 🆕 | 013 |
| 4.4 | Migrer `ai_engine/skills/` → `adapters/ai/skills/` | `adapters/ai/skills/*.py` 🆕 | 013 |
| 4.5 | Migrer `ai_engine/storage/` → `adapters/ai/storage/` | `adapters/ai/storage/*.py` 🆕 | 013 |
| 4.6 | Migrer `ai_engine/services/agent.py` → `engine/ai/agent_service.py` | `engine/ai/agent_service.py` 🆕 | 013 |
| 4.7 | Créer les ponts : `AIStep`, `AITrigger`, `AgentExecutor`, `JobAsTool` | `adapters/ai/steps/`, `triggers/`, `executors/`, `bridges/` 🆕 | 013 |
| 4.8 | Étendre `BaseStorage` avec méthodes Pipeline + IA (défaut `NotImplementedError`) | `ports/storage.py` | 013+014 |
| 4.9 | Implémenter dans `SQLiteStorage` (tables `pipelines`, `pipeline_runs`, `stage_runs` + tables IA) | `adapters/storage/sqlite.py` | 013+014 |
| 4.10 | Migrer les adapters Django/FastAPI IA | `adapters/ai/django/`, `adapters/ai/fastapi/` 🆕 | 013 |
| 4.11 | Tests | `tests/unit/adapters/ai/`, `tests/integration/` | 013 |

### Phase 5 — PipelineRunner promu + facade enrichie (semaine 5)

> **Objectif** : le PipelineRunner devient un citoyen de première classe dans le moteur.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 5.1 | Promouvoir `pipelines/shared/runner.py` → `engine/pipeline_runner.py` (refactored : accepte `Pipeline`, produit `PipelineRun`) | `engine/pipeline_runner.py` 🆕 | 014 |
| 5.2 | Enrichir `WorkflowEngine` : `run_pipeline()`, `run_pipeline_with_storage()` | `facade.py` | 014 |
| 5.3 | Enrichir `WorkflowEngine` : méthodes IA optionnelles (garde lazy import) | `facade.py` | 013 |
| 5.4 | Réécrire `pipelines/weekly/countries_to_dwh.py` avec `@pipeline`/`@stage` | `pipelines/weekly/countries_to_dwh.py` | 014 |
| 5.5 | Rétrocompatibilité : `pipelines/shared/runner.py` délègue vers `engine/pipeline_runner.py` | `pipelines/shared/runner.py` | 014 |
| 5.6 | Tests intégration | `tests/integration/test_pipeline_execution.py` 🆕 | 014 |

### Phase 6 — Nettoyage + documentation (semaine 6)

> **Objectif** : supprimer `ai_engine/`, documenter, valider.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 6.1 | Archiver `ai_engine/` dans `_archives/ai_engine/` | `_archives/ai_engine/` | 013 |
| 6.2 | Optionnel : shim `ai_engine/__init__.py` avec re-exports + `DeprecationWarning` | `ai_engine/__init__.py` | 013 |
| 6.3 | Mettre à jour `pyproject.toml` (version 0.8.0, extras IA) | `pyproject.toml` | 013 |
| 6.4 | Mettre à jour `[tool.hatch.build.targets.wheel]` si nécessaire | `pyproject.toml` | 013 |
| 6.5 | Validation finale : `grep -rni "from ai_engine"` → zéro occurrence (hors shim) | — | 013 |
| 6.6 | `pytest`, `mypy`, `ruff` — green | — | all |
| 6.7 | Guide de migration `docs/guides/migrating-from-ai-engine.md` | `docs/guides/` 🆕 | 013 |
| 6.8 | Mettre à jour `README.md`, `CHANGELOG.md` | — | all |
| 6.9 | Exemples : `examples/03_ai_step_in_pipeline.py`, `examples/04_agent_orchestrated_job.py` | `examples/` 🆕 | 013+014 |

---

## Règles de cohabitation dataclass / Pydantic

```
                ┌─────────────────────────────────────────────────┐
                │          models/ (dataclass stdlib)              │
                │  enums.py, job.py, step.py, run.py              │
                │  pipeline.py, pipeline_run.py                    │
                │                                                  │
                │  ⚠️ NE DOIT JAMAIS importer depuis models/ai/   │
                └──────────────────────┬──────────────────────────┘
                                       │ peut importer
                                       ▼
                ┌─────────────────────────────────────────────────┐
                │          models/ai/ (Pydantic BaseModel)         │
                │  agent.py, provider.py, message.py, ...          │
                │                                                  │
                │  ✅ PEUT importer RunStatus, StepType, etc.     │
                │     depuis models/enums.py                       │
                └─────────────────────────────────────────────────┘
```

Cette règle garantit que :
- Le **core reste zéro dépendance** (`pip install pyworkflow-engine` n'installe rien).
- Pydantic n'est requis que pour `models/ai/` → uniquement si `[pydantic]` ou `[ai]` est installé.
- Les imports sont unidirectionnels : `ai/ → core`, jamais `core → ai/`.

---

## Matrice des impacts par fichier

| Fichier | Phase | ADR | Nature du changement |
|---|---|---|---|
| `models/enums.py` | 1 | 013+014 | Ajout valeurs (non-breaking) |
| `models/pipeline.py` | 1 | 014 | 🆕 Création |
| `models/pipeline_run.py` | 1 | 014 | 🆕 Création |
| `models/__init__.py` | 1 | 014 | Ajout exports |
| `decorators/pipeline_decorator.py` | 2 | 014 | 🆕 Création |
| `decorators/__init__.py` | 2 | 014 | Ajout exports |
| `events/bus.py` | 2 | 013 | 🆕 Création (depuis ai_engine) |
| `events/events.py` | 2 | 013+014 | 🆕 Création |
| `models/ai/*.py` | 3 | 013 | 🆕 Création (depuis ai_engine) |
| `models/run.py` | 3 | 013 | Ajout champs optionnels (non-breaking) |
| `config/ai.py` | 3 | 013 | 🆕 Création |
| `exceptions.py` | 3 | 013 | Ajout exceptions IA |
| `ports/ai/*.py` | 4 | 013 | 🆕 Création |
| `adapters/ai/**` | 4 | 013 | 🆕 Création (depuis ai_engine) |
| `ports/storage.py` | 4 | 013+014 | Ajout méthodes (non-breaking, défaut NotImpl) |
| `adapters/storage/sqlite.py` | 4 | 013+014 | Ajout tables |
| `engine/ai/*.py` | 4 | 013 | 🆕 Création (depuis ai_engine) |
| `engine/pipeline_runner.py` | 5 | 014 | 🆕 Création (promu depuis pipelines/shared/) |
| `facade.py` | 5 | 013+014 | Ajout méthodes |
| `pipelines/shared/runner.py` | 5 | 014 | Refactor → délègue |
| `pipelines/weekly/countries_to_dwh.py` | 5 | 014 | Réécriture @pipeline/@stage |
| `pyproject.toml` | 6 | 013 | Ajout extras IA |

---

## Critères de validation

### Par phase

| Phase | Critère |
|---|---|
| 1 | `pytest tests/unit/` green. `mypy` green. Aucun test existant ne casse. |
| 2 | `@pipeline`/`@stage` produisent un `Pipeline` correct. EventBus fonctionne. |
| 3 | Tous les modèles IA importables depuis `pyworkflow_engine.models.ai`. `StepRun` accepte les champs IA. |
| 4 | Un agent IA peut exécuter un chat via `engine.ai.agent_service`. Les ponts (`AIStep`, `JobAsTool`) fonctionnent. |
| 5 | `engine.run_pipeline()` produit un `PipelineRun` persistable. `countries_to_dwh.py` fonctionne avec `@pipeline`. |
| 6 | `grep -rni "from ai_engine"` → 0 (hors shim). `pytest` + `mypy` + `ruff` green. |

### Globaux

- [ ] `pip install pyworkflow-engine` (core seul) fonctionne — zéro dépendance.
- [ ] `pip install pyworkflow-engine[ai]` fonctionne — modèles IA + LLM factory.
- [ ] `pip install pyworkflow-engine[all]` fonctionne — tout.
- [ ] Les workflows existants (ETL classiques) ne sont pas impactés.
- [ ] Le `PipelineRunner` existant dans `pipelines/shared/` reste fonctionnel (rétrocompat).

---

## Alternatives rejetées

### Implémenter ADR-013 et ADR-014 séparément

- ✅ Branches indépendantes, reviews isolées.
- ❌ `models/enums.py` modifié deux fois → conflits de merge.
- ❌ `ports/storage.py` étendu deux fois → conflits.
- ❌ `facade.py` enrichi deux fois → conflits.
- ❌ `models/run.py` touché deux fois → conflits.
- ❌ Les scénarios hybrides (Pipeline + IA) ne seraient testés qu'après la fusion des deux branches.

### Implémenter ADR-014 d'abord, puis ADR-013

- ✅ Moins risqué (Pipeline est plus simple qu'IA).
- ❌ Le `PipelineRunner` promu en Phase 5 devrait être re-refactoré en ADR-013 pour supporter les steps IA.
- ❌ Deux cycles de tests sur les mêmes fichiers.
- ❌ 6 semaines au lieu de 6 (phases séquentielles au lieu d'entrelacées).

---

## Conséquences

### Positives

- **Un seul plan**, une seule branche, une seule review pour les deux ADR.
- **Zéro conflit de merge** entre les modifications de `enums.py`, `storage.py`, `facade.py`, `run.py`.
- **Symétrie architecturale complète** : Step → Job → Pipeline × (classique + IA).
- **Scénarios hybrides testés dès le départ** : Pipeline avec stages IA validé en Phase 5.
- **Rétrocompatibilité totale** : le core reste dataclass stdlib, zéro dépendance.
- **6 phases incrémentales** : chaque phase est validable indépendamment.

### Négatives / risques

- **Scope large** : ~30 fichiers créés/modifiés sur 6 semaines.
- **Risque de régression** : mitigé par la validation phase par phase.
- **Review volumineuse** : mitigé en découpant en PRs par phase.

---

## Statut

🔵 Proposition — en attente de validation. Remplace les plans d'implémentation d'ADR-013 et ADR-014 (les deux ADR restent comme documents d'analyse, cette ADR-015 est le plan d'exécution).
