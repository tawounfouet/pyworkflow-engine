# ADR-020 — Stratégie framework IA : architecture maison vs LangChain

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-020                             |
| **Date**    | 12 avril 2026                       |
| **Mise à jour** | 12 avril 2026 (révision post-audit `AgentService` + ADR-023) |
| **Statut**  | ✅ Décision prise — plan révisé     |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-013 (AI engine integration), ADR-016 (master plan), ADR-018 (models reorg), ADR-019 (agents catalog), ADR-023 (knowledge/RAG architecture) |
| **Version cible** | v0.11.0                        |

---

## Contexte

### La question stratégique

L'intégration IA de `pyworkflow_engine` a atteint une maturité opérationnelle significative (ADR-013 → ADR-019).  La question se pose naturellement : faut-il remplacer l'architecture maison par **LangChain** (ou un framework équivalent) pour gérer les agents et leurs interactions ?

Cette ADR documente l'analyse comparative complète, les recommandations, et le plan d'action retenu.

### L'existant : un système déjà fonctionnel

L'audit du codebase révèle un système d'agents structuré en **7 couches** :

```
┌─────────────────────────────────────────────────────────────────┐
│  agents/                          Catalogue concret (ADR-019)   │
│  ├── manifest.yaml                5 agents déclarés             │
│  ├── assistants/researchers/…     Instances Agent(...)           │
│  └── shared/runner.py             AgentRunner (one-shot + REPL) │
├─────────────────────────────────────────────────────────────────┤
│  engine/ai/                       Service domaine (ADR-016)     │
│  └── agent_service.py             AgentService (CRUD + chat     │
│                                   via BaseAIStorage)            │
├─────────────────────────────────────────────────────────────────┤
│  ports/ai/                        Contrats abstraits (hex.)     │
│  ├── llm.py                       BaseLLMClient (ABC)           │
│  ├── tool.py                      BaseTool (ABC)                │
│  ├── skill.py                     BaseSkill (ABC)               │
│  └── storage.py                   BaseAIStorage (ABC, 30+ meth.)│
├─────────────────────────────────────────────────────────────────┤
│  adapters/ai/                     Implémentations concrètes     │
│  ├── llm/                         OpenAI, Anthropic, Groq,      │
│  │                                Ollama, Gemini (5 providers)  │
│  ├── tools/                       ToolRegistry + ToolExecutor   │
│  │                                + boucle tool-calling         │
│  ├── skills/                      SkillRegistry                 │
│  ├── knowledge/                   RAG pipeline (ADR-023) ✅     │
│  │   ├── chroma_store.py          ChromaVectorStore             │
│  │   ├── numpy_store.py           NumpyVectorStore (tests)      │
│  │   ├── openai_embedder.py       OpenAIEmbedder                │
│  │   ├── recursive_chunker.py     SmartChunker                  │
│  │   └── document_parser.py       DocumentParser                │
│  └── storage/memory.py            InMemoryAIStorage             │
├─────────────────────────────────────────────────────────────────┤
│  models/ai/                       Modèles Pydantic (15 classes) │
│  ├── agent.py                     Agent + AgentConfig           │
│  │                                (enable_memory=True ✅)       │
│  ├── message.py                   Message, ToolCall, ToolResult │
│  ├── conversation.py              Conversation                  │
│  ├── memory.py                    AgentMemory (3 MemoryTypes)   │
│  ├── provider.py                  LLMProviderConfig             │
│  ├── execution.py                 Execution, ExecutionStep      │
│  └── ...                          Graph, Skill, Tool, Knowledge │
├─────────────────────────────────────────────────────────────────┤
│  agents/shared/persistence.py     Persistence v4 (runtime)      │
│  ├── ai_agent_runs                147 runs enregistrés          │
│  └── ai_agent_messages            361 messages persistés        │
├─────────────────────────────────────────────────────────────────┤
│  adapters/steps/ai_bridges.py     Bridges workflow ↔ IA         │
│  ├── AIStep                       Agent comme step de workflow   │
│  ├── AgentExecutor                BaseExecutor wrappant AgentSvc │
│  └── JobAsTool                    Job workflow comme BaseTool    │
├─────────────────────────────────────────────────────────────────┤
│  adapters/cli/commands/           CLI agent (typer + rich)       │
│  └── agent.py                     run, list, sync, chat         │
└─────────────────────────────────────────────────────────────────┘
```

### Les gaps identifiés

L'analyse a révélé **deux services d'orchestration concurrents**, **deux systèmes de persistence parallèles**, et des **lacunes fonctionnelles résiduelles**.

