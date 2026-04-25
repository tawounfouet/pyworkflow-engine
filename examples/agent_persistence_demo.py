#!/usr/bin/env python3
"""
Exemple — Persistance et logs des agents IA dans workflow.db.

Démontre end-to-end comment chaque interaction agent est :
  1. **Tracée dans les logs** (``logs/pyworkflow.log`` + ``workflow_logs`` SQLite)
  2. **Persistée en base** (``ai_conversations`` + ``ai_messages`` + ``ai_memories``)
  3. **Consultable** depuis la CLI ou via ``SQLiteAIStorage``

Scénarios illustrés :
  A. One-shot simple          — 1 question → 1 réponse → 1 conversation en base
  B. Multi-turn tracé         — conversation à 3 tours, tout historisé
  C. Multi-agents             — 3 agents, conversations séparées, métriques agrégées
  D. Lecture de l'historique  — requêtes sur ai_conversations / ai_messages
  E. Gestion d'erreur         — conversation marquée "error" si la clé API est absente

Architecture :
  AgentRunner ──► SQLiteAIStorage ──► workflow.db (ai_conversations + ai_messages + ai_memories)
              └──► get_logger("agents.runner") ──► pyworkflow.log

Prérequis :
  pip install "pyworkflow-engine[ai]"   # ou : pip install openai
  OPENAI_API_KEY défini dans .env ou l'environnement

Usage :
  python examples/agent_persistence_demo.py          # tous les scénarios
  python examples/agent_persistence_demo.py --read   # lecture historique seul
  python examples/agent_persistence_demo.py --multi  # multi-agents seulement

Équivalent CLI :
  pyworkflow agent run general-assistant "Bonjour" -v
  pyworkflow agent history --messages
  pyworkflow agent sync --show
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Bootstrap sys.path (identique à agent_chat.py) ───────────────────────────
_ROOT = Path(__file__).resolve().parents[1]
if (_ROOT / "agents" / "manifest.yaml").exists() and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Charger .env si disponible
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ── Activer logging fichier + SQLite (même pattern que la CLI) ────────────────
try:
    from jobs.shared.logging import configure_platform_logging

    configure_platform_logging()
except Exception:
    pass


# ── Helpers d'affichage ───────────────────────────────────────────────────────

SEP = "─" * 60


def section(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def ok(msg: str) -> None:
    print(f"  ✅  {msg}")


def info(msg: str) -> None:
    print(f"  ℹ️   {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠️   {msg}")


def row(label: str, value: object) -> None:
    print(f"  {label:<28} {value}")


# ── Storage helper ────────────────────────────────────────────────────────────


def _get_storage():
    """Instancie un SQLiteAIStorage pour lecture."""
    from pyworkflow_engine.adapters.ai.storage.sqlite import SQLiteAIStorage

    db_path = os.environ.get("PYWORKFLOW_DB", "workflow.db")
    return SQLiteAIStorage(Path(db_path).expanduser().resolve())


# ── Scénario A : One-shot avec persistance ────────────────────────────────────


def scenario_a_oneshot() -> None:
    """A. Un seul échange — vérifier que la conversation est bien persistée."""
    section("A. One-shot — persistance automatique")

    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner

    runner = AgentRunner(general_assistant, model="gpt-4o-mini", verbose=True)
    info(f"Runner créé — modèle : {runner.model}")
    info(f"Persistance active : {runner.storage is not None}")

    response = runner.ask("Dis-moi en une phrase ce qu'est un data pipeline.")

    print(f"\n  🤖 {response.content}")
    if response.usage:
        row("Tokens :", response.usage.total_tokens)
    if response.response_time_ms:
        row("Temps :", f"{response.response_time_ms:.0f}ms")

    runner.finish()

    # Vérifier en base
    storage = _get_storage()
    convs = storage.list_conversations(agent_id=runner.agent.id)
    if convs:
        c = convs[-1]
        ok(f"Conversation persistée — conv_id: {c.id[:8]}…")
        row("  status :", c.status.value)
        row("  messages :", c.message_count)
        row("  total_tokens :", c.total_tokens)
    else:
        warn("Aucune conversation trouvée en base (vérifiez workflow.db)")


# ── Scénario B : Multi-turn tracé ─────────────────────────────────────────────


def scenario_b_multiturn() -> None:
    """B. Conversation multi-tours — chaque message tracé dans ai_messages."""
    section("B. Multi-turn — historique complet en base")

    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner

    runner = AgentRunner(general_assistant, model="gpt-4o-mini")

    questions = [
        "Quel langage est le plus utilisé en data engineering ?",
        "Quels sont ses 3 principaux avantages dans ce contexte ?",
        "Et son principal inconvénient ?",
    ]

    print()
    for i, q in enumerate(questions, 1):
        print(f"  👤 [{i}] {q}")
        resp = runner.ask(q)
        print(
            f"  🤖     → {resp.content[:120]}{'…' if len(resp.content) > 120 else ''}"
        )
        if resp.usage:
            print(f"         ({resp.usage.total_tokens} tokens)\n")

    conv_id = runner.conversation_id
    runner.finish()

    # Inspecter les messages en base
    if conv_id:
        storage = _get_storage()
        msgs = storage.get_messages(conv_id)
        ok(f"Conversation {conv_id[:8]}… — {len(msgs)} messages persistés")
        print()
        for m in msgs:
            if m.role.value == "system":
                continue
            role_label = "👤 User     " if m.role.value == "user" else "🤖 Assistant"
            preview = m.content[:80] + ("…" if len(m.content) > 80 else "")
            print(f"    {role_label}  {preview}")


# ── Scénario C : Multi-agents ─────────────────────────────────────────────────


def scenario_c_multi_agents() -> None:
    """C. 3 agents différents — conversations séparées, métriques par agent."""
    section("C. Multi-agents — conversations distinctes par agent")

    from agents.assistants.general_assistant import general_assistant
    from agents.coders.code_reviewer import code_reviewer
    from agents.analysts.data_analyst import data_analyst
    from agents.shared.runner import AgentRunner

    tasks = [
        (general_assistant, "Explique le concept de ETL en 2 phrases."),
        (code_reviewer, "Review: `df.fillna(0, inplace=True)` — bonne pratique ?"),
        (
            data_analyst,
            "Quelle est la différence entre COUNT(*) et COUNT(col) en SQL ?",
        ),
    ]

    print()
    for agent, question in tasks:
        runner = AgentRunner(agent, model="gpt-4o-mini")
        print(f"  🤖 [{agent.role.value:>12}] {agent.name}")
        print(f"     Q: {question[:70]}")
        resp = runner.ask(question)
        runner.finish()
        tok = resp.usage.total_tokens if resp.usage else "?"
        ms = f"{resp.response_time_ms:.0f}ms" if resp.response_time_ms else "?"
        print(f"     A: {resp.content[:80]}{'…' if len(resp.content) > 80 else ''}")
        print(f"     ⚡ {tok} tokens — {ms}\n")


# ── Scénario D : Lecture de l'historique ──────────────────────────────────────


def scenario_d_read_history() -> None:
    """D. Lecture de l'historique — requêtes directes via SQLiteAIStorage."""
    section("D. Lecture de l'historique persisté")

    try:
        storage = _get_storage()
    except Exception:
        warn("workflow.db introuvable. Lancez d'abord les scénarios A-C.")
        return

    conversations = storage.list_conversations()
    conversations.sort(key=lambda c: c.created_at, reverse=True)
    conversations = conversations[:20]

    print(f"\n  📋 {len(conversations)} conversation(s) dans ai_conversations\n")

    print(
        f"  {'Conv ID':>10}  {'Agent':<20}  {'Status':>12}  "
        f"{'Msgs':>4}  {'Tokens':>6}  {'Créé le'}"
    )
    print(f"  {SEP}")

    for c in conversations:
        conv_id = c.id[:8]
        agent_slug = "—"
        if c.agent_id:
            ag = storage.get_agent(c.agent_id)
            if ag:
                agent_slug = ag.slug
        try:
            created = c.created_at.strftime("%d/%m %H:%M")
        except (ValueError, AttributeError):
            created = str(c.created_at)[:16]

        status_icon = {
            "completed": "✅", "archived": "📦", "active": "⏳"
        }.get(c.status.value, "?")
        print(
            f"  {conv_id:>10}  {agent_slug:<20}  "
            f"{status_icon} {c.status.value:>8}  {c.message_count or 0:>4}  "
            f"{c.total_tokens or 0:>6}  {created}"
        )

    # Messages du dernier
    if conversations:
        last = conversations[0]
        msgs = storage.get_messages(last.id)
        user_assistant = [
            m for m in msgs if m.role.value in ("user", "assistant")
        ]
        print(f"\n  📨 Messages de la dernière conversation ({last.id[:8]}…) :\n")
        for m in user_assistant:
            role_icon = "👤" if m.role.value == "user" else "🤖"
            preview = m.content[:100] + ("…" if len(m.content) > 100 else "")
            print(f"    {role_icon} {m.role.value.upper():<10}  {preview}")

    # Agents persistés
    all_agents = storage.list_agents()
    print(f"\n  🤖 {len(all_agents)} agent(s) dans ai_agents :")
    for a in all_agents:
        active = "✅" if a.is_active else "❌"
        print(f"    {active}  {a.slug:<22} [{a.role.value:<12}]  {a.name}")


