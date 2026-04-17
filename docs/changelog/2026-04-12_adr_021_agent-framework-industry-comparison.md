# ADR-021 — Positionnement de pyworkflow-engine face aux frameworks agents 2026

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-021                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (hexagonal), ADR-013 (AI engine), ADR-019 (agents catalog), ADR-020 (framework strategy) |
| **Version cible** | v0.12.0                        |

---

## Contexte

### Les 4 frameworks agents dominants en 2026

L'écosystème des frameworks agents IA s'est structuré autour de 4 paradigmes distincts :

| Framework | Éditeur | Paradigme | Philosophie |
|-----------|---------|-----------|-------------|
| **OpenAI Agents SDK** | OpenAI | Agent + tools + handoffs | Simplicité, production-first, lock-in OpenAI |
| **LangGraph** | LangChain Inc. | State machine + graph | Orchestration avancée, contrôle total, verbeux |
| **AutoGen** | Microsoft | Multi-agent conversation | Agents qui « débattent », émergence, research-first |
| **Google Agent SDK (ADK)** | Google | Agent + GCP infra | Enterprise, sécurité, intégration data GCP-native |

### La question posée

Face à cette offre, **pyworkflow-engine doit-il adopter, intégrer ou ignorer ces frameworks ?** Et plus spécifiquement : **AutoGen (multi-agent conversation) est-il pertinent pour le projet ?**

Cette ADR prolonge l'ADR-020 (qui traitait LangChain seul) en élargissant l'analyse aux 4 frameworks et en approfondissant le cas AutoGen.

---

« pyworkflow-engine n'est pas un concurrent des 4 frameworks — c'est la couche d'orchestration dans laquelle ces frameworks pourraient s'intégrer comme adapters. »

## Analyse comparative : pyworkflow-engine vs les 4 frameworks

### Mapping des paradigmes

