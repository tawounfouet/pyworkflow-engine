# ADR-019 — Création du catalogue `agents/` pour les agents IA concrets

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-019                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | ✅ Implémentée                      |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-013 (AI engine integration), ADR-016 (master plan), ADR-018 (models reorg) |
| **Version cible** | v0.10.0                        |

---

## Contexte

### Le pattern « catalogue à la racine » existant

Le projet a établi une convention claire : les **modèles de domaine** vivent dans `src/pyworkflow_engine/models/` (classes abstraites, schémas Pydantic, DDL), tandis que les **instances concrètes** vivent dans des dossiers catalogue à la racine du projet.

| Catalogue | Modèle source | Convention |
|-----------|--------------|------------|
| `jobs/` | `src/.../models/workflow/job.py` → `Job`, `Step` | 1 dossier par domaine (ingestion, transformation, ml, reporting, ops), 1 fichier = 1 job atomique |
| `pipelines/` | `src/.../models/pipeline/pipeline.py` → `Pipeline`, `PipelineStage` | 1 dossier par fréquence (daily, weekly, monthly, on_demand), 1 fichier = 1 pipeline |

Chaque catalogue suit la même structure :

```
catalogue/
├── __init__.py       # Docstring décrivant le catalogue
├── README.md         # Documentation d'usage, conventions, exemples
├── manifest.yaml     # Registre déclaratif (optionnel, cf. jobs/)
├── {catégorie_1}/    # Sous-dossiers organisationnels
├── {catégorie_2}/
└── shared/           # Utilitaires transversaux
```

### L'absence d'un catalogue `agents/`

L'ADR-013 a intégré `ai_engine` dans `pyworkflow_engine`. L'ADR-018 a réorganisé les modèles et namespaced les tables (`ai_agents`, `ai_providers`, etc.). Le modèle `Agent` est mature :

```python
# src/pyworkflow_engine/models/ai/agent.py
@ModelRegistry.register
class Agent(PersistableModel):
    __table_meta__ = TableMeta(table_name="ai_agents", ...)
    name: str
    slug: str
    role: AgentRole          # ASSISTANT, RESEARCHER, CODER, ANALYST, REVIEWER, ORCHESTRATOR, CUSTOM
    provider_id: str         # FK → ai_providers.id
    model: str | None
    system_prompt: str
    config: AgentConfig      # temperature, max_iterations, tokens, memory, tools, RAG, retries
    tool_ids: list[str]
    skill_ids: list[str]
    knowledge_base_ids: list[str]
    ...
```

**Mais il n'existe aucun endroit pour déclarer les agents concrets.** Les développeurs doivent instancier des `Agent(...)` ad hoc dans leur code applicatif, sans catalogue centralisé, sans conventions de nommage, sans manifest.

L'asymétrie est flagrante :

```
pyworkflow-engine/
├── jobs/           ✅ Catalogue concret de Job
├── pipelines/      ✅ Catalogue concret de Pipeline
├── agents/         ❌ ABSENT — pas de catalogue concret d'Agent
```

---

## Décision

### Créer un catalogue `agents/` à la racine du projet

Le dossier `agents/` suit exactement le même pattern que `jobs/` et `pipelines/` : il contient des **instances concrètes** du modèle `Agent`, organisées par rôle (`AgentRole`).

### Structure retenue

```
agents/
├── __init__.py
├── README.md
├── manifest.yaml
│
├── assistants/               # AgentRole.ASSISTANT — agents conversationnels généralistes
│   ├── __init__.py
│   └── general_assistant.py
│
├── researchers/              # AgentRole.RESEARCHER — agents de recherche documentaire
│   ├── __init__.py
│   └── doc_researcher.py
│
├── coders/                   # AgentRole.CODER — agents de génération / review de code
│   ├── __init__.py
│   └── code_reviewer.py
│
├── analysts/                 # AgentRole.ANALYST — agents d'analyse de données
│   ├── __init__.py
│   └── data_analyst.py
│
├── orchestrators/            # AgentRole.ORCHESTRATOR — agents multi-agents / planificateurs
│   ├── __init__.py
│   └── pipeline_planner.py
│
├── _template/                # Template pour créer un nouvel agent
│   ├── __init__.py
│   └── agent_example.py
│
└── shared/                   # Utilitaires transversaux
    ├── __init__.py
    ├── prompts/              # System prompts réutilisables
    │   └── base_prompts.py
    ├── configs.py            # AgentConfig presets (creative, precise, balanced…)
    └── tool_sets.py          # Groupes de tool_ids courants
```

