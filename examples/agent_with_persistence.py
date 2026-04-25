#!/usr/bin/env python3
"""
Exemple — Agent réel avec persistence DB + logging structuré.

Démontre l'intégration complète de la stack agent :

    ┌─────────────────────────────────────────────────────────┐
    │  AgentRunner                                            │
    │  ├── BaseLLMClient (OpenAI / Anthropic / Groq…)        │
    │  ├── SQLiteAIStorage (persistence unifiée)              │
    │  │   ├── ai_conversations  (1 ligne / session)         │
    │  │   ├── ai_messages       (1 ligne / message)         │
    │  │   └── ai_memories       (faits extraits par LLM)    │
    │  └── get_logger("agents.runner")                       │
    │      ├── Console  : StructuredFormatter (ANSI + human) │
    │      └── Fichier  : logs/agent_demo.log (sans ANSI)    │
    └─────────────────────────────────────────────────────────┘

Scénarios :
  A. One-shot    — une question → une réponse → conversation clôturée
  B. Multi-turn  — 3 tours, contexte maintenu, tout historisé
  C. Erreur LLM  — clé API absente → conversation marquée "error" en DB
  D. Relecture   — interroger ai_conversations / ai_messages via SQLiteAIStorage

Usage :
  python examples/agent_with_persistence.py             # tous les scénarios
  python examples/agent_with_persistence.py --oneshot   # A seulement
  python examples/agent_with_persistence.py --chat      # B seulement
  python examples/agent_with_persistence.py --read      # D seulement (lecture DB)

Prérequis :
  OPENAI_API_KEY  défini dans .env ou l'environnement.
  Le fichier workflow.db doit exister (uv run pyworkflow db init).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Bootstrap sys.path ────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Logging — configurer AVANT tout import d'agent ───────────────────────────

from pyworkflow_engine.logging import LoggingConfig, configure_logging, get_logger

_LOGS_DIR = _ROOT / "logs"
_LOGS_DIR.mkdir(exist_ok=True)

configure_logging(
    LoggingConfig(
        level="DEBUG",
        json_output=False,
        log_file=str(_LOGS_DIR / "agent_demo.log"),
        log_file_max_bytes=5 * 1024 * 1024,
        log_file_backup_count=3,
    )
)

log = get_logger("examples.agent_demo")

# ── Utilitaires d'affichage ───────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
BLUE   = "\033[94m"


def section(title: str) -> None:
    bar = "═" * 62
    print(f"\n{CYAN}{BOLD}{bar}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{bar}{RESET}")


def subsection(title: str) -> None:
    print(f"\n{BLUE}{BOLD}  ▶ {title}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET}  {msg}")


def info(msg: str) -> None:
    print(f"  {YELLOW}ℹ{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def err(msg: str) -> None:
    print(f"  {RED}✗{RESET}  {msg}")


def row(label: str, value: object) -> None:
    print(f"    {DIM}{label + ':':<28}{RESET} {value}")


def sep() -> None:
    print(f"  {DIM}{'─' * 58}{RESET}")


# ── Storage helper ────────────────────────────────────────────────────────────


def _get_storage():
    from pyworkflow_engine.adapters.ai.storage.sqlite import SQLiteAIStorage
    db_path = os.environ.get("PYWORKFLOW_DB", "workflow.db")
    return SQLiteAIStorage(Path(db_path).expanduser().resolve())


# ── Scénario A : One-shot ─────────────────────────────────────────────────────


def scenario_a_oneshot() -> None:
    section("A. One-shot — une question, une réponse, tout persisté")

    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner

    log.info("Démarrage scénario one-shot", extra={"event": "scenario_start", "scenario": "A_oneshot"})

    runner = AgentRunner(general_assistant, verbose=True, triggered_by="example_script")

    info(f"Agent  : {runner.agent.name}  ({runner.agent.slug})")
    info(f"Modèle : {runner.model}")
    info(f"Persist: {runner.storage is not None}")
    sep()

    question = (
        "Explique en exactement 3 phrases ce qu'est l'architecture hexagonale "
        "et pourquoi elle facilite les tests unitaires."
    )
    info(f"Question : {question}")
    print()

    response = runner.ask(question)

    print()
    print(f"  {BOLD}Réponse :{RESET}")
    for line in (response.content or "").splitlines():
        print(f"    {line}")

    runner.finish(status="success")

    sep()
    if response.usage:
        u = response.usage
        ok(f"Tokens : {u.total_tokens} total (prompt={u.prompt_tokens}, completion={u.completion_tokens})")
    if response.response_time_ms:
        ok(f"Temps  : {response.response_time_ms:.0f} ms")
    if runner.storage and runner.conversation_id is None:
        ok("Conversation persistée dans ai_conversations ✓")

    log.info("Scénario one-shot terminé", extra={
        "event": "scenario_end", "scenario": "A_oneshot",
        "tokens": response.usage.total_tokens if response.usage else None,
        "response_ms": response.response_time_ms,
    })


# ── Scénario B : Multi-turn ───────────────────────────────────────────────────


def scenario_b_multiturn() -> None:
    section("B. Multi-turn — 3 tours, contexte mémorisé")

    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner

    runner = AgentRunner(general_assistant, verbose=False, triggered_by="example_script")

    exchanges = [
        "Quel est le plus grand désert du monde ?",
        "Quelle est sa superficie approximative en km² ?",
        "Et le deuxième plus grand désert — lequel est-ce ?",
    ]

    cumulative_tokens = 0

    for i, question in enumerate(exchanges, start=1):
        subsection(f"Tour {i}/{len(exchanges)}")
        info(f"Q : {question}")

        response = runner.ask(question)

        answer = response.content or ""
        first_line = answer.splitlines()[0] if answer else "—"
        ok(f"R : {first_line[:100]}{'…' if len(first_line) > 100 else ''}")

        if response.usage:
            t = response.usage.total_tokens or 0
            cumulative_tokens += t
            info(f"   Tokens ce tour : {t}  |  Cumulé : {cumulative_tokens}")

    runner.finish(status="success")

    sep()
    ok(f"Session terminée : {runner._turn} tours, {cumulative_tokens} tokens cumulés")
    ok(f"Historique runner : {len(runner.history)} messages (system + user + assistant)")


# ── Scénario C : Gestion d'erreur ────────────────────────────────────────────


def scenario_c_error() -> None:
    section("C. Gestion d'erreur — clé API absente → conversation marquée 'error'")

    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner, AgentRunnerError

    saved_keys: dict[str, str] = {}
    api_env_vars = ["OPENAI_API_KEY", "PYWORKFLOW_AI_OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"]
    for var in api_env_vars:
        val = os.environ.pop(var, None)
        if val:
            saved_keys[var] = val

    if saved_keys:
        warn(f"Clés API temporairement supprimées : {', '.join(saved_keys)}")

    try:
        runner = AgentRunner(general_assistant, triggered_by="example_script")
        runner.ask("Cette question ne sera jamais envoyée.")
        err("Aucune erreur levée — inattendu si la clé est absente.")
    except AgentRunnerError as exc:
        ok("AgentRunnerError interceptée comme attendu :")
        info(f"   {exc}")
    except Exception as exc:
        warn(f"Erreur inattendue : {type(exc).__name__}: {exc}")
    finally:
        for var, val in saved_keys.items():
            os.environ[var] = val
        if saved_keys:
            ok("Clés API restaurées.")


# ── Scénario D : Lecture DB ───────────────────────────────────────────────────


def scenario_d_read_db() -> None:
    section("D. Lecture DB — relire les conversations depuis ai_conversations")

    try:
        storage = _get_storage()
    except Exception as exc:
        warn(f"Impossible d'ouvrir workflow.db : {exc}")
        return

    subsection("Dernières conversations (tous agents)")

    conversations = storage.list_conversations()
    conversations.sort(key=lambda c: c.created_at, reverse=True)
    conversations = conversations[:10]

    if not conversations:
        info("Aucune conversation en base.")
        return

    info(f"{len(conversations)} conversation(s) trouvée(s)")
    sep()

    for conv in conversations:
        agent_slug = "—"
        if conv.agent_id:
            ag = storage.get_agent(conv.agent_id)
            if ag:
                agent_slug = ag.slug

        status_color = GREEN if conv.status.value == "completed" else (
            RED if conv.status.value == "archived" else YELLOW
        )
        mode = conv.metadata.get("mode", "—") if conv.metadata else "—"
        try:
            created = conv.created_at.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            created = str(conv.created_at)[:19]

        print(
            f"  {DIM}{conv.id[:8]}…{RESET}  "
            f"{agent_slug:<22}  "
            f"{status_color}{conv.status.value:<10}{RESET}  "
            f"mode={mode:<9}  "
            f"msgs={conv.message_count or 0:>3}  "
            f"tokens={conv.total_tokens or 0:>6}  "
            f"{DIM}{created}{RESET}"
        )

    sep()

    # Messages du dernier
    subsection("Messages de la dernière conversation")
    latest = conversations[0]
    row("conversation_id", latest.id)
    row("status", latest.status.value)
    row("message_count", latest.message_count or 0)
    row("total_tokens", latest.total_tokens or 0)

    messages = storage.get_messages(latest.id)
    user_assistant = [m for m in messages if m.role.value in ("user", "assistant")]

    if not user_assistant:
        info("Aucun message enregistré pour cette conversation.")
    else:
        info(f"{len(user_assistant)} message(s) user/assistant")
        sep()
        for msg in user_assistant:
            role = msg.role.value.upper()
            role_color = BLUE if role == "USER" else GREEN
            content = msg.content[:80] + ("…" if len(msg.content) > 80 else "")
            print(f"  {role_color}{role:<10}{RESET}  {content}")

    # Stats
    subsection("Statistiques agrégées")
    all_convs = storage.list_conversations()
    total_tokens = sum(c.total_tokens or 0 for c in all_convs)
    total_msgs = sum(c.message_count or 0 for c in all_convs)
    row("Total conversations", len(all_convs))
    row("Total messages", total_msgs)
    row("Total tokens", f"{total_tokens:,}")


# ── Point d'entrée ────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Agent réel avec persistence DB + logging structuré")
    parser.add_argument("--oneshot", action="store_true", help="Scénario A seulement")
    parser.add_argument("--chat",    action="store_true", help="Scénario B seulement")
    parser.add_argument("--error",   action="store_true", help="Scénario C seulement")
    parser.add_argument("--read",    action="store_true", help="Scénario D seulement (lecture DB)")
    args = parser.parse_args()

    run_all = not any([args.oneshot, args.chat, args.error, args.read])

    bar = "═" * 62
    print(f"\n{CYAN}{BOLD}{bar}{RESET}")
    print(f"{CYAN}{BOLD}  pyworkflow-engine — Agent + Persistence + Logging{RESET}")
    print(f"{CYAN}{BOLD}{bar}{RESET}")
    info(f"Logs console  : StructuredFormatter (ANSI)")
    info(f"Logs fichier  : {_LOGS_DIR / 'agent_demo.log'}")
    info(f"DB persistence: workflow.db → ai_conversations + ai_messages + ai_memories")
    info(f"Logger namespace : pyworkflow_engine.agents.runner")

    if args.oneshot or run_all:
        scenario_a_oneshot()
    if args.chat or run_all:
        scenario_b_multiturn()
    if args.error or run_all:
        scenario_c_error()
    if args.read or run_all:
        scenario_d_read_db()

    section("Démonstration terminée ✓")
    ok(f"Logs écrits dans : {_LOGS_DIR / 'agent_demo.log'}")
    ok("Données en base  : pyworkflow agent history --messages")


if __name__ == "__main__":
    main()