#### Deux services d'orchestration concurrents : `AgentRunner` vs `AgentService`

> **⚠️ Correction post-audit** : l'analyse initiale ne mentionnait pas `engine/ai/agent_service.py`, découvert lors de l'audit approfondi du codebase. Ce module change significativement le diagnostic sur les conversations et la persistence.

Le codebase contient **deux orchestrateurs** qui font des choses similaires mais avec des chemins de persistence différents :

| | `AgentRunner` (agents/shared/) | `AgentService` (engine/ai/) |
|---|---|---|
| **Rôle** | Exécution CLI directe (one-shot, REPL) | Service domaine hexagonal (CRUD + chat) |
| **Persistence** | `AgentSessionPersistence` → tables v4 SQLite directement | `BaseAIStorage` → `InMemoryAIStorage` (volatile) |
| **Utilisé par** | CLI (`agent run`, `agent chat`), exemples, tests (**43 usages**) | Facade, ai_bridges (**8 usages**) |
| **Provider resolution** | Auto-résolution env vars (`OPENAI_API_KEY`) | Lookup via `storage.get_provider()` |
| **Historique conversation** | `list[Message]` en mémoire Python (perdu au restart) | `storage.get_messages()` (persistable si backend durable) |
| **Tool calling** | Directement via `BaseLLMClient` | Via `ToolExecutor` + `ToolRegistry` |
| **Context building** | System prompt + historique en mémoire | `_build_conversation_context()` : system prompt + historique DB |
| **Mémoire inter-sessions** | ❌ Non | ❌ Non (mais infrastructure `save_memory`/`list_memories` prête) |

**`AgentService` est un writer fonctionnel pour les tables Rich API** — il appelle `save_conversation()`, `save_message()`, `get_messages()`, `count_messages()`. Mais il est **sous-utilisé** car `AgentRunner` est le chemin dominant en production (CLI).

#### Deux systèmes de persistence non reliés

| Système | Tables | Écrit par | État |
|---------|--------|-----------|------|
| **v4 runtime** (léger, opérationnel) | `ai_agent_runs` (147 rows), `ai_agent_messages` (361 rows) | `AgentSessionPersistence` via `AgentRunner` | ✅ Actif, chemin dominant |
| **Rich API** (modèles Pydantic, ADR-013) | `ai_conversations`, `ai_messages`, `ai_memories` | `AgentService` via `BaseAIStorage` | ⚠️ Writer existe, mais branché sur `InMemoryAIStorage` (volatile → 0 rows persistées en DB) |

> **Correction** : l'analyse initiale indiquait « aucun writer » pour les tables Rich API. C'est **inexact** : `AgentService.chat()` écrit bien dans `ai_conversations` et `ai_messages` via `BaseAIStorage`. Le problème est que la `facade.py` injecte `InMemoryAIStorage` (volatile) et non un backend SQLite durable :
>
> ```python
> # facade.py — ligne ~747
> ai_storage = getattr(self, "_ai_storage", None) or InMemoryAIStorage()
> self._cached_ai_service = AgentService(storage=ai_storage)
> ```
>
> Les données sont donc écrites mais **perdues à chaque redémarrage**. L'implémentation d'un `SQLiteAIStorage` rendrait `AgentService` pleinement opérationnel sans modifications de son code.

#### Lacunes fonctionnelles résiduelles (révisées post-ADR-023)

| Lacune | Impact | État post-analyse | Effort restant |
|--------|--------|-------------------|----------------|
| **RAG pipeline** | Pas de recherche documentaire augmentée | ✅ **Résolu par ADR-023** — ports (`BaseVectorStore`, `BaseChunker`, `BaseEmbedder`, `BaseDocumentParser`) + adapters (`ChromaVectorStore`, `NumpyVectorStore`, `OpenAIEmbedder`, `SmartChunker`, `DocumentParser`) implémentés dans `adapters/ai/knowledge/` | 0 |
| **Mémoire conversationnelle** — pas d'extraction/injection de faits persistants entre sessions | Les agents repartent de zéro à chaque conversation | ⚠️ **Infrastructure prête, câblage manquant** — `AgentMemory` (modèle Pydantic), `MemoryType` (SHORT_TERM, LONG_TERM, EPISODIC), `BaseAIStorage.save_memory()`/`list_memories()`/`delete_expired_memories()` existent. `AgentConfig.enable_memory=True` par défaut. Manque : extracteur + injection dans contexte | **~135 lignes** |
| **Multi-agent orchestration** | Chaque agent travaille en silo | ❌ Non implémenté | Élevée (~800 lignes ou lib externe) |
| **Persistence unifiée** | Deux chemins parallèles, données Rich API volatiles | ⚠️ `AgentService` est le pont naturel, manque `SQLiteAIStorage` | **~4h** (SQLiteAIStorage) |