L'audit du codebase révèle que pyworkflow-engine **couvre déjà** une partie significative de chaque paradigme :

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PARADIGMES INDUSTRIE                              │
│                                                                     │
│   OpenAI Agents SDK          LangGraph                              │
│   agent + tools + handoffs   state machine + graph                  │
│         │                          │                                │
│         ▼                          ▼                                │
│   ┌──────────┐              ┌──────────────┐                        │
│   │AgentRunner│              │WorkflowEngine│                        │
│   │ToolRegistry│             │Pipeline      │                        │
│   │ToolExecutor│             │PipelineStage │                        │
│   └──────────┘              │DAGResolver   │                        │
│     ~70%                    │context_mapping│                        │
│     couvert                 └──────────────┘                        │
│                               ~80% couvert                          │
│                                                                     │
│   AutoGen                    Google ADK                              │
│   multi-agent conversation   enterprise + GCP                       │
│         │                          │                                │
│         ▼                          ▼                                │
│   ┌──────────┐              ┌──────────────┐                        │
│   │(rien)    │              │(non pertinent)│                        │
│   │          │              │pas sur GCP    │                        │
│   └──────────┘              └──────────────┘                        │
│     0%                        N/A                                   │
│     couvert                                                         │
└─────────────────────────────────────────────────────────────────────┘
```

### Détail du mapping par framework

#### 🔵 OpenAI Agents SDK — Couverture ~70%

| Primitive OpenAI | Équivalent pyworkflow-engine | Fichier | Gap |
|-----------------|------------------------------|---------|-----|
| `Agent` | `Agent` (Pydantic model + AgentConfig) | `models/ai/agent.py` | ✅ Équivalent |
| `Runner` | `AgentRunner` (one-shot, async, REPL) | `agents/shared/runner.py` | ✅ Équivalent |
| `@tool` | `ToolRegistry.register()` + `ToolDefinition` | `adapters/ai/tools/registry.py` | ✅ Équivalent |
| Tool execution loop | `ToolExecutor.run_tool_loop()` (max_iterations) | `adapters/ai/tools/executor.py` | ✅ Équivalent |
| `handoff()` | ❌ Pas d'implémentation | — | **Gap : handoff inter-agents** |
| `guardrails` | ❌ Pas de validation input/output structurée | — | **Gap : guardrails** |
| Streaming | `BaseLLMClient.stream()` / `astream()` | `ports/ai/llm.py` | ✅ Équivalent |
| Multi-provider | 5 adapters (OpenAI, Anthropic, Groq, Ollama, Gemini) | `adapters/ai/llm/` | ✅ **Supérieur** (OpenAI SDK = lock-in) |
| Persistence sessions | `AgentSessionPersistence` (runs + messages + métriques) | `agents/shared/persistence.py` | ✅ **Supérieur** |

**Verdict** : L'OpenAI Agents SDK est plus simple à utiliser pour un cas basique (30 lignes → agent qui marche). Mais pyworkflow-engine offre plus de contrôle, plus de providers, et une meilleure persistence. Les 2 gaps (handoff, guardrails) sont comblables en ~200 lignes.

#### 🟣 LangGraph — Couverture ~80%

| Primitive LangGraph | Équivalent pyworkflow-engine | Fichier | Gap |
|--------------------|------------------------------|---------|-----|
| `StateGraph` | `Pipeline` + `PipelineStage` (séquence de jobs) | `models/pipeline/pipeline.py` | ✅ Similaire |
| `nodes` | `Step` (unité d'exécution atomique) | `models/workflow/step.py` | ✅ Équivalent |
| `edges` | Dépendances `Step.depends_on` + `DAGResolver` | `engine/dag.py` | ✅ Équivalent |
| `State` (TypedDict) | `WorkflowContext` (dict propagé entre steps) | `engine/context.py` | ✅ Équivalent |
| `context_mapping` | `PipelineStage.context_mapping` (propagation inter-stages) | `models/pipeline/pipeline.py` | ✅ Identique |
| Conditional edges | `PipelineStage.condition: Callable` + `Step.condition` | `models/pipeline/pipeline.py` | ✅ Équivalent |
| Checkpointing | ❌ Pas de snapshot/restore du state | — | **Gap : checkpointing** |
| Time-travel / replay | ❌ Pas de rejeu à partir d'un checkpoint | — | **Gap : replay** |
| Human-in-the-loop | `StepType.HUMAN_APPROVAL` + `SuspensionManager` | `engine/suspension.py` | ✅ Équivalent |
| Multi-provider | 5 adapters LLM natifs | `adapters/ai/llm/` | ✅ Équivalent |

**Verdict** : pyworkflow-engine **est** un LangGraph-like par construction. Le commentaire de ChatGPT — *« ton pyworkflow_engine ressemble déjà à ça »* — est exact. Les 2 gaps (checkpointing, replay) sont des features de résilience avancée, pas des manques fondamentaux.

#### 🟢 AutoGen — Couverture 0%

| Primitive AutoGen | Équivalent pyworkflow-engine | Gap |
|------------------|------------------------------|-----|
| `ConversableAgent` | ❌ Aucun agent ne parle à un autre agent | **Fondamental** |
| Conversation protocol | ❌ Pas de boucle multi-agent | **Fondamental** |
| `GroupChat` | ❌ Pas de chat de groupe | **Fondamental** |
| `GroupChatManager` | ❌ Pas d'arbitre de conversation | **Fondamental** |
| Code execution sandbox | ❌ Pas de sandbox intégré | **Significatif** |
| Human-in-the-loop | ✅ `StepType.HUMAN_APPROVAL` | Couvert |

**Verdict** : Le paradigme AutoGen est **fondamentalement absent** de pyworkflow-engine. Mais est-ce un problème ? Voir l'analyse détaillée ci-dessous.

#### 🟡 Google Agent SDK — Non pertinent

Le Google ADK est optimisé pour GCP (Vertex AI, BigQuery, IAM). pyworkflow-engine n'est pas sur GCP. **Aucune action requise.**

---

## Focus : AutoGen est-il pertinent pour pyworkflow-engine ?

### État des agents existants

L'audit du catalogue `agents/manifest.yaml` révèle **5 agents**, tous **single-agent** :

| Agent | Rôle | Interaction inter-agents | Mode d'usage |
|-------|------|-------------------------|-------------|
| `general-assistant` | `ASSISTANT` | ❌ Solo | One-shot / REPL |
| `doc-researcher` | `RESEARCHER` | ❌ Solo | One-shot |
| `code-reviewer` | `CODER` | ❌ Solo | One-shot |
| `data-analyst` | `ANALYST` | ❌ Solo | One-shot |
| `pipeline-planner` | `ORCHESTRATOR` | ❌ Solo* | One-shot |

> \* Le `pipeline-planner` a un system prompt qui mentionne les autres agents (« Agents disponibles : general-assistant, doc-researcher, code-reviewer, data-analyst »), mais il ne les invoque pas réellement. Il produit un **plan textuel**, pas une exécution multi-agent.

**Conclusion : 100% des agents sont single-agent. Aucun cas d'usage multi-agent n'existe aujourd'hui.**

### Scénarios multi-agent évalués

| Scénario | AutoGen utile ? | Pourquoi |
|----------|----------------|----------|
| `code-reviewer` → `doc-writer` (chaîne séquentielle) | ❌ Non | C'est un **pipeline séquentiel**, pas une conversation. Le modèle `Pipeline` existant le fait déjà via `PipelineStage` |
| `data-analyst` débat avec `code-reviewer` | ❌ Non | Aucun bénéfice objectif — un seul agent avec le bon system prompt produit un résultat plus fiable et moins coûteux |
| Agent auto-correctif (reflection loop) | ⚠️ Marginalement | Implémentable en ~50 lignes dans `AgentRunner` (appeler `ask()` en boucle avec le feedback) — pas besoin d'un framework |
| `pipeline-planner` qui délègue **réellement** à N agents | ✅ Oui, potentiellement | Pattern « orchestrator → workers ». Pertinent à terme, mais implémentable via un `AgentPipeline` léger |

### 5 raisons de ne PAS adopter AutoGen

#### 1. AutoGen résout un problème que le projet n'a pas (encore)

Aucun cas d'usage concret ne nécessite que des agents « débattent ». Le `pipeline-planner` produit un plan textuel — il n'a pas besoin d'exécuter les agents qu'il mentionne. Si ce besoin émerge, il sera couvert par le pattern `AgentPipeline` (voir « Solution proposée »).

#### 2. Le non-déterminisme est un deal-breaker architectural

L'architecture de pyworkflow-engine est construite sur le **déterminisme observable** :

```
Step → statut clair (SUCCESS / FAILED / SKIPPED)
     → durée mesurée
     → context propagé
     → persistance en BD (step_runs)