### Correspondance avec les rôles `AgentRole`

| Dossier | `AgentRole` | Responsabilité |
|---------|-------------|----------------|
| `assistants/` | `ASSISTANT` | Agents conversationnels généralistes, Q&A |
| `researchers/` | `RESEARCHER` | Recherche documentaire, RAG, synthèse |
| `coders/` | `CODER` | Génération de code, refactoring, review |
| `analysts/` | `ANALYST` | Analyse de données, SQL, visualisation |
| `orchestrators/` | `ORCHESTRATOR` | Planification multi-agents, décomposition de tâches |
| (pas de dossier dédié) | `REVIEWER` | Peut vivre dans `coders/` ou `shared/` selon le contexte |
| (pas de dossier dédié) | `CUSTOM` | Libre — créer un dossier spécifique si le volume le justifie |

> **Règle** : un nouveau dossier se crée quand ≥ 3 agents partagent le même rôle. En-dessous, on place le fichier dans le dossier le plus proche sémantiquement.

---

## Conventions

### Convention de nommage

| Élément | Pattern | Exemple |
|---------|---------|---------|
| Fichier agent | `{nom_descriptif}.py` | `general_assistant.py` |
| Variable agent | `{nom_descriptif}` (snake_case) | `general_assistant` |
| Slug agent | `{nom-descriptif}` (kebab-case) | `general-assistant` |
| Dossier catégorie | `{role_pluriel}/` | `assistants/`, `researchers/` |

### Convention d'un fichier agent

Chaque fichier agent suit ce template :

```python
"""
Agent — {Nom} ({Rôle}).

Description courte de la responsabilité de l'agent.
Provider : {provider attendu}
Outils   : {liste des outils utilisés}
"""

from __future__ import annotations

from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.types import AgentRole

{nom_variable} = Agent(
    name="{Nom Humain}",
    slug="{nom-slug}",
    description="{Description détaillée}",
    role=AgentRole.{ROLE},
    provider_id="{provider-id}",          # Résolu au runtime via manifest ou config
    system_prompt="...",
    welcome_message="...",                 # Optionnel
    config=AgentConfig(
        max_iterations=10,
        temperature=0.7,
        enable_memory=True,
        enable_tools=True,
    ),
    tool_ids=[...],                        # IDs des outils autorisés
    skill_ids=[...],                       # IDs des compétences
    knowledge_base_ids=[...],              # IDs des bases de connaissance (RAG)
)
```

### Manifest (`manifest.yaml`)

Le manifest sert de registre déclaratif consultable, sur le même modèle que `jobs/manifest.yaml` :

```yaml
# agents/manifest.yaml — Registre des agents IA de la plateforme
#
# Ce fichier référence tous les agents déclarés dans agents/.
# Il sert de catalogue consultable (rôle, provider, outils) et peut être
# utilisé par un orchestrateur ou un service de découverte d'agents.

agents:
  # ── Assistants ──────────────────────────────────────────────────────

  - name: general-assistant
    module: agents.assistants.general_assistant
    attr: general_assistant
    role: assistant
    provider: default-openai
    tags: [assistant, general, conversational]
    description: "Assistant IA polyvalent pour les tâches courantes."

  # ── Researchers ─────────────────────────────────────────────────────

  - name: doc-researcher
    module: agents.researchers.doc_researcher
    attr: doc_researcher
    role: researcher
    provider: default-openai
    tags: [researcher, rag, documentation]
    description: "Agent de recherche documentaire avec RAG."

  # ── Orchestrators ───────────────────────────────────────────────────

  - name: pipeline-planner
    module: agents.orchestrators.pipeline_planner
    attr: pipeline_planner
    role: orchestrator
    provider: default-openai
    tags: [orchestrator, planner, multi-agent]
    description: "Planificateur multi-agents pour décomposition de tâches."
```