---

## Analyse comparative : Architecture maison vs LangChain

### Matrice de comparaison détaillée

| Critère | Architecture maison (actuelle) | LangChain | Verdict |
|---------|-------------------------------|-----------|---------|
| **Multi-provider LLM** | ✅ 5 adapters (OpenAI, Anthropic, Groq, Ollama, Gemini) | ✅ 50+ providers | Maison couvre 95% des cas réels |
| **Tool calling loop** | ✅ `ToolExecutor.run_tool_loop()` avec max_iterations | ✅ `AgentExecutor` | **Équivalent** |
| **Tool registry** | ✅ `ToolRegistry` + résolution par path | ✅ `@tool` decorator | **Équivalent** |
| **Streaming** | ✅ `stream()` / `astream()` dans `BaseLLMClient` | ✅ Natif | Équivalent |
| **Mémoire conversationnelle** | ⚠️ Infrastructure prête (`AgentMemory`, `BaseAIStorage.save_memory()`/`list_memories()`), câblage manquant (~135 loc) | ✅ 6+ types (Buffer, Summary, Vector, Entity…) | **Avantage LangChain** (mais gap réduit) |
| **RAG** | ✅ ADR-023 implémenté : `BaseVectorStore`, `BaseChunker`, `BaseEmbedder`, `ChromaVectorStore`, `OpenAIEmbedder`, `SmartChunker` dans `adapters/ai/knowledge/` | ✅ Loaders + splitters + vectorstores intégrés | **Équivalent** |
| **Chaînes composables** | ❌ Pas d'opérateur pipe | ✅ LCEL (`prompt | llm | parser`) | **Avantage LangChain** |
| **Multi-agent** | ❌ Pas d'orchestration inter-agents | ✅ LangGraph (state machines) | **Avantage LangChain** |
| **Structured output** | ❌ Pas de parsing structuré | ✅ `with_structured_output()` | Avantage LangChain (mais `instructor` suffit) |
| **Observabilité** | ✅ Logging structuré + DB persistence + métriques tokens | ✅ LangSmith / callbacks | **Maison plus intégré au workflow engine** |
| **Persistance sessions** | ✅ `ai_agent_runs` + `ai_agent_messages` avec métriques LLM complètes | ⚠️ Callbacks / `RunnableWithMessageHistory` | **Avantage maison** |
| **Architecture hexagonale** | ✅ Ports/Adapters, contrats ABC, injection | ❌ Monolithique, couplage fort | **Avantage maison** |
| **Poids dépendances** | ✅ Minimal (pydantic, httpx, openai, anthropic) | ❌ ~200+ dépendances transitives | **Avantage maison** |
| **Stabilité API** | ✅ Contrôle total, pas de breaking changes externes | ❌ Breaking changes fréquents (v0.1 → v0.2 → v0.3) | **Avantage maison** |
| **Débuggabilité** | ✅ Code lisible de bout en bout | ❌ Abstractions profondes, stack traces opaques | **Avantage maison** |
| **Cohérence projet** | ✅ Même patterns que `jobs/`, `pipelines/`, `triggers/` | ❌ Paradigme alien dans le codebase | **Avantage maison** |

### Score synthétique (révisé post-ADR-023)

| Dimension | Maison | LangChain |
|-----------|--------|-----------|
| Fonctionnalités IA avancées | **4/5** ↑ (RAG fait, mémoire prête) | 5/5 |
| Architecture & maintenabilité | 5/5 | 2/5 |
| Cohérence du projet | 5/5 | 1/5 |
| Poids opérationnel (deps, upgrades, debug) | 5/5 | 2/5 |
| Vitesse de prototypage features manquantes | **4/5** ↑ (infrastructure existante) | 5/5 |
| **Total** | **23/25** ↑ | **15/25** |

> **Note** : le score maison progresse de 21/25 à 23/25 grâce à l'implémentation RAG (ADR-023) et la découverte de l'infrastructure mémoire existante.

---

## Décision

### Conserver l'architecture maison et combler les gaps avec des bibliothèques ciblées

**LangChain est rejeté** pour les raisons suivantes :

1. **Incompatibilité architecturale** — L'architecture hexagonale du projet (`ports/` ← ABC purs, `adapters/` ← implémentations) est fondamentalement incompatible avec la philosophie monolithique de LangChain. Introduire LangChain reviendrait à créer un « super-adapter » qui absorbe et court-circuite toute la couche `ports/ai/`.