```

AutoGen fonctionne par « conversation émergente » :

```
Agent A dit → Agent B répond → Agent A reformule → ...
     → nombre de tours inconnu
     → coût en tokens imprévisible
     → résultat non garanti
```

Ces deux philosophies sont **fondamentalement incompatibles**. Introduire AutoGen dans le runtime créerait une zone d'opacité au milieu d'un système conçu pour la transparence.

#### 3. Le coût en tokens est explosif et non contrôlable

Benchmark estimé pour une tâche de code review + documentation :

| Approche | Appels LLM | Tokens estimés | Coût ($15/M tokens) |
|----------|-----------|----------------|---------------------|
| Single agent bien prompté | 1 | ~2 000 | $0.03 |
| Pipeline séquentielle (2 agents) | 2 | ~4 000 | $0.06 |
| AutoGen 3 agents × 5 tours | 15 | ~30 000 | $0.45 |
| AutoGen 3 agents × 10 tours (convergence lente) | 30 | ~60 000 | $0.90 |

Pour le même résultat, AutoGen coûte **15× à 30× plus cher** qu'un pipeline séquentiel.

#### 4. AutoGen est instable en production

L'historique du projet est symptomatique :

| Date | Événement |
|------|-----------|
| 2023-09 | AutoGen v0.1 (Microsoft Research) |
| 2024-06 | Refonte v0.2 (breaking changes majeurs) |
| 2024-11 | Fork **AG2** par une partie de l'équipe |
| 2025-03 | AutoGen v0.4 (nouvelle architecture, incompatible v0.2) |
| 2025-09 | AutoGen Studio (UI) abandonné |
| 2026-01 | AG2 et AutoGen sont désormais deux projets séparés |

Adopter AutoGen signifie parier sur un projet qui s'est scindé en deux et dont l'API a été réécrite 3 fois en 30 mois.

#### 5. La dépendance est lourde et contamine le graphe

```
pyautogen → openai, chromadb, docker, jupyter, flaml, diskcache, termcolor, ...
         → ~60+ dépendances transitives
