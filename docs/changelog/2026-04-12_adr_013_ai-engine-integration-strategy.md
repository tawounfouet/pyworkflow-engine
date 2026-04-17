# ADR-013 — Intégration du package `ai_engine` dans `pyworkflow_engine`

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-013                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | 🔄 Remplacée par ADR-016            |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-002 (architecture modulaire), ADR-006 (hexagonal ports/adapters), ADR-012 (rename storage) |
| **Version cible** | v0.8.0                         |

---

## Contexte

Le projet contient actuellement **deux packages** colocalisés dans le même dépôt :

```
pyworkflow-engine/
├── src/pyworkflow_engine/   ← Moteur de workflows (publié sur PyPI)
└── ai_engine/               ← Toolkit IA / agents LLM (standalone, non publié)
```

`pyworkflow_engine` orchestre des **jobs déterministes** (ETL, ops, reporting) via une architecture hexagonale (ports/adapters). `ai_engine` orchestre des **agents LLM non-déterministes** (conversations, tools, skills, graphs multi-agents).

L'objectif est de permettre des **workflows hybrides** où jobs classiques et agents IA collaborent dans une même exécution tracée.

---

## Analyse des similitudes

### Correspondance structurelle

| Concept | `pyworkflow_engine` | `ai_engine` | Doublon |
|---|---|---|---|
| Exécution tracée | `JobRun` (dataclass, `models/run.py`) | `Execution` (Pydantic, `models/execution.py`) | ⚠️ Oui |
| Étape d'exécution | `StepRun` (dataclass, `models/run.py`) | `ExecutionStep` (Pydantic, `models/execution.py`) | ⚠️ Oui |
| Statuts d'exécution | `RunStatus` (Enum, `models/enums.py`) | `ExecutionStatus` (StrEnum, `types.py`) | ⚠️ Oui |
| Types d'étapes | `StepType` (Enum, `models/enums.py`) | `StepType` (StrEnum, `types.py`) | ⚠️ Oui — même nom |
| Stockage abstrait | `BaseStorage` (ABC, `ports/storage.py`) | `StorageBackend` (ABC, `storage/base.py`) | ⚠️ Même pattern |
| Stockage mémoire | `MemoryStorage` (`adapters/storage/memory.py`) | `InMemoryStorage` (`storage/memory.py`) | ⚠️ Oui |
| Stockage SQLite | `SQLiteStorage` (`adapters/storage/sqlite.py`) | `SQLiteStorage` (`storage/sqlite.py`) | ⚠️ Oui |
| Logging | `src/.../logging/` | `ai_engine/logging/` | ⚠️ Oui |
| Exceptions | `exceptions.py` | `exceptions.py` | ⚠️ Oui |
| Config | `config/settings.py` (stdlib) | `config.py` (pydantic-settings) | Différent |

### Correspondance des adapters

| Adapter | `pyworkflow_engine` | `ai_engine` |
|---|---|---|
| Django | ❌ Non | ✅ `adapters/django/` (ORM, admin, views, serializers) |
| FastAPI | ✅ `adapters/api/` | ✅ `adapters/fastapi/` (routers, schemas, deps) |
| CLI | ✅ `adapters/cli/` | ✅ `adapters/cli/` |
| Structlog | ✅ `adapters/structlog/` | ✅ `adapters/structlog/` |
| Snowflake | ✅ `adapters/snowflake/` | ✅ `adapters/snowflake/` |
| Celery | ✅ `adapters/celery/` | ❌ Non |
| TUI | ✅ `adapters/tui/` | ❌ Non |
| GUI | ✅ `adapters/gui/` | ❌ Non |
| MCP | ✅ `adapters/mcp/` | ❌ Non |

### Modules exclusifs à `ai_engine`

Ces modules n'ont pas d'équivalent dans `pyworkflow_engine` :