2. **Le coût caché est disproportionné** — Les breaking changes de LangChain (3 refontes majeures en 2 ans : Chains → LCEL → LangGraph) imposent un coût de maintenance récurrent qui annule le gain de productivité initial.

3. **Les gaps sont ciblés et comblables** — Les lacunes résiduelles (mémoire ~135 loc de câblage, persistence ~4h pour `SQLiteAIStorage`, multi-agent différé) sont incrémentalement implémentables dans l'architecture existante. Le RAG est déjà résolu (ADR-023). Le volume total de code nouveau est **drastiquement réduit** par rapport à l'estimation initiale de ~1600 lignes.

4. **La cohérence est un actif** — Le pattern `models/ → ports/ → adapters/ → catalogues/` est le fil conducteur du projet (cf. ADR-002, 006, 019). Le briser pour les agents créerait une asymétrie architecturale et compliquerait l'onboarding.

### Stratégie retenue : « cherry-pick de libs atomiques »

Au lieu d'un framework monolithique, intégrer des **bibliothèques spécialisées** qui s'insèrent proprement dans les ports existants :

```
┌──────────────────────────────────────────────────────────────────┐
│                        BESOIN                                    │
├──────────────┬───────────────────┬───────────────────────────────┤
│  Mémoire     │  RAG / Embeddings │  Structured Output            │
│              │                   │                               │
│  Câblage     │  ✅ FAIT          │  instructor                   │
│  ~135 loc    │  (ADR-023)        │  (wrapper sur BaseLLMClient)  │
│  sur infra   │  ChromaVectorStore│  (~100 loc)                   │
│  existante   │  OpenAIEmbedder   │                               │
│              │  SmartChunker     │                               │
├──────────────┴───────────────────┴───────────────────────────────┤
│              Architecture existante (inchangée)                  │
│  ports/ai/   →  adapters/ai/   →  agents/ + engine/ai/          │
│  BaseLLMClient  OpenAIClient      AgentRunner (CLI)              │
│  BaseAIStorage  InMemoryAI...     AgentService (domaine)         │
│  BaseTool       ToolRegistry      AgentSessionPersistence (v4)   │
│  BaseVectorStore ChromaVector...  ai_bridges (workflow ↔ IA)     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Plan d'implémentation (révisé)

> **Changements majeurs par rapport au plan initial** :
> - La Phase 3 (RAG) est **supprimée** — livrée par l'ADR-023
> - La Phase 1 est **simplifiée** — `AgentService` est le pont naturel, pas besoin de modifier `AgentSessionPersistence`
> - La Phase 2 (mémoire) est **réduite de ~300 loc à ~135 loc** — l'infrastructure existe, seul le câblage manque
> - Nouvelle Phase 1-bis : convergence `AgentRunner` → `AgentService`

### Phase 1 — Unification de la persistence (v0.11.0)

**Objectif** : faire de `AgentService` + `BaseAIStorage` le chemin de persistence unique.

#### 1a. Implémenter `SQLiteAIStorage` (~4h)

C'est le **prérequis clé**. `AgentService` fonctionne déjà — il écrit dans `BaseAIStorage`. Le problème est que la `facade.py` injecte `InMemoryAIStorage` (volatile). Un `SQLiteAIStorage` rend tout opérationnel sans toucher à `AgentService`.

| Tâche | Description | Effort |
|-------|-------------|--------|
| **`adapters/ai/storage/sqlite.py`** | Implémenter `SQLiteAIStorage(BaseAIStorage)` — 30+ méthodes CRUD. `InMemoryAIStorage` sert de référence 1:1 | 4h |
| **Injection dans `facade.py`** | Remplacer `InMemoryAIStorage()` par `SQLiteAIStorage(db_path)` quand un backend SQLite est disponible | 30min |
| **Tests** | Dupliquer les tests `InMemoryAIStorage` pour `SQLiteAIStorage` | 1h |

#### 1b. Convergence `AgentRunner` → `AgentService` (~3h)

Faire en sorte que `AgentRunner` délègue à `AgentService` pour la persistence, au lieu d'utiliser son propre `AgentSessionPersistence`.

| Tâche | Description | Effort |
|-------|-------------|--------|
| **Injecter `AgentService` dans `AgentRunner`** | Optionnel (backward-compat) : si un `AgentService` est fourni, `AgentRunner` l'utilise pour persister conversations/messages | 2h |
| **Déprécier `AgentSessionPersistence`** | Marquer les tables v4 (`ai_agent_runs`, `ai_agent_messages`) comme deprecated. Conserver un flag `legacy_persistence=True` pour la rétro-compatibilité | 1h |

#### Diagramme de convergence (révisé)

```
AVANT (v0.10.0) — Deux chemins disjoints :

  AgentRunner.ask() (43 usages, CLI)
       │
       └──→ AgentSessionPersistence ──→ ai_agent_runs / ai_agent_messages  ✅ SQLite

  AgentService.chat() (8 usages, facade/bridges)
       │
       └──→ InMemoryAIStorage      ──→ ai_conversations / ai_messages     ❌ Volatile