```

Comparé au profil minimaliste de pyworkflow-engine (pydantic, httpx, typer, rich), c'est disproportionné pour une feature non utilisée.

---

## Décision

### AutoGen est rejeté. Le multi-agent sera couvert par un `AgentPipeline` léger.

L'orchestration multi-agent est un besoin **futur et ciblé** (pattern orchestrator → workers), pas un besoin de conversation émergente (pattern AutoGen). La solution est un composant maison de ~90 lignes qui réutilise intégralement l'infrastructure existante.

### Aucun des 4 frameworks n'est adopté comme dépendance

| Framework | Décision | Justification |
|-----------|----------|---------------|
| **OpenAI Agents SDK** | ❌ Non adopté | Lock-in OpenAI, 70% déjà couvert, gaps comblables |
| **LangGraph** | ❌ Non adopté | 80% déjà couvert, philosophie trop opinionated |
| **AutoGen** | ❌ Non adopté | 0% d'overlap, non-déterministe, instable, coûteux |
| **Google ADK** | ❌ Non pertinent | Pas sur GCP |

### Stratégie : combler les 4 gaps identifiés en interne

```
┌─────────────────────────────────────────────────────────┐
│  Gaps identifiés (croisement des 4 frameworks)          │
│                                                         │
│  1. Agent handoff (OpenAI SDK)     → Phase 1            │
│  2. Checkpointing / replay (LangGraph) → Phase 2       │
│  3. Multi-agent pipeline (AutoGen-like) → Phase 3       │
│  4. Guardrails (OpenAI SDK)        → Phase 4            │
│                                                         │
│  Chaque gap = composant interne,                        │
│  intégré dans l'architecture hexagonale existante        │
└─────────────────────────────────────────────────────────┘
```

---

## Plan d'implémentation

### Phase 1 — Agent Handoff (v0.11.0) — ~150 lignes

Permettre à un agent de déléguer à un autre agent via un protocole explicite (pas une conversation émergente).

```python
# agents/shared/handoff.py — Protocole de délégation inter-agents

@dataclass
class HandoffRequest:
    """Demande de délégation d'un agent source vers un agent cible."""
    source_agent_slug: str
    target_agent_slug: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

@dataclass
class HandoffResult:
    """Résultat de la délégation."""
    source_agent_slug: str
    target_agent_slug: str
    response: str
    tokens_used: int = 0
    success: bool = True
```

```python
# Extension de AgentRunner :
class AgentRunner:
    # ...existing code...

    def handoff(self, target_slug: str, message: str,
                context: dict | None = None) -> LLMResponse:
        """Délègue un message à un autre agent et retourne sa réponse.

        Le handoff est **synchrone et explicite** — pas de conversation
        émergente. L'agent source décide consciemment de déléguer.
        """
        from agents.shared.loader import load_agent_by_slug
        target_agent = load_agent_by_slug(target_slug)
        target_runner = AgentRunner(target_agent, persist=True,
                                     triggered_by="handoff")
        response = target_runner.ask(message)
        target_runner.finish()
        return response