| Module | Responsabilité |
|---|---|
| `services/llm/` | Factory LLM (OpenAI, Anthropic, Ollama, Gemini, Groq) |
| `services/agent.py` | Orchestration agents (lifecycle, context, conversation) |
| `tools/` | BaseTool + implémentations concrètes (calculator, web_search, http_client) |
| `skills/` | BaseSkill + SkillRegistry |
| `events/` | EventBus (sync/async, wildcard, middleware) |
| `embeddings/` | Module d'embeddings (prévu, vide) |
| `models/agent.py` | Agent, AgentConfig |
| `models/provider.py` | LLMProviderConfig, ProviderSettings, ProviderCapabilities |
| `models/conversation.py` | Conversation |
| `models/message.py` | Message, ToolCall, ToolResult, TokenUsage |
| `models/memory.py` | AgentMemory |
| `models/knowledge.py` | KnowledgeSource, Document, Chunk |
| `models/graph.py` | Graph, GraphNode, GraphEdge |
| `models/skill.py` | Skill, AgentSkillAssignment |
| `models/tool.py` | ToolDefinition |
| `types.py` | Enums IA (ProviderType, AgentRole, NodeType, MemoryType, etc.) |

---

## Options évaluées

### Option A — `pip install ai-engine` comme dépendance externe

```
pyworkflow-engine/
├── src/pyworkflow_engine/
│   └── pyproject.toml → dependencies = ["ai-engine>=0.1.0"]
└── ai_engine/  → publié séparément
```

**Avantages :**
- Séparation stricte des responsabilités.
- Versioning indépendant.
- `ai_engine` réutilisable dans d'autres projets sans `pyworkflow_engine`.

**Inconvénients :**
- Deux systèmes de traçabilité parallèles (`JobRun` vs `Execution`) qui ne se parlent pas.
- Doublons de storage, logging, exceptions maintenus séparément.
- L'utilisateur doit naviguer entre deux APIs pour un workflow hybride.
- Synchronisation des releases entre deux packages.
- Les adapters communs (Django, FastAPI, structlog, snowflake, CLI) sont dupliqués.

### Option B — Copier `ai_engine/` dans `contrib/`

```
pyworkflow-engine/
└── src/pyworkflow_engine/
    └── contrib/
        └── ai_engine/  ← copie brute
```

**Avantages :**
- Package unique.
- Import cohérent : `from pyworkflow_engine.contrib.ai_engine import Agent`.

**Inconvénients :**
- Duplication du code sans rationalisation des doublons.
- Pas de fusion des modèles d'exécution → deux `Execution` dans le même package.
- Les adapters communs restent dupliqués dans `adapters/` et `contrib/ai_engine/adapters/`.
- Maintenance complexe : modifications en double.

### Option C — Fusion de `ai_engine` dans `pyworkflow_engine` comme domaine intégré

```
pyworkflow-engine/
└── src/pyworkflow_engine/
    ├── models/
    │   ├── (existants)
    │   └── ai/           ← modèles IA
    ├── ports/
    │   └── ai/           ← contrats IA
    ├── adapters/
    │   └── ai/           ← implémentations IA
    ├── engine/
    │   └── ai/           ← services IA
    └── events/           ← EventBus unifié
```

**Avantages :**
- **Un seul modèle d'exécution** : `Execution` unifié (job classique + agent IA).
- **Un seul storage** : `BaseStorage` étendu pour couvrir les entités IA.
- **Un seul EventBus** : événements workflow + IA sur le même bus.
- **Un seul logging** : configuration partagée.
- **Adapters non dupliqués** : Django, FastAPI, CLI, structlog → une seule implémentation.
- **API cohérente** : l'utilisateur a un seul point d'entrée (`WorkflowEngine`).
- **Dépendances IA optionnelles** : via `[project.optional-dependencies]`.

**Inconvénients :**
- Travail de migration significatif.
- `ai_engine` perd son identité comme package standalone.
- Package plus gros (même si les extras restent optionnels).

---

## Décision

**→ Option C : Fusion de `ai_engine` dans `pyworkflow_engine` comme domaine intégré.**