APRÈS (v0.11.0) — Un seul chemin :

  AgentRunner.ask() ──→ délègue à AgentService
       │
       └──→ AgentService.chat()
                 │
                 ├──→ SQLiteAIStorage   ──→ ai_conversations / ai_messages  ✅ Persisté
                 │
                 └──→ MemoryExtractor   ──→ ai_memories                     ✅ (Phase 2)

  AgentSessionPersistence ──→ ai_agent_runs / ai_agent_messages  ⚠️ Deprecated (legacy)
```

### Phase 2 — Mémoire conversationnelle : câblage (~135 loc) (v0.11.0)

> **Contexte révisé** : l'infrastructure mémoire est **déjà en place** — ce qui manque est uniquement le câblage entre les composants existants.

**Ce qui existe déjà :**

| Composant | Fichier | État |
|-----------|---------|------|
| `AgentMemory` (modèle Pydantic) | `models/ai/memory.py` | ✅ Complet — `agent_id`, `key`, `content`, `memory_type`, `importance`, `embedding`, `expires_at`, `is_expired` |
| `MemoryType` (enum) | `models/ai/types.py` | ✅ `SHORT_TERM`, `LONG_TERM`, `EPISODIC` |
| `BaseAIStorage` memory CRUD | `ports/ai/storage.py` | ✅ `save_memory()`, `get_memory()`, `list_memories()`, `delete_memory()`, `delete_expired_memories()` |
| `InMemoryAIStorage` memory impl | `adapters/ai/storage/memory.py` | ✅ 5 méthodes implémentées |
| `AgentConfig.enable_memory` | `models/ai/agent.py` | ✅ `enable_memory: bool = True` (défaut activé) |
| `AgentService._build_conversation_context()` | `engine/ai/agent_service.py` | ✅ Short-term memory (system prompt + historique N messages) |

**Ce qui manque (3 points de câblage) :**

#### 2a. Injection des mémoires dans le contexte (~40 loc)

Modifier `AgentService._build_conversation_context()` pour charger et injecter les mémoires persistantes :

```python
# engine/ai/agent_service.py — modifier _build_conversation_context()
def _build_conversation_context(self, agent, conversation_id, max_messages=50):
    messages = []
    if agent.system_prompt:
        messages.append(Message(content=agent.system_prompt, role=MessageRole.SYSTEM, ...))

    # ── NOUVEAU : injection des mémoires persistantes ──
    if agent.config.enable_memory:
        memories = self.storage.list_memories(agent.id)
        if memories:
            top = sorted(memories, key=lambda m: m.importance, reverse=True)[:20]
            block = "\n".join(f"- [{m.memory_type.value}] {m.key}: {m.content}" for m in top)
            messages.append(Message(
                content=f"## Relevant memories\n{block}\n\nUse these to personalize responses.",
                role=MessageRole.SYSTEM,
                conversation_id=conversation_id,
            ))

    history = self.storage.get_messages(conversation_id=conversation_id, limit=max_messages)
    messages.extend(history)
    return messages
```

#### 2b. Extraction de mémoires après un échange (~80 loc)

Nouveau module `engine/ai/memory_extractor.py` — utilise le LLM pour identifier les faits à retenir :

```python
# engine/ai/memory_extractor.py — nouveau fichier
class MemoryExtractor:
    """Extrait et persiste les mémoires depuis les échanges agent."""

    def __init__(self, storage: BaseAIStorage) -> None:
        self.storage = storage

    def extract_and_save(self, agent_id, user_message, assistant_message, llm_client):
        """Analyse un échange via LLM, extrait les faits saillants, les persiste."""
        # Prompt LLM → JSON array de {key, content, memory_type, importance}
        # Upsert via self.storage.save_memory(AgentMemory(...))
```

#### 2c. Câblage dans `AgentService.chat()` (~15 loc)

Appeler `MemoryExtractor` après chaque échange réussi (best-effort, ne bloque pas le chat) :

```python
# engine/ai/agent_service.py — après save_message(assistant_message)
if agent.config.enable_memory:
    try:
        self.memory_extractor.extract_and_save(
            agent_id=agent_id,
            user_message=user_message,
            assistant_message=assistant_message,
            llm_client=llm_client,
        )
    except Exception:
        pass  # best-effort