---

## Utilitaires partagés (`shared/`)

### `shared/configs.py` — Presets d'`AgentConfig`

Des configurations pré-définies réutilisables, adaptées à différents cas d'usage :

```python
from pyworkflow_engine.models.ai.agent import AgentConfig

# Créatif : haute température, beaucoup d'itérations
CREATIVE = AgentConfig(temperature=1.2, max_iterations=15, enable_memory=True)

# Précis : basse température, peu d'itérations
PRECISE = AgentConfig(temperature=0.1, max_iterations=5, enable_memory=True)

# Équilibré : défauts raisonnables
BALANCED = AgentConfig(temperature=0.7, max_iterations=10, enable_memory=True)

# RAG-enabled : recherche documentaire activée
RAG_ENABLED = AgentConfig(temperature=0.3, enable_rag=True, enable_memory=True)

# Code : basse température, outils activés
CODE = AgentConfig(temperature=0.0, max_iterations=20, enable_tools=True)
```

### `shared/prompts/` — System prompts réutilisables

Des fragments de prompts système composables :

```python
# shared/prompts/base_prompts.py

CONCISE = "Réponds de manière concise, structurée et factuelle."
FRENCH = "Tu réponds toujours en français."
CITE_SOURCES = "Cite systématiquement tes sources avec des liens."
NO_HALLUCINATION = "Si tu ne connais pas la réponse, dis-le explicitement."

def compose(*fragments: str) -> str:
    """Compose un system prompt à partir de fragments."""
    return "\n".join(fragments)
```

### `shared/tool_sets.py` — Groupes d'outils courants

```python
# shared/tool_sets.py

# Outils de recherche web
WEB_SEARCH_TOOLS = ["web-search", "url-fetch", "html-parser"]

# Outils de base de données
DATABASE_TOOLS = ["sql-query", "schema-inspector"]

# Outils de code
CODE_TOOLS = ["code-executor", "linter", "formatter"]

# Outils de fichier
FILE_TOOLS = ["file-reader", "file-writer", "csv-parser"]
```

---

## Relation avec les composants existants

### Séparation modèle / instance

```
src/pyworkflow_engine/models/ai/agent.py     ← CLASSE (schéma Pydantic, DDL, validation)
                    ↕
agents/assistants/general_assistant.py        ← INSTANCE (configuration concrète)
```

C'est le même pattern que :

```
src/pyworkflow_engine/models/workflow/job.py  ← CLASSE Job
                    ↕
jobs/ingestion/stripe/extract_payments.py     ← INSTANCE concrète de Job
```

### Cycle de vie

```
                     ┌─────────────────────────┐
                     │  agents/manifest.yaml    │ ← Registre déclaratif
                     └────────────┬────────────┘
                                  │ référence
                     ┌────────────▼────────────┐
                     │  agents/{role}/{name}.py │ ← Instance Agent(...)
                     └────────────┬────────────┘
                                  │ import
                     ┌────────────▼────────────┐
                     │  models/ai/agent.py      │ ← Classe Agent (PersistableModel)
                     └────────────┬────────────┘
                                  │ persiste via
                     ┌────────────▼────────────┐
                     │  Repository[Agent]       │ ← Table ai_agents (ADR-017/018)
                     └────────────┬────────────┘
                                  │ exécuté par
                     ┌────────────▼────────────┐
                     │  services/llm/           │ ← Provider LLM (OpenAI, Anthropic…)
                     └─────────────────────────┘
```

---

## Alternatives considérées

### Option A — Agents dans `src/pyworkflow_engine/agents/`

Placer les agents concrets dans le package source.

**Rejeté** : casse le pattern établi (`jobs/` et `pipelines/` sont à la racine, pas dans `src/`). Les instances concrètes ne font pas partie du package distribué — elles sont spécifiques au déploiement.