Le taux de doublons (storage, execution, logging, exceptions, 5 adapters identiques) est trop élevé pour justifier deux packages séparés. La convergence naturelle des deux modèles d'exécution confirme qu'il s'agit d'un seul produit : **un moteur d'orchestration qui supporte à la fois des jobs déterministes et des agents IA non-déterministes**.

---

## Architecture cible

### Structure des dossiers

```
src/pyworkflow_engine/
│
├── models/                              # Modèles de domaine
│   ├── __init__.py                      # Re-exports publics
│   ├── enums.py                         # ✅ Existant — enrichi avec enums IA
│   ├── job.py                           # ✅ Existant
│   ├── step.py                          # ✅ Existant
│   ├── run.py                           # ✅ Existant → étendu (voir « Exécution unifiée »)
│   │
│   └── ai/                              # 🆕 Modèles IA (depuis ai_engine/models/)
│       ├── __init__.py
│       ├── agent.py                     # Agent, AgentConfig
│       ├── provider.py                  # LLMProviderConfig, ProviderSettings, ...
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
│   ├── storage.py                       # ✅ Existant → étendu (entités IA)
│   ├── trigger.py                       # ✅ Existant
│   │
│   └── ai/                              # 🆕 Ports IA
│       ├── __init__.py
│       ├── llm.py                       # BaseLLMClient (contrat LLM)
│       ├── tool.py                      # BaseTool (contrat tool IA)
│       ├── skill.py                     # BaseSkill (contrat skill)
│       └── storage.py                   # BaseAIStorage (contrat storage IA)
│
├── adapters/                            # Implémentations concrètes
│   ├── api/                             # ✅ Existant (FastAPI workflows)
│   ├── celery/                          # ✅ Existant
│   ├── cli/                             # ✅ Existant → enrichi (commandes IA)
│   ├── executors/                       # ✅ Existant
│   ├── gui/                             # ✅ Existant
│   ├── mcp/                             # ✅ Existant
│   ├── snowflake/                       # ✅ Existant → fusionné (un seul adapter)
│   ├── sqlalchemy/                      # ✅ Existant
│   ├── storage/                         # ✅ Existant (memory, sqlite, json, sqlalchemy)
│   ├── structlog/                       # ✅ Existant → fusionné (un seul adapter)
│   ├── triggers/                        # ✅ Existant (manual, schedule)
│   ├── tui/                             # ✅ Existant
│   │
│   └── ai/                              # 🆕 Adapters IA
│       ├── __init__.py
│       ├── llm/                         # Factory LLM
│       │   ├── __init__.py
│       │   ├── base.py                  # BaseLLMClient (depuis ai_engine/services/llm/base.py)
│       │   ├── factory.py               # LLMFactory (depuis ai_engine/services/llm/factory.py)
│       │   ├── openai.py
│       │   ├── anthropic.py
│       │   ├── ollama.py
│       │   ├── gemini.py
│       │   └── groq.py
│       ├── tools/                       # Tools concrets
│       │   ├── __init__.py
│       │   ├── base.py                  # BaseTool (depuis ai_engine/tools/base.py)
│       │   ├── registry.py              # ToolRegistry (depuis ai_engine/tools/registry.py)
│       │   ├── executor.py              # ToolExecutor (depuis ai_engine/tools/executor.py)
│       │   ├── calculator.py
│       │   ├── web_search.py
│       │   └── http_client.py
│       ├── skills/                      # Skills
│       │   ├── __init__.py
│       │   ├── base.py                  # BaseSkill (depuis ai_engine/skills/base.py)
│       │   └── registry.py              # SkillRegistry (depuis ai_engine/skills/registry.py)
│       ├── storage/                     # Storage IA
│       │   ├── __init__.py
│       │   ├── memory.py               # InMemoryStorage (depuis ai_engine/storage/memory.py)
│       │   └── sqlite.py               # SQLiteStorage (depuis ai_engine/storage/sqlite.py)
│       ├── triggers/                    # 🆕 Triggers IA
│       │   ├── __init__.py
│       │   └── ai_trigger.py           # AITrigger — agent IA comme trigger
│       ├── steps/                       # 🆕 Steps IA
│       │   ├── __init__.py
│       │   └── ai_step.py              # AIStep — agent IA comme step
│       ├── executors/                   # 🆕 Executors IA
│       │   ├── __init__.py
│       │   └── agent_executor.py        # AgentExecutor — agent orchestre un job
│       ├── bridges/                     # 🆕 Ponts entre les deux mondes
│       │   ├── __init__.py
│       │   └── job_as_tool.py           # JobAsTool — expose un Job comme Tool IA
│       ├── django/                      # Adapter Django IA (depuis ai_engine/adapters/django/)
│       │   ├── __init__.py
│       │   ├── orm_models.py
│       │   ├── admin.py
│       │   ├── serializers.py
│       │   └── views.py
│       └── fastapi/                     # Adapter FastAPI IA (depuis ai_engine/adapters/fastapi/)
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
│   │
│   └── ai/                              # 🆕 Services IA (depuis ai_engine/services/)
│       ├── __init__.py
│       ├── agent_service.py             # AgentService (depuis ai_engine/services/agent.py)
│       ├── conversation_service.py      # Gestion conversations
│       └── skill_registry.py            # SkillRegistry (orchestration level)
│
├── events/                              # 🆕 EventBus unifié (depuis ai_engine/events/)
│   ├── __init__.py
│   ├── bus.py                           # EventBus (thread-safe, sync/async)
│   └── events.py                        # Tous les événements (workflow + IA)
│
├── config/                              # ✅ Existant
│   ├── __init__.py
│   ├── base.py
│   ├── engine.py
│   ├── executor.py
│   ├── logging.py
│   ├── settings.py
│   ├── storage.py
│   └── ai.py                           # 🆕 AISettings (depuis ai_engine/config.py)
│
├── decorators/                          # ✅ Existant
├── logging/                             # ✅ Existant (fusionner ai_engine/logging/)
├── exceptions.py                        # ✅ Existant → enrichi (exceptions IA)
├── facade.py                            # ✅ Existant → enrichi (API IA)
└── py.typed
```