```

> **Note coût** : l'extraction par LLM ajoute **un appel LLM supplémentaire par échange** (coût + latence). Le flag `enable_memory` dans `AgentConfig` (déjà `True` par défaut) permet de le désactiver par agent. Il pourrait être pertinent de le passer à `False` par défaut et de le rendre opt-in.

| Tâche | Description | Effort |
|-------|-------------|--------|
| **Injection mémoires dans contexte** | Modifier `_build_conversation_context()` | 1h |
| **`engine/ai/memory_extractor.py`** | Extracteur LLM → `save_memory()` | 2h |
| **Câblage dans `chat()`** | Appel best-effort post-échange | 30min |
| **CLI `pyworkflow agent memories`** | Commande pour lister / purger les mémoires d'un agent | 1h |

### ~~Phase 3 — RAG pipeline~~ → ✅ Livré par ADR-023

> **Cette phase est supprimée du plan** — intégralement livrée par l'ADR-023.
>
> Implémentation dans `adapters/ai/knowledge/` :
> - `chroma_store.py` → `ChromaVectorStore(BaseVectorStore)`
> - `numpy_store.py` → `NumpyVectorStore(BaseVectorStore)` (tests)
> - `openai_embedder.py` → `OpenAIEmbedder(BaseEmbedder)`
> - `recursive_chunker.py` → `SmartChunker(BaseChunker)`
> - `document_parser.py` → `DocumentParser(BaseDocumentParser)`
>
> Ports dans `ports/ai/` : `BaseVectorStore`, `BaseChunker`, `BaseEmbedder`, `BaseDocumentParser`.

### Phase 3 — Structured output (v0.12.0)

*(Renumérotée, anciennement Phase 4)*

| Tâche | Description | Effort |
|-------|-------------|--------|
| **Intégrer `instructor`** | Wrapper léger autour de `BaseLLMClient` pour le parsing structuré Pydantic | 2h |
| **Dépendance optionnelle** | `pip install pyworkflow-engine[structured]` → instructor | 30min |

```python
# Usage prévu :
from pyworkflow_engine.adapters.ai.structured import structured_output

class BookReview(BaseModel):
    title: str
    rating: float
    summary: str