# ── Scénario E : Gestion d'erreur ─────────────────────────────────────────────


def scenario_e_error_handling() -> None:
    """E. Conversation marquée 'error' en base quand le LLM échoue."""
    section("E. Gestion d'erreur — conversation persistée avec status=error")

    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner, AgentRunnerError

    try:
        runner = AgentRunner(general_assistant, api_key="sk-invalid-key-for-demo")
        runner.ask("Ceci va échouer.")
        runner.finish()
    except AgentRunnerError as exc:
        warn(f"Erreur capturée (attendue) : {str(exc)[:80]}")

    info("Erreur intervenue — vérifiez l'historique avec --read.")


# ── Point d'entrée ────────────────────────────────────────────────────────────


def main() -> None:
    has_key = bool(
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("PYWORKFLOW_AI_OPENAI_API_KEY")
    )

    args = set(sys.argv[1:])

    if "--read" in args:
        scenario_d_read_history()
        return

    if not has_key:
        print(
            "⚠️  OPENAI_API_KEY manquante — seule la lecture d'historique est possible."
        )
        print("   Lancez avec --read pour consulter les conversations précédentes.")
        print("   Ou : export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    if "--multi" in args:
        scenario_c_multi_agents()
        scenario_d_read_history()
        return

    if "--error" in args:
        scenario_e_error_handling()
        return

    scenario_a_oneshot()
    scenario_b_multiturn()
    scenario_c_multi_agents()
    scenario_d_read_history()

    section("Récapitulatif")
    print(
        """
  workflow.db contient maintenant :
    ┌─────────────────────────┬──────────────────────────────────────────┐
    │ ai_agents               │ agents synchronisés (agent sync)         │
    │ ai_providers            │ providers auto-créés                     │
    │ ai_conversations        │ N conversations (one-shot + multi-turn)  │
    │ ai_messages             │ N×2 messages (user + assistant)          │
    │ ai_memories             │ faits extraits (si enable_memory=True)   │
    │ workflow_logs           │ logs structurés                          │
    └─────────────────────────┴──────────────────────────────────────────┘

  Commandes CLI utiles :
    pyworkflow agent history              # liste les conversations
    pyworkflow agent history --messages   # avec détail des messages
    pyworkflow agent sync --show          # état de ai_agents
    pyworkflow agent run general-assistant "Bonjour" -v
"""
    )


if __name__ == "__main__":
    main()