### Exécution unifiée — fusion `JobRun` + `Execution`

Les modèles `JobRun` (pyworkflow_engine) et `Execution` (ai_engine) fusionnent en un seul système de traçabilité. Le `JobRun` existant est **étendu** (pas remplacé) pour supporter les champs IA optionnels :

| Champ | Source | Obligation |
|---|---|---|
| `id`, `status`, `started_at`, `completed_at` | Les deux | Toujours |
| `job_id`, `job_name` | `JobRun` | Si `source_type = "job"` |
| `agent_id`, `conversation_id`, `graph_id` | `Execution` | Si `source_type = "agent"` |
| `token_usage`, `total_cost_usd` | `Execution` | Optionnel (nul pour jobs classiques) |
| `trigger_type`, `trigger_name` | Nouveau | Toujours |
| `source_type` | Nouveau | Toujours (`"job"`, `"agent"`, `"workflow"`) |

De même, `StepRun` est étendu avec des champs IA optionnels (`agent_id`, `tool_id`, `token_usage`).

**Principe : les champs IA sont `None` par défaut — les workflows classiques ne sont pas impactés.**

### Enums unifiés — fusion `models/enums.py` + `ai_engine/types.py`

Le fichier `enums.py` existant est enrichi des enums IA. Les enums doublons sont fusionnés :

| Enum | `pyworkflow_engine` | `ai_engine` | Résultat |
|---|---|---|---|
| `RunStatus` | `PENDING, RUNNING, SUCCESS, FAILED, ...` | `ExecutionStatus` : `PENDING, RUNNING, SUCCESS, FAILED, CANCELLED` | **Fusionné** : `RunStatus` + `CANCELLED` |
| `StepType` | `FUNCTION, SUBPROCESS, HTTP_REQUEST, SQL_QUERY, HUMAN_TASK, ...` | `LLM_CALL, TOOL_CALL, TOOL_RESULT, DECISION, ERROR` | **Fusionné** : toutes les valeurs dans un seul enum |
| `TriggerType` | `MANUAL, SCHEDULE, SIGNAL, WEBHOOK, FILE_WATCHER` | ❌ N'existe pas | **Étendu** : + `AI` |