```

| Propriété | Valeur |
|-----------|--------|
| Déterministe | ✅ Oui — un appel, une réponse |
| Traçable | ✅ Oui — chaque handoff crée son propre run dans `ai_agent_runs` |
| Coût contrôlé | ✅ Oui — 1 appel LLM par handoff |
| Effort | ~150 lignes |

### Phase 2 — Checkpointing / Replay (v0.11.0) — ~200 lignes

Permettre de sauvegarder l'état d'un pipeline à un point donné et de reprendre l'exécution depuis ce point.

```python
# ports/checkpoint.py — Nouveau port (contrat abstrait)

class BaseCheckpointStore(ABC):
    """Contrat pour la persistence de checkpoints de pipeline."""

    @abstractmethod
    def save(self, pipeline_run_id: str, stage_index: int,
             context: dict[str, Any]) -> str:
        """Sauvegarde un snapshot du contexte à un stage donné."""

    @abstractmethod
    def load(self, checkpoint_id: str) -> dict[str, Any]:
        """Charge un checkpoint pour reprise d'exécution."""

    @abstractmethod
    def list_for_run(self, pipeline_run_id: str) -> list[dict]:
        """Liste les checkpoints disponibles pour un run."""
```

| Propriété | Valeur |
|-----------|--------|
| Pattern | LangGraph-inspiré (checkpointing), adapté au modèle Pipeline |
| Stockage | Table SQLite `pipeline_checkpoints` via adapter `SQLiteCheckpointStore` |
| Replay | `engine.resume_pipeline(checkpoint_id)` → reprend depuis le stage N |
| Effort | ~200 lignes (port + adapter SQLite + extension facade) |

### Phase 3 — AgentPipeline (v0.12.0) — ~100 lignes

Orchestration **séquentielle et déterministe** d'agents — l'alternative légère au paradigme AutoGen. Chaque stage exécute un agent et passe son output comme input au suivant (pattern pipe-and-filter).

```python
# agents/shared/pipeline.py — Orchestration séquentielle d'agents

@dataclass
class AgentStage:
    """Un agent dans le pipeline d'orchestration."""
    agent_slug: str
    prompt_template: str = "{input}"    # {input} = output précédent
                                         # {original} = input initial
    max_turns: int = 1
    stop_on_error: bool = True

@dataclass
class AgentPipelineResult:
    """Résultat d'exécution d'un pipeline d'agents."""
    stages_completed: int = 0
    outputs: dict[str, str] = field(default_factory=dict)
    total_tokens: int = 0
    total_response_time_ms: float = 0.0
    success: bool = True
    error: str | None = None

class AgentPipeline:
    """Orchestration séquentielle d'agents — alternative à AutoGen.

    Exemple ::

        pipeline = AgentPipeline(stages=[
            AgentStage("code-reviewer",
                       prompt_template="Review this code:\\n{input}"),
            AgentStage("doc-writer",
                       prompt_template="Write docs for reviewed code:\\n{input}"),
        ])
        result = pipeline.run("def add(a, b): return a + b")
    """

    def __init__(self, stages: list[AgentStage],
                 name: str = "agent-pipeline") -> None:
        self.stages = stages
        self.name = name

    def run(self, initial_input: str, **kwargs) -> AgentPipelineResult:
        """Exécute chaque stage séquentiellement."""
        from agents.shared.loader import load_agent_by_slug

        result = AgentPipelineResult()
        current_input = initial_input

        for stage in self.stages:
            try:
                agent = load_agent_by_slug(stage.agent_slug)
                runner = AgentRunner(agent, persist=True,
                                     triggered_by="agent-pipeline")

                prompt = stage.prompt_template.format(
                    input=current_input,
                    original=initial_input,
                )
                response = runner.ask(prompt, **kwargs)
                runner.finish()

                current_input = response.content
                result.outputs[stage.agent_slug] = response.content
                if response.usage:
                    result.total_tokens += response.usage.total_tokens or 0
                if response.response_time_ms:
                    result.total_response_time_ms += response.response_time_ms
                result.stages_completed += 1

            except Exception as exc:
                result.success = False
                result.error = f"Stage '{stage.agent_slug}' failed: {exc}"
                if stage.stop_on_error:
                    break

        return result
