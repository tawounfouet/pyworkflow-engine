#!/usr/bin/env python3
# filepath: /Users/awf/Projects/software-engineering/python-packages/pyworkflow-engine/examples/agent_chat.py
"""
Exemple — Exécution réelle d'un agent IA avec un LLM.

Ce script montre 3 façons d'utiliser les agents du catalogue :

  1. One-shot programmatique (AgentRunner.ask)
  2. REPL interactif (AgentRunner.repl)
  3. Via la CLI (pyworkflow agent run / chat)

Prérequis :
  - pip install openai   (ou pip install pyworkflow-engine[ai])
  - Définir OPENAI_API_KEY dans le .env ou l'environnement

Usage :
  python examples/agent_chat.py           # one-shot demo
  python examples/agent_chat.py --repl    # mode interactif
  python examples/agent_chat.py --all     # tester les 5 agents

Ou via la CLI :
  pyworkflow agent run general-assistant "Résume le concept de l'architecture hexagonale" -v
  pyworkflow agent chat general-assistant -v
  pyworkflow agent run code-reviewer "Review: def add(a,b): return a+b" --model gpt-4o-mini
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# ── Bootstrap : injecter le project root dans sys.path ───────────────────────
# Permet d'exécuter le script directement :  python examples/agent_chat.py
# sans avoir à faire  PYTHONPATH=. python examples/agent_chat.py
def _bootstrap() -> None:
    """Remonte jusqu'à la racine du projet (là où agents/ existe) et l'injecte."""
    here = Path(__file__).resolve().parent  # examples/
    root = here.parent  # pyworkflow-engine/
    if (root / "agents" / "manifest.yaml").exists() and str(root) not in sys.path:
        sys.path.insert(0, str(root))


_bootstrap()


# Charger .env si python-dotenv est installé
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def demo_oneshot() -> None:
    """Démo one-shot : une question → une réponse."""
    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner

    print("=" * 60)
    print("🤖 Démo One-Shot — General Assistant")
    print("=" * 60)

    runner = AgentRunner(general_assistant, verbose=True)
    print(f"   Modèle : {runner.model}")
    print(f"   Agent  : {runner.agent.name}")
    print()

    response = runner.ask("Explique en 3 phrases ce qu'est l'architecture hexagonale.")

    print(f"📝 Réponse :\n{response.content}\n")

    if response.usage:
        print(
            f"⚡ Tokens: {response.usage.total_tokens} "
            f"(prompt: {response.usage.prompt_tokens}, "
            f"completion: {response.usage.completion_tokens})"
        )
    if response.response_time_ms:
        print(f"⏱  Temps : {response.response_time_ms:.0f}ms")


def demo_multi_turn() -> None:
    """Démo multi-turn : conversation avec contexte."""
    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner

    print("\n" + "=" * 60)
    print("🤖 Démo Multi-Turn — Conversation")
    print("=" * 60)

    runner = AgentRunner(general_assistant)

    questions = [
        "Quel est le plus grand océan du monde ?",
        "Quelle est sa superficie approximative ?",
        "Et le deuxième plus grand ?",
    ]

    for q in questions:
        print(f"\n👤 {q}")
        response = runner.ask(q)
        print(f"🤖 {response.content}")

    print(f"\n📊 Historique : {len(runner.history)} messages")


def demo_code_reviewer() -> None:
    """Démo avec le code reviewer."""
    from agents.coders.code_reviewer import code_reviewer
    from agents.shared.runner import AgentRunner

    print("\n" + "=" * 60)
    print("🤖 Démo Code Reviewer")
    print("=" * 60)

    runner = AgentRunner(code_reviewer, model="gpt-4o-mini")

    code = """
def fibonacci(n):
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n-1) + fibonacci(n-2)

result = fibonacci(40)
print(result)
"""

    response = runner.ask(f"Review ce code Python :\n```python{code}```")
    print(f"\n📝 Review :\n{response.content}")


def demo_all_agents() -> None:
    """Teste rapidement les 5 agents."""
    from agents.shared.loader import load_all_agents
    from agents.shared.runner import AgentRunner

    print("\n" + "=" * 60)
    print("🤖 Test de tous les agents du catalogue")
    print("=" * 60)

    agents = load_all_agents()
    question = "Dis-moi en une phrase ce que tu sais faire."

    for agent in agents:
        print(f"\n{'─' * 40}")
        print(f"🤖 {agent.name} ({agent.role.value})")
        try:
            runner = AgentRunner(agent, model="gpt-4o-mini")
            response = runner.ask(question)
            print(f"   → {response.content[:200]}")
            if response.usage:
                print(f"   ⚡ {response.usage.total_tokens} tokens")
        except Exception as exc:
            print(f"   ✗ Erreur : {exc}")


def demo_repl() -> None:
    """Lance le REPL interactif."""
    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner

    runner = AgentRunner(general_assistant, verbose=True)
    runner.repl()


if __name__ == "__main__":
    # Vérifier la clé API
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get(
        "PYWORKFLOW_AI_OPENAI_API_KEY"
    ):
        print("⚠️  Aucune clé API trouvée.")
        print("   Définissez OPENAI_API_KEY dans votre .env ou environnement.")
        print("   Exemple : export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    args = sys.argv[1:]

    if "--repl" in args:
        demo_repl()
    elif "--all" in args:
        demo_all_agents()
    elif "--code" in args:
        demo_code_reviewer()
    elif "--multi" in args:
        demo_multi_turn()
    else:
        demo_oneshot()
        print("\n💡 Autres modes : --repl, --multi, --code, --all")
        print("💡 Via CLI : pyworkflow agent run general-assistant 'votre question' -v")