Les enums exclusifs à `ai_engine` (`ProviderType`, `AgentRole`, `NodeType`, `MemoryType`, etc.) sont ajoutés dans un nouveau fichier `models/ai/types.py` pour éviter de surcharger `enums.py`.

### Storage unifié

Le port `BaseStorage` existant est **étendu** avec des méthodes optionnelles pour les entités IA :

```python
class BaseStorage(ABC):
    # ── Existant (workflow) ──
    def save_job(self, job: Job) -> None: ...
    def get_job(self, job_id: str) -> Job: ...
    def save_run(self, run: JobRun) -> None: ...
    def get_run(self, run_id: str) -> JobRun: ...
    # ...

    # ── Nouveau (IA — optionnel, NotImplementedError par défaut) ──
    def save_agent(self, agent: Agent) -> Agent: ...
    def get_agent(self, agent_id: str) -> Agent | None: ...
    def save_provider(self, provider: LLMProviderConfig) -> LLMProviderConfig: ...
    # ...
```

Les méthodes IA ont une implémentation par défaut levant `NotImplementedError` → les backends existants (memory, SQLite, JSON) continuent de fonctionner sans modification.

### EventBus unifié

L'EventBus de `ai_engine` (thread-safe, sync/async, wildcard, middleware) est promu au niveau du package principal dans `events/`. Les événements workflow existants (si présents) et IA cohabitent sur le même bus.

---

## Scénarios d'utilisation

### Scénario A — Agent IA comme étape dans un job classique

```python
from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.adapters.ai.steps import AIStep

engine = WorkflowEngine()
job = engine.create_job(
    name="etl_with_ai",
    steps=[
        extract_step,
        validate_step,
        AIStep(agent=analyst, prompt="Classify anomalies: {data}"),  # 🧠
        load_step,
    ],
)
run = engine.run(job)
```

### Scénario B — Agent IA orchestre un job

```python
from pyworkflow_engine.adapters.ai.executors import AgentExecutor

executor = AgentExecutor(agent=supervisor, max_iterations=10)
context = executor.run(repair_job, context={"db": "prod"})
# L'agent décide dynamiquement quelles étapes exécuter
```

### Scénario C — Job exposé comme tool pour un agent IA

```python
from pyworkflow_engine.adapters.ai.bridges import JobAsTool

etl_tool = JobAsTool(engine, etl_job)
agent_service.register_tool(analyst, etl_tool.to_tool_definition())
# L'agent peut déclencher le job ETL complet via function calling
```

---

## Dépendances optionnelles (`pyproject.toml`)

```toml
[project]
dependencies = []  # Core reste zéro dépendance

[project.optional-dependencies]
# ── Existants (inchangés) ──
# django, fastapi, celery, sqlalchemy, cli, tui, gui, ...

# ── Nouveaux (IA) ──
pydantic = ["pydantic>=2.0", "pydantic-settings>=2.0"]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.30"]
ollama = ["ollama>=0.2"]
gemini = ["google-generativeai>=0.5"]
groq = ["groq>=0.5"]
llm = ["pyworkflow-engine[pydantic,openai,anthropic,ollama,gemini,groq]"]
ai-tools = ["duckduckgo-search>=5.0", "httpx>=0.27"]
ai = ["pyworkflow-engine[llm,ai-tools]"]
ai-django = ["pyworkflow-engine[ai,django]"]
ai-fastapi = ["pyworkflow-engine[ai,fastapi]"]

# ── Tout ──
all = ["pyworkflow-engine[ai,django,fastapi,celery,sqlalchemy,cli,tui,gui,...]"]
```