```

#### Comparaison directe : AgentPipeline vs AutoGen

| Critère | AutoGen | `AgentPipeline` |
|---------|---------|-----------------|
| Lignes de code framework | ~15 000 | ~100 |
| Dépendances ajoutées | ~60 transitives | 0 |
| Déterminisme | ❌ Émergent (nombre de tours inconnu) | ✅ Séquentiel (1 tour par stage) |
| Coût tokens | ❌ Explosif (N agents × M tours) | ✅ Contrôlé (1 appel par stage) |
| Persistence | ❌ Non intégré | ✅ Chaque stage crée son propre run via `AgentSessionPersistence` |
| Observabilité | ❌ Logs custom à implémenter | ✅ Réutilise le logging structuré existant |
| Debugging | ❌ Conversation opaque | ✅ Output de chaque stage visible dans `result.outputs` |
| Human-in-the-loop | ✅ Natif | ⚠️ À implémenter (ajout d'un flag `requires_approval` sur `AgentStage`) |
| Conversation libre | ✅ Agents débattent | ❌ Séquentiel pur (design voulu) |

#### Quand AutoGen serait-il justifié ?

Le seul scénario où AutoGen apporte une valeur que `AgentPipeline` ne couvre pas :

> **Des agents qui doivent itérer librement sur un problème ouvert avec un critère de convergence flou.**

Exemples réels : recherche scientifique collaborative, brainstorming créatif multi-perspectives, débat contradictoire sur une architecture.

**Ce n'est pas le cas d'usage de pyworkflow-engine**, qui orchestre des **workflows data déterministes** (ingestion, transformation, reporting). Si ce besoin émerge un jour, une ADR dédiée sera créée.

### Phase 4 — Guardrails (v0.12.0) — ~150 lignes

Validation structurée des inputs et outputs d'un agent.

```python
# agents/shared/guardrails.py

@dataclass
class Guardrail:
    """Règle de validation appliquée avant ou après un appel LLM."""
    name: str
    check: Callable[[str], bool]     # True = pass, False = block
    on_fail: str = "block"           # "block" | "warn" | "retry"
    message: str = ""

class GuardrailChain:
    """Chaîne de guardrails appliquée à un AgentRunner."""

    def __init__(self, guardrails: list[Guardrail]) -> None:
        self.guardrails = guardrails

    def validate_input(self, message: str) -> tuple[bool, str | None]:
        """Valide le message utilisateur avant envoi au LLM."""
        for g in self.guardrails:
            if not g.check(message):
                return False, f"Guardrail '{g.name}' failed: {g.message}"
        return True, None

    def validate_output(self, response: str) -> tuple[bool, str | None]:
        """Valide la réponse LLM avant retour à l'utilisateur."""
        for g in self.guardrails:
            if not g.check(response):
                return False, f"Guardrail '{g.name}' failed: {g.message}"
        return True, None