review = structured_output(client, BookReview, "Analyse ce livre : ...")
```

### Phase 4 — Multi-agent (v0.13.0+)

*(Renumérotée, anciennement Phase 5)*

| Tâche | Description | Effort |
|-------|-------------|--------|
| **Évaluer `autogen` (Microsoft)** | Tester l'intégration comme adapter multi-agent | 2h |
| **Ou implémenter maison** | Étendre `AgentRunner` avec un `OrchestratorRunner` qui coordonne N agents | 8h |
| **Relier aux pipelines** | Un `PipelineStage` qui orchestre des agents comme une étape (pont via `ai_bridges.py`) | 4h |

> **Note** : La Phase 4 est la seule où un framework externe (autogen, crewai) pourrait apporter un ROI significatif. La décision sera réévaluée quand les Phases 1-2 seront livrées.

---

## Gestion des dépendances (révisée)

### Principe : dépendances optionnelles par feature

```toml
# pyproject.toml — extras optionnels
[project.optional-dependencies]
rag = ["chromadb>=0.5", "sentence-transformers>=3.0"]     # ✅ Déjà utilisé (ADR-023)
structured = ["instructor>=1.0"]                           # Phase 3
multiagent = []                                            # À définir en Phase 4
ai-full = ["pyworkflow-engine[rag,structured]"]
```

Les providers LLM restent des dépendances directes (déjà le cas) :

```toml
[project.optional-dependencies]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.30"]
groq = ["groq>=0.10"]
```

> **Note** : la dépendance `chromadb` est déjà en place via l'ADR-023. Aucune nouvelle dépendance n'est requise pour la Phase 2 (mémoire) — elle utilise uniquement le LLM déjà configuré et `BaseAIStorage` déjà implémenté.

---

## Alternatives considérées

### Option A — Migration complète vers LangChain

Remplacer `ports/ai/`, `adapters/ai/`, `AgentRunner` par LangChain.

**Rejeté** :
- Casse l'architecture hexagonale (ADR-006)
- ~200+ dépendances transitives ajoutées
- Historique de breaking changes (v0.1 → v0.2 incompatibles, LCEL refonte, LangGraph séparé)
- La persistence custom (`ai_agent_runs` / `ai_agent_messages` avec métriques LLM) n'a pas d'équivalent natif
- Paradigme étranger au reste du codebase (jobs, pipelines, triggers)

### Option B — LangChain comme adapter unique derrière le port

Utiliser LangChain uniquement comme implémentation de `BaseLLMClient` (derrière le port).

**Rejeté** :
- LangChain n'est pas conçu pour être un adapter passif — il veut contrôler le flow complet
- Overhead disproportionné : on n'utiliserait que `ChatOpenAI` / `ChatAnthropic`, soit exactement ce que nos adapters font déjà
- La boucle tool-calling de LangChain (`AgentExecutor`) est incompatible avec notre `ToolExecutor` qui utilise nos propres `ToolCall` / `ToolResult` Pydantic

### Option C — LiteLLM comme couche d'abstraction provider

Utiliser LiteLLM pour unifier les appels multi-provider au lieu de maintenir 5 adapters.

**Considéré positivement, décision différée** :
- LiteLLM est léger, stable, et bien conçu (100+ providers, API unifiée)
- Pourrait remplacer nos 5 adapters par un seul `LiteLLMClient(BaseLLMClient)`
- **Mais** : nos adapters actuels fonctionnent et sont bien testés
- **Décision** : réévaluer si/quand un 6ème provider est demandé, ou si la maintenance des adapters existants devient un fardeau

### Option D — Haystack (deepset) au lieu de LangChain

Framework RAG-first, plus léger que LangChain.

**Non retenu** (et désormais caduc) :
- L'ADR-023 a livré notre propre pipeline RAG hexagonal (`BaseVectorStore`, `ChromaVectorStore`, `SmartChunker`, `OpenAIEmbedder`)
- Haystack aurait apporté un overhead de framework pour un problème désormais résolu
- Le pattern « adapter sandwich » (ADR-022) appliqué au RAG s'est avéré plus cohérent que l'intégration d'un framework externe

---

## Conséquences (révisées)

### Positives

- ✅ **Architecture préservée** — Le pattern hexagonal ports/adapters reste intact, cohérent avec jobs, pipelines, triggers
- ✅ **Dépendances maîtrisées** — Pas de framework monolithique, uniquement des libs ciblées en extras optionnels
- ✅ **RAG livré** — ADR-023 a implémenté la couche Knowledge/RAG complète (`BaseVectorStore`, `ChromaVectorStore`, `OpenAIEmbedder`, `SmartChunker`, `DocumentParser`)
- ✅ **Mémoire : infrastructure prête** — `AgentMemory`, `MemoryType`, `BaseAIStorage.save_memory()`/`list_memories()` fonctionnent ; seul le câblage (~135 loc) est à écrire
- ✅ **`AgentService` identifié comme pont naturel** — Le service domaine fonctionne déjà pour conversations/messages via `BaseAIStorage`, la convergence avec `AgentRunner` est simplifiée
- ✅ **Pas de lock-in** — Chaque composant est remplaçable indépendamment

### Négatives

- ⚠️ **Code à écrire réduit mais non nul** — `SQLiteAIStorage` (~4h), câblage mémoire (~135 loc), convergence `AgentRunner`→`AgentService` (~3h)
- ⚠️ **Pas de communauté LangChain** — Les tutoriels, exemples et intégrations LangChain ne s'appliquent pas directement
- ⚠️ **Multi-agent différé** — La Phase 4 (orchestration multi-agent) reste ouverte ; pourrait nécessiter un framework externe
- ⚠️ **Extraction mémoire = coût LLM** — Chaque échange avec `enable_memory=True` déclenche un appel LLM supplémentaire pour l'extraction de faits

### Neutres

- LiteLLM reste une option ouverte pour simplifier la couche provider à terme (Option C)
- Les tables v4 (`ai_agent_runs`, `ai_agent_messages`) restent en lecture seule pour l'historique existant (147 runs, 361 messages)
- La Phase 4 fera l'objet d'une ADR dédiée quand les besoins multi-agent se préciseront

---

## Métriques de suivi (révisées)

| Métrique | Baseline (v0.10.0) | État actuel (post-ADR-023) | Cible (v0.12.0) |
|----------|-------------------|---------------------------|-----------------|
| Tables AI remplies (en DB durable) | 2/5 (`ai_agent_runs`, `ai_agent_messages`) | 2/5 (idem — `AgentService` écrit dans les Rich API mais via `InMemoryAIStorage` volatile) | 5/5 (+ `ai_conversations`, `ai_messages`, `ai_memories` via `SQLiteAIStorage`) |
| Providers LLM supportés | 5 | 5 | 5 (réévaluer LiteLLM si besoin d'un 6ème) |
| RAG pipeline | ❌ Modèles seuls | ✅ **Implémenté** (ADR-023) — 4 ports + 5 adapters | ✅ Done |
| Stratégies mémoire | 0 | Infrastructure prête (modèles + ports + storage), câblage manquant | 1 (extraction LLM + injection contexte) |
| Vectorstore intégré | 0 | ✅ **2** (ChromaVectorStore + NumpyVectorStore) | ✅ Done |
| Orchestrateurs unifiés | 2 disjoints (`AgentRunner`, `AgentService`) | 2 disjoints | 1 (`AgentRunner` → `AgentService`) |
| Dépendances transitives AI | ~15 | ~20 (+ chromadb via ADR-023) | ~25 (avec extras structured) |
| Lignes de code couche AI | ~3500 | ~4500 (+ knowledge/) | ~4700 (+SQLiteAIStorage, +memory câblage) |
| **Effort restant estimé** | ~1600 loc | — | **~300 loc + 8h config/tests** (vs ~1600 initial) |

---

## Références

- **ADR-006** — Architecture hexagonale : ports et adapters
- **ADR-013** — Intégration AI engine (modèles, tables, ports)
- **ADR-016** — Master integration plan
- **ADR-018** — Réorganisation des modèles, namespacing SQL
- **ADR-019** — Catalogue `agents/` (instances concrètes)
- **ADR-023** — Architecture Knowledge & RAG (ports, adapters, embeddings) ✅ implémenté
- **LangChain** — https://python.langchain.com/ (comparatif)
- **LiteLLM** — https://docs.litellm.ai/ (Option C différée)
- **Instructor** — https://python.useinstructor.com/ (Phase 3 structured output)

### Fichiers clés du codebase

| Fichier | Rôle | Pertinence ADR-020 |
|---------|------|---------------------|
| `engine/ai/agent_service.py` | Service domaine : CRUD agents, `chat()`, `_build_conversation_context()` | **Writer Rich API** — pont naturel pour la convergence persistence |
| `agents/shared/runner.py` | `AgentRunner` : exécution CLI (43 usages) | Chemin dominant, à faire converger vers `AgentService` |
| `agents/shared/persistence.py` | `AgentSessionPersistence` : tables v4 SQLite | Legacy, à déprécier |
| `ports/ai/storage.py` | `BaseAIStorage` : 30+ méthodes CRUD (dont memory) | Port central, toute l'infrastructure mémoire y est définie |
| `adapters/ai/storage/memory.py` | `InMemoryAIStorage` : implem de référence | Backend actuel (volatile), à compléter par `SQLiteAIStorage` |
| `models/ai/agent.py` | `AgentConfig` avec `enable_memory=True`, `enable_rag=False` | Flags de feature déjà en place |
| `models/ai/memory.py` | `AgentMemory` : modèle Pydantic complet | Infrastructure mémoire prête |
| `models/ai/types.py` | `MemoryType` : `SHORT_TERM`, `LONG_TERM`, `EPISODIC` | Types de mémoire définis |
| `adapters/ai/knowledge/` | RAG pipeline complet (ADR-023) | Phase 3 originale → livrée |
| `adapters/steps/ai_bridges.py` | `AIStep`, `AgentExecutor`, `JobAsTool` | Bridges workflow ↔ IA via `AgentService` |
| `facade.py` (ligne ~747) | Injection `InMemoryAIStorage` dans `AgentService` | Point d'injection à modifier pour `SQLiteAIStorage` |

---

## Annexe — Historique des révisions

| Date | Changement |
|------|-----------|
| 12 avril 2026 (initial) | Rédaction initiale : analyse LangChain vs maison, plan 5 phases |
| 12 avril 2026 (révision) | **Révision majeure** suite à l'audit approfondi : |
| | — Découverte de `engine/ai/agent_service.py` comme writer Rich API existant |
| | — Correction du constat « aucun writer » → « writer existe, branché sur InMemoryAIStorage volatile » |
| | — Identification du dualisme `AgentRunner` (43 usages) vs `AgentService` (8 usages) |
| | — Prise en compte de l'ADR-023 (RAG livré) : suppression de la Phase 3 originale |
| | — Inventaire de l'infrastructure mémoire existante : `AgentMemory`, `MemoryType`, `BaseAIStorage` memory CRUD, `AgentConfig.enable_memory` |
| | — Réduction de l'effort estimé : ~1600 loc → ~300 loc + 8h config/tests |
| | — Score synthétique maison : 21/25 → 23/25 |
