#!/usr/bin/env python3
"""
Exemple — Démonstration complète du sous-système AI Storage (ADR-020 / ADR-021).

Ce script illustre l'architecture hexagonale du backend de persistence IA de
``pyworkflow-engine`` en parcourant les 8 domaines exposés par ``BaseAIStorage`` :

  1. **Provider**      — configurer un fournisseur LLM (OpenAI, Anthropic…)
  2. **Agent**         — créer et lister des agents avec rôles et slugs
  3. **Tool**          — enregistrer des outils function-calling
  4. **Skill**         — définir des compétences composites + assignments
  5. **Conversation**  — démarrer des conversations et récupérer l'historique
  6. **Message**       — persister des échanges USER / ASSISTANT
  7. **Execution**     — tracer des runs IA avec leurs étapes détaillées
  8. **Memory**        — stocker/rappeler des mémoires persistantes inter-sessions

Deux backends sont démontrés côte à côte :
  • ``InMemoryAIStorage``  — zéro configuration, idéal pour les tests
  • ``SQLiteAIStorage``    — fichier SQLite durable, production-ready

Scénarios :
  A. Bootstrap — providers + agents + tools + skills
  B. Conversation multi-turn avec mémorisation
  C. Execution tracking (LLM call → tool call → résultat)
  D. Mémoire persistante : écriture, lecture filtrée, expiration
  E. Transactions atomiques (SQLite uniquement)
  F. Lecture croisée — même données relues depuis disque
  G. Nettoyage — delete cascade, close

Architecture (ADR-020) :
  BaseAIStorage (port)
  ├── InMemoryAIStorage   (adapter — adapters/ai/storage/memory.py)
  └── SQLiteAIStorage     (adapter — adapters/ai/storage/sqlite.py)

Conforme ADR-021 (positionnement framework IA) :
  l'architecture hexagonale permet de swapper le backend
  sans toucher au code applicatif — AgentService l'exploite
  exactement de la même façon quelle que soit l'implémentation.

Prérequis :
  pip install pyworkflow-engine   # ou : uv sync

Usage :
  uv run python examples/ai_storage_demo.py           # démo complète
  uv run python examples/ai_storage_demo.py --memory  # InMemory seulement
  uv run python examples/ai_storage_demo.py --sqlite  # SQLite seulement
  uv run python examples/ai_storage_demo.py --txn     # focus transactions
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# ── Bootstrap sys.path ────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Modèles ───────────────────────────────────────────────────────────────────
from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.conversation import Conversation
from pyworkflow_engine.models.ai.execution import Execution, ExecutionStep
from pyworkflow_engine.models.ai.memory import AgentMemory
from pyworkflow_engine.models.ai.message import Message, TokenUsage
from pyworkflow_engine.models.ai.provider import LLMProviderConfig
from pyworkflow_engine.models.ai.skill import AgentSkillAssignment, Skill
from pyworkflow_engine.models.ai.tool import ToolDefinition
from pyworkflow_engine.models.ai.types import (
    AgentRole,
    AIStepType,
    ExecutionStatus,
    MemoryType,
    MessageRole,
    Proficiency,
    ProviderType,
    SkillCategory,
    ToolType,
)

# ── Backends ──────────────────────────────────────────────────────────────────
from pyworkflow_engine.adapters.ai.storage.memory import InMemoryAIStorage
from pyworkflow_engine.adapters.ai.storage.sqlite import SQLiteAIStorage
from pyworkflow_engine.ports.ai.storage import BaseAIStorage


# ── Utilitaires d'affichage ───────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
DIM = "\033[2m"


def section(title: str, color: str = CYAN) -> None:
    bar = "═" * 64
    print(f"\n{color}{BOLD}{bar}{RESET}")
    print(f"{color}{BOLD}  {title}{RESET}")
    print(f"{color}{BOLD}{bar}{RESET}")


def subsection(title: str) -> None:
    print(f"\n{BLUE}{BOLD}  ▶ {title}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET}  {msg}")


def info(msg: str) -> None:
    print(f"  {YELLOW}ℹ{RESET}  {msg}")


def row(label: str, value: Any) -> None:
    label_str = f"{label}:"
    print(f"    {DIM}{label_str:<30}{RESET} {value}")


def header_row(*cols: str, widths: tuple[int, ...] = ()) -> None:
    parts = [f"{c:<{w}}" if w else c for c, w in zip(cols, widths or (0,) * len(cols))]
    print(f"    {BOLD}{'  '.join(parts)}{RESET}")


# ── Scénario A : Bootstrap — Providers, Agents, Tools, Skills ─────────────────


def scenario_a_bootstrap(storage: BaseAIStorage) -> dict[str, Any]:
    """
    Crée le catalogue complet : providers, agents, tools, skills.
    Retourne les IDs créés pour les scénarios suivants.
    """
    section("A. Bootstrap — Providers · Agents · Tools · Skills")

    # ── Providers ──────────────────────────────────────────────────────────

    subsection("Providers LLM")

    openai_provider = LLMProviderConfig(
        name="OpenAI GPT-4o",
        provider_type=ProviderType.OPENAI,
        default_model="gpt-4o",
        description="Provider OpenAI — gpt-4o pour les tâches générales",
    )
    saved_provider = storage.save_provider(openai_provider)
    ok(f"Provider sauvegardé : {saved_provider.name!r}  (id={saved_provider.id[:8]}…)")

    anthropic_provider = LLMProviderConfig(
        name="Anthropic Claude 3",
        provider_type=ProviderType.ANTHROPIC,
        default_model="claude-3-5-sonnet-20241022",
        description="Provider Anthropic — Claude 3.5 pour le code et l'analyse",
    )
    storage.save_provider(anthropic_provider)
    ok(
        f"Provider sauvegardé : {anthropic_provider.name!r}  (id={anthropic_provider.id[:8]}…)"
    )

    # Lecture individuelle
    fetched = storage.get_provider(saved_provider.id)
    assert fetched is not None and fetched.name == "OpenAI GPT-4o"
    ok("get_provider() → objet correct")

    # Lecture par nom
    by_name = storage.get_provider_by_name("Anthropic Claude 3")
    assert by_name is not None
    ok(f"get_provider_by_name() → {by_name.provider_type.value}")

    all_providers = storage.list_providers()
    info(f"list_providers() → {len(all_providers)} provider(s) enregistré(s)")

    # ── Agents ─────────────────────────────────────────────────────────────

    subsection("Agents IA")

    research_agent = Agent(
        name="Research Assistant",
        slug="research-assistant",
        role=AgentRole.RESEARCHER,
        provider_id=openai_provider.id,
        system_prompt=(
            "Tu es un chercheur expert. Tu analyses des sujets complexes "
            "et fournis des synthèses factuelles et sourcées."
        ),
        config=AgentConfig(
            max_iterations=5,
            temperature=0.3,
            enable_memory=True,
            enable_tools=True,
        ),
        description="Agent de recherche documentaire",
        owner_id="user-demo-1",
    )
    storage.save_agent(research_agent)
    ok(f"Agent créé : {research_agent.name!r}  slug={research_agent.slug!r}")

    code_agent = Agent(
        name="Code Reviewer",
        slug="code-reviewer",
        role=AgentRole.CODER,
        provider_id=anthropic_provider.id,
        system_prompt=(
            "Tu es un expert en revue de code Python. Tu détectes les bugs, "
            "les problèmes de performance et les violations de style."
        ),
        config=AgentConfig(
            max_iterations=8,
            temperature=0.1,
            enable_memory=False,
            enable_tools=True,
        ),
        description="Agent de revue de code",
        owner_id="user-demo-1",
    )
    storage.save_agent(code_agent)
    ok(f"Agent créé : {code_agent.name!r}  slug={code_agent.slug!r}")

    orchestrator_agent = Agent(
        name="Pipeline Orchestrator",
        slug="pipeline-orchestrator",
        role=AgentRole.ORCHESTRATOR,
        provider_id=openai_provider.id,
        system_prompt="Tu coordonnes plusieurs agents spécialisés pour accomplir des tâches complexes.",
        is_active=False,  # désactivé — démonstration du filtre
    )
    storage.save_agent(orchestrator_agent)
    ok(f"Agent créé (inactif) : {orchestrator_agent.name!r}")

    # Lectures et filtres
    fetched_agent = storage.get_agent(research_agent.id)
    assert fetched_agent is not None
    ok(f"get_agent() → {fetched_agent.name!r} / role={fetched_agent.role.value}")

    by_slug = storage.get_agent_by_slug("code-reviewer")
    assert by_slug is not None
    ok(f"get_agent_by_slug('code-reviewer') → {by_slug.name!r}")

    active_agents = storage.list_agents(is_active=True)
    info(f"list_agents(is_active=True) → {len(active_agents)} agent(s)")

    researcher_agents = storage.list_agents(role=AgentRole.RESEARCHER)
    info(f"list_agents(role=RESEARCHER) → {len(researcher_agents)} agent(s)")

    # ── Tools ──────────────────────────────────────────────────────────────

    subsection("Tools (function-calling)")

    web_search_tool = ToolDefinition(
        key="web_search",
        name="Web Search",
        description="Recherche sur le web et retourne les résultats les plus pertinents.",
        tool_type=ToolType.API,
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Requête de recherche"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    )
    storage.save_tool(web_search_tool)
    ok(f"Tool enregistré : {web_search_tool.key!r}")

    code_exec_tool = ToolDefinition(
        key="code_executor",
        name="Code Executor",
        description="Exécute un snippet Python dans un environnement sandboxé.",
        tool_type=ToolType.FUNCTION,
        is_dangerous=True,
        requires_approval=True,
        parameters_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "timeout_sec": {"type": "integer", "default": 10},
            },
            "required": ["code"],
        },
    )
    storage.save_tool(code_exec_tool)
    ok(f"Tool enregistré : {code_exec_tool.key!r}  (dangereux, approbation requise)")

    db_query_tool = ToolDefinition(
        key="db_query",
        name="Database Query",
        description="Interroge la base de données SQL (lecture seule).",
        tool_type=ToolType.DATABASE,
        parameters_schema={
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
        is_active=False,
    )
    storage.save_tool(db_query_tool)
    ok(f"Tool enregistré (inactif) : {db_query_tool.key!r}")

    # Assigner les tools aux agents (tool_ids)
    research_agent.tool_ids = [web_search_tool.id]
    storage.save_agent(research_agent)

    code_agent.tool_ids = [code_exec_tool.id, db_query_tool.id]
    storage.save_agent(code_agent)

    tools_for_research = storage.list_tools_for_agent(research_agent.id)
    info(
        f"list_tools_for_agent(research) → {len(tools_for_research)} tool(s) : "
        + ", ".join(t.key for t in tools_for_research)
    )

    tools_for_code = storage.list_tools_for_agent(code_agent.id)
    info(
        f"list_tools_for_agent(code)     → {len(tools_for_code)} tool(s) : "
        + ", ".join(t.key for t in tools_for_code)
    )

    # function_schema OpenAI
    schema = web_search_tool.get_function_schema()
    ok(
        f"get_function_schema() → type={schema['type']!r}, name={schema['function']['name']!r}"
    )

    # ── Skills ─────────────────────────────────────────────────────────────

    subsection("Skills (compétences composites)")

    deep_research_skill = Skill(
        key="deep_research",
        name="Deep Research",
        category=SkillCategory.RESEARCH,
        description="Recherche approfondie multi-sources avec synthèse structurée.",
        system_prompt=(
            "Lorsque tu effectues une recherche, consulte au moins 3 sources "
            "distinctes et structure ta réponse avec des sections claires."
        ),
        required_tool_ids=[web_search_tool.id],
    )
    storage.save_skill(deep_research_skill)
    ok(
        f"Skill créé : {deep_research_skill.key!r}  (catégorie={deep_research_skill.category.value})"
    )

    code_review_skill = Skill(
        key="code_review",
        name="Code Review",
        category=SkillCategory.CODING,
        description="Revue de code Python avec détection de bugs et suggestions.",
        system_prompt="Analyse le code ligne par ligne. Signale tous les problèmes.",
        required_tool_ids=[code_exec_tool.id],
    )
    storage.save_skill(code_review_skill)
    ok(f"Skill créé : {code_review_skill.key!r}")

    # Assignments agent ↔ skill
    assignment_research = AgentSkillAssignment(
        agent_id=research_agent.id,
        skill_id=deep_research_skill.id,
        proficiency=Proficiency.EXPERT,
    )
    storage.save_skill_assignment(assignment_research)
    ok(
        f"Assignment : {research_agent.slug!r} ↔ {deep_research_skill.key!r} "
        f"(proficiency={assignment_research.proficiency.value})"
    )

    assignment_code = AgentSkillAssignment(
        agent_id=code_agent.id,
        skill_id=code_review_skill.id,
        proficiency=Proficiency.ADVANCED,
    )
    storage.save_skill_assignment(assignment_code)
    ok(
        f"Assignment : {code_agent.slug!r} ↔ {code_review_skill.key!r} "
        f"(proficiency={assignment_code.proficiency.value})"
    )

    # Bonus : assigner le skill de research à l'orchestrateur aussi
    assignment_orch = AgentSkillAssignment(
        agent_id=orchestrator_agent.id,
        skill_id=deep_research_skill.id,
        proficiency=Proficiency.INTERMEDIATE,
    )
    storage.save_skill_assignment(assignment_orch)

    assignments_for_research_agent = storage.list_skill_assignments_for_agent(
        research_agent.id
    )
    info(
        f"list_skill_assignments_for_agent(research) → "
        f"{len(assignments_for_research_agent)} assignment(s)"
    )

    return {
        "provider_openai_id": openai_provider.id,
        "provider_anthropic_id": anthropic_provider.id,
        "agent_research_id": research_agent.id,
        "agent_code_id": code_agent.id,
        "agent_orchestrator_id": orchestrator_agent.id,
        "tool_web_search_id": web_search_tool.id,
        "tool_code_exec_id": code_exec_tool.id,
        "skill_research_id": deep_research_skill.id,
        "skill_code_id": code_review_skill.id,
    }


# ── Scénario B : Conversation multi-turn ──────────────────────────────────────


def scenario_b_conversations(
    storage: BaseAIStorage,
    ids: dict[str, Any],
) -> dict[str, Any]:
    """
    Simule une conversation multi-turn entre un utilisateur et le Research Agent.
    Démontre save/get/list_conversations et save/get_messages.
    """
    section("B. Conversations multi-turn")

    agent_id = ids["agent_research_id"]

    # ── Conversation 1 — Recherche sur l'architecture hexagonale ──────────

    subsection("Conversation 1 — Recherche architecture hexagonale")

    conv1 = Conversation(
        agent_id=agent_id,
        title="Architecture hexagonale — explications",
        owner_id="user-demo-1",
    )
    storage.save_conversation(conv1)
    ok(f"Conversation créée : {conv1.title!r}  (id={conv1.id[:8]}…)")

    exchanges = [
        (MessageRole.USER, "Qu'est-ce que l'architecture hexagonale ?"),
        (
            MessageRole.ASSISTANT,
            "L'architecture hexagonale (ou Ports & Adapters) sépare le domaine métier "
            "des détails techniques. Le cœur de l'application expose des ports (interfaces) "
            "que des adapters implémentent concrètement.",
        ),
        (MessageRole.USER, "Quels sont les avantages principaux ?"),
        (
            MessageRole.ASSISTANT,
            "Les 3 avantages clés sont : 1) testabilité (on peut mocker n'importe quel port), "
            "2) interchangeabilité des adapters (SQLite ↔ PostgreSQL sans changer le domaine), "
            "3) clarté architecturale (dépendances toujours dirigées vers le centre).",
        ),
        (MessageRole.USER, "Comment cela s'applique à pyworkflow-engine ?"),
        (
            MessageRole.ASSISTANT,
            "Dans pyworkflow-engine, BaseAIStorage est le port. InMemoryAIStorage et "
            "SQLiteAIStorage sont deux adapters interchangeables. AgentService ne connaît "
            "que le port — il fonctionne identiquement quel que soit le backend.",
        ),
    ]

    messages_conv1 = []
    for role, content in exchanges:
        msg = Message(
            conversation_id=conv1.id,
            role=role,
            content=content,
            token_usage=(
                TokenUsage(
                    prompt_tokens=len(content.split()) * 2,
                    completion_tokens=len(content.split()),
                    total_tokens=len(content.split()) * 3,
                )
                if role == MessageRole.ASSISTANT
                else None
            ),
        )
        storage.save_message(msg)
        messages_conv1.append(msg)

    ok(f"{len(exchanges)} messages persistés dans la conversation 1")

    # Relecture
    retrieved = storage.get_messages(conv1.id)
    assert len(retrieved) == len(
        exchanges
    ), f"Expected {len(exchanges)}, got {len(retrieved)}"
    ok(f"get_messages() → {len(retrieved)} messages relus en ordre chronologique")

    # Pagination
    page1 = storage.get_messages(conv1.id, limit=2, offset=0)
    page2 = storage.get_messages(conv1.id, limit=2, offset=2)
    info(f"Pagination : page1={len(page1)} msgs, page2={len(page2)} msgs")

    # count_messages
    count = storage.count_messages(conv1.id)
    assert count == len(exchanges)
    ok(f"count_messages() → {count}")

    # ── Conversation 2 — Autre utilisateur ────────────────────────────────

    subsection("Conversation 2 — Autre utilisateur")

    conv2 = Conversation(
        agent_id=agent_id,
        title="Microservices vs Monolithe",
        owner_id="user-demo-2",
    )
    storage.save_conversation(conv2)

    msg_u = Message(
        conversation_id=conv2.id,
        role=MessageRole.USER,
        content="Microservices ou monolithe, que choisir pour un MVP ?",
    )
    msg_a = Message(
        conversation_id=conv2.id,
        role=MessageRole.ASSISTANT,
        content="Pour un MVP : monolithe. Simpler à déployer, debugger et faire évoluer. "
        "Migrez vers les microservices uniquement si la charge ou les équipes le justifient.",
    )
    storage.save_message(msg_u)
    storage.save_message(msg_a)
    ok("Conversation 2 créée avec 2 messages")

    # Filtres
    all_convs = storage.list_conversations()
    convs_agent = storage.list_conversations(agent_id=agent_id)
    convs_user1 = storage.list_conversations(owner_id="user-demo-1")
    convs_user2 = storage.list_conversations(owner_id="user-demo-2")

    info(f"list_conversations()                       → {len(all_convs)} total")
    info(f"list_conversations(agent_id=research)      → {len(convs_agent)}")
    info(f"list_conversations(owner_id='user-demo-1') → {len(convs_user1)}")
    info(f"list_conversations(owner_id='user-demo-2') → {len(convs_user2)}")

    # Vérification de cohérence
    assert len(convs_user1) == 1
    assert len(convs_user2) == 1
    ok("Filtres owner_id cohérents ✓")

    return {
        "conv1_id": conv1.id,
        "conv2_id": conv2.id,
        "msg_ids_conv1": [m.id for m in messages_conv1],
    }


# ── Scénario C : Execution tracking ───────────────────────────────────────────


def scenario_c_executions(
    storage: BaseAIStorage,
    ids: dict[str, Any],
) -> dict[str, Any]:
    """
    Trace une exécution IA complète :
      PENDING → RUNNING → SUCCESS
    avec des étapes détaillées (LLM call → tool call → tool result).
    """
    section("C. Execution Tracking (runs + steps)")

    agent_id = ids["agent_research_id"]
    tool_id = ids["tool_web_search_id"]

    subsection("Exécution 1 — One-shot avec tool calling")

    # Créer l'exécution (état initial PENDING)
    execution = Execution(
        agent_id=agent_id,
        status=ExecutionStatus.PENDING,
        input_data={
            "prompt": "Quelles sont les dernières avancées en quantum computing ?"
        },
        metadata={"source": "demo", "version": "1.0"},
    )
    storage.save_execution(execution)
    ok(f"Execution créée : {execution.id[:8]}…  status={execution.status.value}")

    # Transition PENDING → RUNNING
    execution.status = ExecutionStatus.RUNNING
    execution.started_at = datetime.now(UTC)
    execution.updated_at = datetime.now(UTC)
    storage.save_execution(execution)
    ok(f"Transition → {execution.status.value}")

    # Étape 1 : LLM Call
    step1 = ExecutionStep(
        execution_id=execution.id,
        step_type=AIStepType.LLM_CALL,
        order=1,
        agent_id=agent_id,
        input_data={
            "messages": [{"role": "user", "content": execution.input_data["prompt"]}]
        },
        output_data={"content": "Je vais chercher les informations…", "tool_calls": 1},
        tokens_used=512,
        cost=0.0015,
        duration_ms=843,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    storage.save_execution_step(step1)
    ok(
        f"  Step 1 : {step1.step_type.value}  tokens={step1.tokens_used}  cost=${step1.cost:.4f}"
    )

    # Étape 2 : Tool Call
    step2 = ExecutionStep(
        execution_id=execution.id,
        step_type=AIStepType.TOOL_CALL,
        order=2,
        agent_id=agent_id,
        tool_id=tool_id,
        input_data={"query": "quantum computing breakthroughs 2025", "max_results": 5},
        output_data={},  # résultat attendu
        duration_ms=1240,
        started_at=datetime.now(UTC),
    )
    storage.save_execution_step(step2)
    ok(f"  Step 2 : {step2.step_type.value}  tool={tool_id[:8]}…")

    # Étape 3 : Tool Result
    step3 = ExecutionStep(
        execution_id=execution.id,
        step_type=AIStepType.TOOL_RESULT,
        order=3,
        agent_id=agent_id,
        tool_id=tool_id,
        input_data={},
        output_data={
            "results": [
                {
                    "title": "Quantum Error Correction Milestone",
                    "url": "https://example.com/1",
                },
                {
                    "title": "IBM Heron 133-qubit Processor",
                    "url": "https://example.com/2",
                },
            ]
        },
        duration_ms=0,
        completed_at=datetime.now(UTC),
    )
    storage.save_execution_step(step3)
    ok(
        f"  Step 3 : {step3.step_type.value}  ({len(step3.output_data['results'])} résultats)"
    )

    # Étape 4 : LLM Call final (synthèse)
    step4 = ExecutionStep(
        execution_id=execution.id,
        step_type=AIStepType.LLM_CALL,
        order=4,
        agent_id=agent_id,
        input_data={"messages_count": 3},
        output_data={
            "content": (
                "Les avancées majeures en quantum computing en 2025 incluent : "
                "1) IBM a déployé son processeur Heron à 133 qubits, "
                "2) Google a démontré la correction d'erreurs quantiques à grande échelle…"
            )
        },
        tokens_used=1024,
        cost=0.0031,
        duration_ms=1876,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    storage.save_execution_step(step4)
    ok(
        f"  Step 4 : {step4.step_type.value} (synthèse)  "
        f"tokens={step4.tokens_used}  cost=${step4.cost:.4f}"
    )

    # Transition RUNNING → SUCCESS
    execution.status = ExecutionStatus.SUCCESS
    execution.completed_at = datetime.now(UTC)
    execution.total_steps = 4
    execution.output_data = {"answer": step4.output_data["content"][:80] + "…"}
    execution.updated_at = datetime.now(UTC)
    storage.save_execution(execution)
    ok(f"Transition → {execution.status.value}  total_steps={execution.total_steps}")

    # Récupération et vérification
    steps = storage.get_execution_steps(execution.id)
    assert len(steps) == 4
    assert [s.order for s in steps] == [1, 2, 3, 4], "Étapes mal triées"
    ok(f"get_execution_steps() → {len(steps)} étapes (triées par order ✓)")

    # Exécution 2 — échouée (pour démontrer les filtres)
    subsection("Exécution 2 — Échec (démonstration filtres)")

    exec_failed = Execution(
        agent_id=agent_id,
        status=ExecutionStatus.FAILED,
        input_data={"prompt": "Tâche impossible"},
        error="TimeoutError: LLM did not respond within 30s",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    storage.save_execution(exec_failed)
    ok(f"Execution échouée : {exec_failed.id[:8]}…  error={exec_failed.error[:40]!r}")

    # Filtres
    all_execs = storage.list_executions()
    by_agent = storage.list_executions(agent_id=agent_id)
    by_success = storage.list_executions(status=ExecutionStatus.SUCCESS)
    by_failed = storage.list_executions(status=ExecutionStatus.FAILED)

    info(f"list_executions()                         → {len(all_execs)} total")
    info(f"list_executions(agent_id=research)        → {len(by_agent)}")
    info(f"list_executions(status=SUCCESS)           → {len(by_success)}")
    info(f"list_executions(status=FAILED)            → {len(by_failed)}")

    assert len(by_success) == 1
    assert len(by_failed) == 1
    ok("Filtres status cohérents ✓")

    return {"exec_success_id": execution.id, "exec_failed_id": exec_failed.id}


# ── Scénario D : Mémoire persistante ──────────────────────────────────────────


def scenario_d_memory(
    storage: BaseAIStorage,
    ids: dict[str, Any],
) -> None:
    """
    Démontre le stockage de mémoires inter-sessions :
      - mémoires long-term / episodic
      - filtrage par type
      - expiration automatique
    """
    section("D. Mémoire persistante inter-sessions")

    agent_id = ids["agent_research_id"]

    subsection("Écriture des mémoires")

    mem_lang = AgentMemory(
        agent_id=agent_id,
        key="user_language",
        content="Cet utilisateur préfère les réponses en français, avec un ton formel.",
        memory_type=MemoryType.LONG_TERM,
        relevance_score=0.95,
    )
    storage.save_memory(mem_lang)
    ok(f"Mémoire LONG_TERM : {mem_lang.key!r}  score={mem_lang.relevance_score}")

    mem_style = AgentMemory(
        agent_id=agent_id,
        key="response_style",
        content="L'utilisateur aime les réponses structurées avec des listes numérotées.",
        memory_type=MemoryType.LONG_TERM,
        relevance_score=0.82,
    )
    storage.save_memory(mem_style)
    ok(f"Mémoire LONG_TERM : {mem_style.key!r}  score={mem_style.relevance_score}")

    mem_episode = AgentMemory(
        agent_id=agent_id,
        key="session_2026_04_12",
        content="L'utilisateur a demandé des recherches sur quantum computing et l'architecture hexagonale.",
        memory_type=MemoryType.EPISODIC,
        relevance_score=0.70,
    )
    storage.save_memory(mem_episode)
    ok(f"Mémoire EPISODIC  : {mem_episode.key!r}")

    # Mémoire temporaire (expire dans 1 heure)
    mem_temp = AgentMemory(
        agent_id=agent_id,
        key="current_session_topic",
        content="Topic actuel : avancées technologiques IA 2025.",
        memory_type=MemoryType.SHORT_TERM,
        relevance_score=0.60,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    storage.save_memory(mem_temp)
    ok(f"Mémoire SHORT_TERM (expire dans 1h) : {mem_temp.key!r}")

    # Mémoire déjà expirée
    mem_expired = AgentMemory(
        agent_id=agent_id,
        key="old_session_topic",
        content="Topic expiré.",
        memory_type=MemoryType.SHORT_TERM,
        relevance_score=0.10,
        expires_at=datetime.now(UTC) - timedelta(hours=24),  # dans le passé
    )
    storage.save_memory(mem_expired)
    ok(f"Mémoire SHORT_TERM expirée : {mem_expired.key!r}")

    subsection("Lecture et filtrage")

    # Lecture individuelle
    fetched = storage.get_memory(agent_id, "user_language")
    assert fetched is not None and fetched.content == mem_lang.content
    ok(f"get_memory(agent_id, 'user_language') → {fetched.content[:50]!r}…")

    # Liste toutes
    all_mems = storage.list_memories(agent_id)
    info(f"list_memories(agent_id) → {len(all_mems)} mémoires au total")

    # Filtre par type
    long_term = storage.list_memories(agent_id, memory_type=MemoryType.LONG_TERM)
    episodic = storage.list_memories(agent_id, memory_type=MemoryType.EPISODIC)
    short_term = storage.list_memories(agent_id, memory_type=MemoryType.SHORT_TERM)

    info(f"  LONG_TERM  : {len(long_term)}")
    info(f"  EPISODIC   : {len(episodic)}")
    info(f"  SHORT_TERM : {len(short_term)}")

    # Vérification expiration (propriété calculée)
    expired_count = sum(1 for m in all_mems if m.is_expired)
    active_count = sum(1 for m in all_mems if not m.is_expired)
    info(f"  Actives : {active_count}  |  Expirées : {expired_count}")
    assert expired_count == 1
    ok("Détection d'expiration (is_expired) ✓")

    # Nettoyage des expirées
    deleted = storage.delete_expired_memories()
    ok(f"delete_expired_memories() → {deleted} mémoire(s) supprimée(s)")

    after_cleanup = storage.list_memories(agent_id)
    assert len(after_cleanup) == len(all_mems) - deleted
    ok(f"Après nettoyage : {len(after_cleanup)} mémoire(s) restante(s)")

    # Mise à jour d'une mémoire (upsert)
    subsection("Mise à jour (upsert)")

    mem_lang_updated = AgentMemory(
        id=mem_lang.id,  # même ID → update
        agent_id=agent_id,
        key="user_language",
        content="Cet utilisateur préfère le français. Il apprécie aussi les exemples concrets.",
        memory_type=MemoryType.LONG_TERM,
        relevance_score=0.97,
    )
    storage.save_memory(mem_lang_updated)
    ok("Mémoire mise à jour via save_memory (upsert par ID)")

    fetched_updated = storage.get_memory(agent_id, "user_language")
    assert fetched_updated is not None
    assert "exemples concrets" in fetched_updated.content
    ok(f"Mémoire mise à jour vérifiée : score={fetched_updated.relevance_score}")


# ── Scénario E : Transactions atomiques ───────────────────────────────────────


def scenario_e_transactions(storage: BaseAIStorage, ids: dict[str, Any]) -> None:
    """
    Démontre les transactions atomiques.

    - SQLiteAIStorage : transaction() garantit l'atomicité — rollback réel sur exception.
    - InMemoryAIStorage : transaction() est un no-op documenté (BaseAIStorage.transaction
      ne fait que `yield`). Les writes sont immédiatement visibles et ne sont pas annulés.
      Ce comportement est intentionnel : les tests unitaires utilisent InMemory sans avoir
      besoin de transactions.
    """
    section("E. Transactions atomiques")

    is_sqlite = isinstance(storage, SQLiteAIStorage)
    agent_id = ids["agent_research_id"]

    # ── Commit ────────────────────────────────────────────────────────────────

    subsection("Transaction commit (succès)")

    conv_before = storage.list_conversations(agent_id=agent_id)

    with storage.transaction():
        txn_conv1 = Conversation(
            agent_id=agent_id,
            title="Conversation transactionnelle 1",
        )
        txn_conv2 = Conversation(
            agent_id=agent_id,
            title="Conversation transactionnelle 2",
        )
        storage.save_conversation(txn_conv1)
        storage.save_conversation(txn_conv2)

    conv_after = storage.list_conversations(agent_id=agent_id)
    assert len(conv_after) == len(conv_before) + 2
    ok(f"Commit : +2 conversations ({len(conv_before)} → {len(conv_after)})")

    # ── Rollback ──────────────────────────────────────────────────────────────

    subsection("Transaction rollback (exception)")

    if not is_sqlite:
        # InMemoryAIStorage : transaction() est un no-op par conception.
        # Les écritures sont immédiates et ne sont pas annulées en cas d'exception.
        # C'est le comportement attendu et documenté — pas un bug.
        info(
            f"{type(storage).__name__}.transaction() est un no-op (BaseAIStorage par défaut)."
        )
        info(
            "Les écritures à l'intérieur du bloc sont immédiatement persistées en mémoire."
        )
        info(
            "Le rollback sur exception n'est garanti que pour SQLiteAIStorage "
            "(qui surcharge transaction() avec BEGIN/COMMIT/ROLLBACK)."
        )
        info(
            "→ Scénario rollback ignoré pour InMemoryAIStorage  [comportement attendu]"
        )
        return

    # SQLiteAIStorage : rollback réel attendu
    conv_before_rollback = storage.list_conversations(agent_id=agent_id)

    try:
        with storage.transaction():
            doomed_conv = Conversation(
                agent_id=agent_id,
                title="Cette conversation ne doit pas être persistée",
            )
            storage.save_conversation(doomed_conv)
            raise ValueError("Erreur simulée — rollback attendu")
    except ValueError:
        pass  # attendu

    conv_after_rollback = storage.list_conversations(agent_id=agent_id)
    assert len(conv_after_rollback) == len(conv_before_rollback), (
        f"Rollback échoué : attendu {len(conv_before_rollback)}, "
        f"obtenu {len(conv_after_rollback)}"
    )
    ok(
        f"Rollback : aucune conversation ajoutée "
        f"({len(conv_after_rollback)} inchangé ✓)"
    )


# ── Scénario F : Lecture croisée depuis disque ────────────────────────────────


def scenario_f_reload_from_disk(db_path: str, ids: dict[str, Any]) -> None:
    """
    Ouvre une nouvelle instance SQLiteAIStorage sur le même fichier,
    et vérifie que toutes les données sont bien présentes (durabilité).
    """
    section("F. Durabilité — Relecture depuis disque (nouvelle instance)")

    with SQLiteAIStorage(db_path) as fresh:
        providers = fresh.list_providers()
        agents = fresh.list_agents()
        tools = fresh.list_tools()
        skills = fresh.list_skills()
        executions = fresh.list_executions()
        convs = fresh.list_conversations()

        row("Providers relus", len(providers))
        row("Agents relus", len(agents))
        row("Tools relus", len(tools))
        row("Skills relus", len(skills))
        row("Executions relues", len(executions))
        row("Conversations relues", len(convs))

        assert len(providers) >= 2, "Providers manquants après rechargement"
        assert len(agents) >= 3, "Agents manquants après rechargement"
        ok("Toutes les entités persistent entre redémarrages ✓")

        # Vérification de la récupération par ID
        research_agent = fresh.get_agent(ids["agent_research_id"])
        assert research_agent is not None
        ok(f"Agent relu par ID : {research_agent.name!r}  slug={research_agent.slug!r}")

        # Vérification des steps d'exécution
        steps = fresh.get_execution_steps(ids["exec_success_id"])
        assert len(steps) == 4
        ok(f"Steps d'exécution relus : {len(steps)} (ordre conservé ✓)")


# ── Scénario G : Nettoyage ────────────────────────────────────────────────────


def scenario_g_cleanup(storage: BaseAIStorage, ids: dict[str, Any]) -> None:
    """
    Démonstration des opérations de suppression.
    """
    section("G. Nettoyage — Delete operations")

    subsection("Suppression d'entités")

    # Supprimer un provider
    deleted = storage.delete_provider(ids["provider_anthropic_id"])
    ok(f"delete_provider(anthropic) → {deleted}")

    remaining = storage.list_providers()
    info(f"Providers restants : {len(remaining)}")

    # Supprimer un agent inactif
    deleted_agent = storage.delete_agent(ids["agent_orchestrator_id"])
    ok(f"delete_agent(orchestrator) → {deleted_agent}")

    remaining_agents = storage.list_agents()
    info(f"Agents restants : {len(remaining_agents)}")

    # Suppression d'un ID inexistant → False
    not_found = storage.delete_agent("does-not-exist-uuid")
    assert not_found is False
    ok(f"delete_agent('does-not-exist') → {not_found}  (comportement attendu)")

    # Supprimer un skill
    deleted_skill = storage.delete_skill(ids["skill_code_id"])
    ok(f"delete_skill(code_review) → {deleted_skill}")

    remaining_skills = storage.list_skills()
    info(f"Skills restants : {len(remaining_skills)}")


# ── Runner principal ───────────────────────────────────────────────────────────


def run_demo(
    storage: BaseAIStorage, backend_name: str, with_disk_reload: str | None = None
) -> None:
    """Exécute tous les scénarios sur un backend donné."""

    print(f"\n{MAGENTA}{BOLD}{'━' * 64}{RESET}")
    print(f"{MAGENTA}{BOLD}  Backend : {backend_name}{RESET}")
    print(f"{MAGENTA}{BOLD}{'━' * 64}{RESET}")

    ids = scenario_a_bootstrap(storage)
    conv_ids = scenario_b_conversations(storage, ids)
    exec_ids = scenario_c_executions(storage, ids)
    ids.update(conv_ids)
    ids.update(exec_ids)

    scenario_d_memory(storage, ids)
    scenario_e_transactions(storage, ids)

    if with_disk_reload:
        scenario_f_reload_from_disk(with_disk_reload, ids)

    scenario_g_cleanup(storage, ids)

    print(
        f"\n{GREEN}{BOLD}  ✓ Tous les scénarios terminés avec succès — {backend_name}{RESET}\n"
    )


def run_inmemory() -> None:
    section("DÉMONSTRATION — InMemoryAIStorage", color=MAGENTA)
    info("Backend volatile : zéro configuration, parfait pour les tests unitaires.")
    info("Toutes les données sont perdues à la fermeture de l'instance.\n")

    with InMemoryAIStorage() as storage:
        run_demo(storage, backend_name="InMemoryAIStorage")


def run_sqlite() -> None:
    section("DÉMONSTRATION — SQLiteAIStorage", color=MAGENTA)
    info("Backend durable : fichier SQLite, production-ready avec WAL mode.")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    info(f"Fichier temporaire : {db_path}\n")

    with SQLiteAIStorage(db_path) as storage:
        run_demo(
            storage,
            backend_name=f"SQLiteAIStorage ({Path(db_path).name})",
            with_disk_reload=db_path,
        )

    # Nettoyage du fichier temporaire
    try:
        Path(db_path).unlink(missing_ok=True)
        for suffix in ("-shm", "-wal"):
            Path(db_path + suffix).unlink(missing_ok=True)
    except OSError:
        pass

    ok(f"Fichier temporaire supprimé : {Path(db_path).name}")


def run_transaction_focus() -> None:
    """Focus uniquement sur les transactions."""
    section("FOCUS — Transactions atomiques SQLiteAIStorage", color=MAGENTA)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with SQLiteAIStorage(db_path) as storage:
        ids = scenario_a_bootstrap(storage)
        scenario_e_transactions(storage, ids)

    try:
        Path(db_path).unlink(missing_ok=True)
        for suffix in ("-shm", "-wal"):
            Path(db_path + suffix).unlink(missing_ok=True)
    except OSError:
        pass

    ok("Démonstration transactions terminée.")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Démo complète du sous-système AI Storage (ADR-020/ADR-021)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--memory",
        action="store_true",
        help="InMemoryAIStorage uniquement",
    )
    group.add_argument(
        "--sqlite",
        action="store_true",
        help="SQLiteAIStorage uniquement",
    )
    group.add_argument(
        "--txn",
        action="store_true",
        help="Focus sur les transactions atomiques (SQLite)",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 64}{RESET}")
    print(f"{BOLD}  pyworkflow-engine — AI Storage Demo{RESET}")
    print(f"{BOLD}  ADR-020 (agent framework) · ADR-021 (industry positioning){RESET}")
    print(f"{BOLD}{'═' * 64}{RESET}")
    print(f"  {DIM}Architecture hexagonale : BaseAIStorage (port){RESET}")
    print(f"  {DIM}Backends : InMemoryAIStorage · SQLiteAIStorage (adapters){RESET}")
    print(f"  {DIM}Entités  : Provider · Agent · Tool · Skill ·{RESET}")
    print(f"  {DIM}           Conversation · Message · Execution · Memory{RESET}")

    if args.memory:
        run_inmemory()
    elif args.sqlite:
        run_sqlite()
    elif args.txn:
        run_transaction_focus()
    else:
        # Démo complète : les deux backends
        run_inmemory()
        run_sqlite()

    print(f"\n{BOLD}{'═' * 64}{RESET}")
    print(f"{GREEN}{BOLD}  DÉMONSTRATION COMPLÈTE TERMINÉE ✓{RESET}")
    print(f"{BOLD}{'═' * 64}{RESET}\n")


if __name__ == "__main__":
    main()