```

| Effort | ~150 lignes |
|--------|-------------|
| Intégration | Hook dans `AgentRunner.ask()` : `pre_call` et `post_call` |
| Exemples | `max_length`, `no_pii`, `language_check`, `no_code_execution` |

---

## Positionnement stratégique

### pyworkflow-engine n'est pas un concurrent des 4 frameworks

C'est la **couche d'orchestration** dans laquelle ces frameworks *pourraient* s'intégrer comme adapters :

```
┌──────────────────────────────────────────────────────────────┐
│  pyworkflow-engine                                           │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐               │
│  │ Jobs      │  │ Pipelines │  │ Agents    │               │
│  │ Steps     │  │ Stages    │  │ Runner    │               │
│  │ DAG       │  │ Context   │  │ Tools     │               │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘               │
│        │              │              │                       │
│        ▼              ▼              ▼                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ports/    (contrats abstraits — ABC purs)           │   │
│  │  BaseLLMClient  BaseStorage  BaseTrigger  BaseAIStor.│   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  adapters/  (implémentations concrètes)              │   │
│  │                                                      │   │
│  │  OpenAIClient     AnthropicClient    GroqClient      │   │
│  │  SQLiteStorage    CronTrigger        ToolRegistry    │   │
│  │                                                      │   │
│  │  ┌─── Adapters futurs possibles (pas prévus) ───┐   │   │
│  │  │  LangGraphAdapter  (Pipeline → LangGraph)     │   │   │
│  │  │  OpenAIAgentAdapter (Runner → OpenAI SDK)     │   │   │
│  │  │  LiteLLMClient (BaseLLMClient → LiteLLM)     │   │   │
│  │  └───────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### Matrice de valeur ajoutée par rapport à chaque framework

| Ce que pyworkflow-engine fait **mieux** | Pourquoi |
|----------------------------------------|----------|
| Persistence intégrée des sessions IA | `ai_agent_runs` + `ai_agent_messages` avec métriques LLM complètes (tokens, temps, finish_reason) — aucun framework ne fait ça nativement |
| Cohérence jobs/pipelines/agents | Un seul pattern architectural (hexagonal) pour 3 types d'exécution — pas 3 paradigmes différents |
| Multi-provider sans lock-in | 5 providers derrière le même port `BaseLLMClient` — l'OpenAI SDK ne supporte que OpenAI |
| Observabilité structurée | Logging JSON + DB persistence intégrés — LangGraph dépend de LangSmith (service externe payant) |
| Poids des dépendances | ~15 deps directes vs ~200+ pour LangChain/LangGraph, ~60+ pour AutoGen |

| Ce que pyworkflow-engine fait **moins bien** | Qui le fait mieux |
|----------------------------------------------|-------------------|
| Conversation émergente multi-agent | AutoGen |
| DX « 30 lignes → agent qui marche » | OpenAI Agents SDK |
| Checkpointing / time-travel avancé | LangGraph |
| RAG pipeline intégré | LangChain (mais comblé par ADR-020 Phase 3) |

---

## Récapitulatif des livrables

| Phase | Composant | Inspiré de | Lignes | Version |
|-------|-----------|-----------|--------|---------|
| 1 | Agent Handoff (`agents/shared/handoff.py`) | OpenAI Agents SDK | ~150 | v0.11.0 |
| 2 | Checkpointing (`ports/checkpoint.py` + adapter) | LangGraph | ~200 | v0.11.0 |
| 3 | AgentPipeline (`agents/shared/pipeline.py`) | AutoGen (simplifié) | ~100 | v0.12.0 |
| 4 | Guardrails (`agents/shared/guardrails.py`) | OpenAI Agents SDK | ~150 | v0.12.0 |
| **Total** | | | **~600** | |

---

## Alternatives considérées

### Option A — Adopter AutoGen pour le multi-agent

**Rejeté** pour les 5 raisons détaillées ci-dessus : pas de cas d'usage, non-déterministe, coûteux, instable, lourd.

### Option B — Adopter l'OpenAI Agents SDK comme couche d'exécution

**Rejeté** : lock-in OpenAI incompatible avec l'approche multi-provider (5 adapters). Le SDK n'apporte rien que `AgentRunner` + `ToolExecutor` ne fassent déjà.

### Option C — Adopter LangGraph pour l'orchestration

**Rejeté** : le modèle `Pipeline` + `PipelineStage` + `DAGResolver` couvre déjà 80% du paradigme LangGraph. Introduire LangGraph impliquerait de maintenir deux systèmes d'orchestration parallèles.

### Option D — Hybrid stack (LangGraph orchestration + OpenAI SDK exécution)

Le comparatif ChatGPT suggérait : *« combo idéal = LangGraph-like core + OpenAI Agents pour execution + event-driven system »*.