```bash
pip install pyworkflow-engine           # Core (jobs, steps, triggers)
pip install pyworkflow-engine[openai]   # + OpenAI uniquement
pip install pyworkflow-engine[ai]       # + Tous les LLM + tools IA
pip install pyworkflow-engine[all]      # Tout
```

---

## Plan de migration

### Phase 1 — Préparation (branche `feature/ai-engine-integration`)

1. Créer l'arborescence `models/ai/`, `ports/ai/`, `adapters/ai/`, `engine/ai/`, `events/`, `config/ai.py`.
2. Copier les fichiers de `ai_engine/` vers leur destination dans `src/pyworkflow_engine/`.
3. Adapter tous les imports internes (`from ai_engine.` → `from pyworkflow_engine.`).

### Phase 2 — Unification des doublons

4. Fusionner `RunStatus` + `ExecutionStatus` → `RunStatus` étendu.
5. Fusionner `StepType` (workflow) + `StepType` (IA) → `StepType` unifié.
6. Étendre `JobRun` avec les champs IA optionnels.
7. Étendre `StepRun` avec les champs IA optionnels.
8. Étendre `BaseStorage` avec les méthodes IA (défaut `NotImplementedError`).
9. Fusionner les exceptions (`exceptions.py`).
10. Fusionner les modules de logging.

### Phase 3 — Ponts et adapters

11. Implémenter `AIStep`, `AITrigger`, `AgentExecutor`, `JobAsTool`.
12. Fusionner les adapters communs (Django, FastAPI, CLI, structlog, snowflake).
13. Promouvoir l'EventBus dans `events/`.

### Phase 4 — Nettoyage

14. Supprimer `ai_engine/` du dépôt (ou archiver dans `_archives/`).
15. Mettre à jour `pyproject.toml` (optional-dependencies IA).
16. Mettre à jour `[tool.hatch.build.targets.wheel]` si nécessaire.
17. Valider : `pytest`, `mypy`, `ruff`, `grep -rni "from ai_engine"` → zéro occurrence.

### Phase 5 — Documentation et rétrocompatibilité

18. Ajouter un guide de migration `docs/guides/migrating-from-ai-engine.md`.
19. Optionnel : shim `ai_engine/__init__.py` temporaire avec des re-exports et `DeprecationWarning`.
20. Mettre à jour `README.md`, `CHANGELOG.md`, exemples.

---

## Alternatives rejetées

### Garder `ai_engine` comme package séparé (Option A)

- ✅ Séparation stricte, versioning indépendant.
- ❌ 6 doublons structurels (storage, execution, logging, exceptions, 5 adapters).
- ❌ Deux systèmes de traçabilité parallèles pour un même workflow hybride.
- ❌ L'utilisateur doit jongler entre deux APIs.

### Copier dans `contrib/` sans fusion (Option B)

- ✅ Package unique, import cohérent.
- ❌ Doublons non rationalisés — pire que Option A car dans le même package.
- ❌ Deux `Execution`, deux `BaseStorage`, deux `logging/` dans un même projet.

---

## Conséquences

### Positives

- **Un seul modèle d'exécution** : `JobRun` trace les workflows classiques ET les exécutions IA.
- **Un seul storage** : pas de duplication des implémentations memory/SQLite.
- **API cohérente** : `WorkflowEngine` expose workflows et agents via la même façade.
- **Core léger** : les dépendances IA restent optionnelles (`[ai]`, `[openai]`, etc.).
- **Extensibilité** : les adapters IA suivent le même pattern ports/adapters que le reste.
- **EventBus** : événements workflow et IA sur le même bus → observabilité unifiée.

### Négatives / risques

- **Migration lourde** : renommage massif des imports, tests à adapter.
- **Package plus gros** : même si les extras sont optionnels, le code source est plus conséquent.
- **`ai_engine` perd son autonomie** : ne peut plus être utilisé seul (mitigation : shim de rétrocompatibilité).
- **Risque de régression** : à mitiger par une couverture de tests exhaustive avant migration.

---

## Statut

🔵 Proposition — en attente de validation.