### Option B — Agents dans `jobs/` comme un type de job spécial

Traiter un agent IA comme un job avec `StepType.AI_CALL`.

**Rejeté** : un agent n'est pas un job. Un job est déterministe, a des étapes ordonnées et un DAG. Un agent est non-déterministe, conversationnel, et peut utiliser des outils. La sémantique est fondamentalement différente. En revanche, un agent peut être **invoqué par** un job (via `StepType.AI_CALL` ou un `ConnectorRef`).

### Option C — Pas de catalogue, agents définis inline

Laisser chaque développeur instancier ses agents dans son propre code.

**Rejeté** : pas de discoverabilité, pas de conventions, duplication des configurations, pas de manifest centralisé. Contraire à l'approche « convention over configuration » du projet.

---

## Plan d'implémentation

### Phase 1 — Scaffolding (immédiat)

| Tâche | Fichiers | Effort |
|-------|----------|--------|
| Créer la structure `agents/` | `__init__.py`, `README.md`, `manifest.yaml` | 15 min |
| Créer `_template/agent_example.py` | Template copier-coller | 10 min |
| Créer `shared/configs.py` | Presets AgentConfig | 10 min |
| Créer `shared/prompts/base_prompts.py` | Fragments de prompts | 10 min |
| Créer `shared/tool_sets.py` | Groupes d'outils | 5 min |

### Phase 2 — Premiers agents (sprint suivant)

| Tâche | Fichiers | Effort |
|-------|----------|--------|
| `assistants/general_assistant.py` | Premier agent concret | 20 min |
| `researchers/doc_researcher.py` | Agent RAG | 30 min |
| `coders/code_reviewer.py` | Agent de code review | 30 min |
| Compléter `manifest.yaml` | Registre à jour | 10 min |

### Phase 3 — Intégration (post-v0.10.0)

| Tâche | Description | Effort |
|-------|-------------|--------|
| Loader de manifest | Charger `manifest.yaml` → instancier les agents automatiquement | 2h |
| CLI discovery | `pyworkflow agents list`, `pyworkflow agents run <slug>` | 3h |
| Tests | Tests unitaires pour chaque agent concret | 2h |

---

## Conséquences

### Positives

- ✅ **Cohérence architecturale** — `jobs/`, `pipelines/`, `agents/` forment une triade symétrique
- ✅ **Discoverabilité** — `manifest.yaml` + convention de nommage permettent la découverte automatique
- ✅ **Réutilisabilité** — `shared/` mutualise configs, prompts et tool sets
- ✅ **Onboarding** — `_template/` permet à un nouveau développeur de créer un agent en < 5 min
- ✅ **Séparation des responsabilités** — le modèle `Agent` reste pur (domaine), les instances concrètes sont applicatives

### Négatives

- ⚠️ **Un dossier de plus à la racine** — mais c'est le pattern établi, pas une exception
- ⚠️ **`provider_id` résolu au runtime** — les fichiers agents référencent un provider par ID/slug, qui doit exister en base. Le manifest pourrait documenter le provider attendu, mais la résolution reste dynamique

### Neutres

- Le dossier `agents/` n'est **pas** inclus dans le package PyPI (`src/pyworkflow_engine/`). C'est un catalogue de déploiement, comme `jobs/` et `pipelines/`
- Les agents de `agents/` peuvent être **persistés** via `Repository[Agent]` dans la table `ai_agents`, mais ce n'est pas obligatoire — ils peuvent aussi être utilisés in-memory

---

## Références

- **ADR-013** — Intégration AI engine (modèle `Agent`, `AgentConfig`)
- **ADR-016** — Master integration plan (structure `models/ai/`)
- **ADR-018** — Réorganisation des modèles, namespacing `ai_agents`
- **`jobs/README.md`** — Convention du catalogue jobs
- **`pipelines/README.md`** — Convention du catalogue pipelines
- **`jobs/manifest.yaml`** — Exemple de manifest déclaratif
- **`jobs/ingestion/_template/`** — Template de référence pour les jobs