**Analyse** : cette recommandation est exacte, mais pyworkflow-engine **est déjà** ce hybrid stack :
- LangGraph-like core → `WorkflowEngine` + `Pipeline` + `DAGResolver`
- Agents pour execution → `AgentRunner` + `ToolExecutor` (multi-provider)
- Event-driven system → `BaseTrigger` + `CronTrigger` + `ManualTrigger` + callbacks

L'architecture est déjà positionnée correctement. Les 4 phases de cette ADR comblent les gaps restants sans dépendance externe.

### Option E — LiteLLM comme couche d'abstraction provider

**Décision différée** (cf. ADR-020) : réévaluer si/quand un 6ème provider est demandé.

---

## Conséquences

### Positives

- ✅ **Zéro dépendance framework ajoutée** — les 600 lignes prévues utilisent uniquement la stdlib + les abstractions existantes
- ✅ **Déterminisme préservé** — le multi-agent reste séquentiel et observable, pas émergent
- ✅ **Coûts maîtrisés** — pas de boucles conversationnelles explosives en tokens
- ✅ **Architecture cohérente** — handoff, checkpointing, AgentPipeline et guardrails s'intègrent dans les ports/adapters existants
- ✅ **Porte ouverte** — si un framework externe devient pertinent, il s'intégrerait comme adapter derrière un port existant

### Négatives

- ⚠️ **Pas de conversation émergente** — si un cas d'usage de « débat entre agents » émerge, il faudra réévaluer (nouvelle ADR)
- ⚠️ **Pas de sandbox d'exécution de code** — AutoGen offre ça nativement ; serait un développement séparé si besoin
- ⚠️ **~600 lignes à écrire** — mais réparties sur 2 versions (v0.11.0 et v0.12.0)

### Neutres

- L'ADR-020 reste valide et complémentaire (elle couvre mémoire, RAG, structured output)
- Le `pipeline-planner` pourra évoluer pour utiliser `AgentPipeline` au lieu de produire un plan textuel — quand la Phase 3 sera livrée
- AutoGen pourra être réévalué si le projet se restructure et livre une API stable (post-v1.0)

---

## Métriques de suivi

| Métrique | Baseline (v0.10.0) | Cible (v0.12.0) |
|----------|-------------------|-----------------|
| Paradigmes couverts (sur 4) | 2/4 (LangGraph-like ~80%, OpenAI-like ~70%) | 3/4 (+AutoGen-like ~60% via AgentPipeline) |
| Agents multi-agent-capable | 0/5 | 5/5 (via handoff + AgentPipeline) |
| Frameworks externes adoptés | 0 | 0 (design voulu) |
| Lignes couche agent | ~1 200 | ~1 800 (+600) |
| Dépendances transitives | ~15 | ~15 (inchangé) |

---

## Références

- **ADR-006** — Architecture hexagonale : ports et adapters
- **ADR-019** — Catalogue `agents/` (instances concrètes)
- **ADR-020** — Stratégie framework IA : architecture maison vs LangChain
- **OpenAI Agents SDK** — https://platform.openai.com/docs/guides/agents-sdk
- **LangGraph** — https://langchain-ai.github.io/langgraph/
- **AutoGen** — https://microsoft.github.io/autogen/
- **Google Agent SDK** — https://google.github.io/adk-docs/
- **`agents/manifest.yaml`** — Catalogue des 5 agents concrets
- **`agents/orchestrators/pipeline_planner.py`** — Agent orchestrateur (plan textuel)
- **`agents/shared/runner.py`** — `AgentRunner` (ask, aask, repl, handoff futur)
- **`models/pipeline/pipeline.py`** — `Pipeline` + `PipelineStage` (LangGraph-like)
- **`adapters/ai/tools/executor.py`** — `ToolExecutor.run_tool_loop()` (boucle tool-calling)
- **`ports/trigger.py`** — `BaseTrigger` (event-driven system)
- **`adapters/triggers/schedule.py`** — `CronTrigger` (cron 5 champs, stdlib pure)
