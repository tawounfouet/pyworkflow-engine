"""
Agent — General Assistant (Assistant).

Assistant IA polyvalent pour les tâches courantes : Q&A, rédaction,
résumé, traduction, brainstorming. Point d'entrée par défaut.

Provider : default-openai
Outils   : aucun (conversationnel pur)
"""

from __future__ import annotations

from pyworkflow_engine.models.ai.agent import Agent
from pyworkflow_engine.models.ai.types import AgentRole

from agents.shared.configs import BALANCED
from agents.shared.prompts.base_prompts import (
    CONCISE,
    FRENCH,
    MARKDOWN,
    NO_HALLUCINATION,
    compose,
)

# ── Agent definition ─────────────────────────────────────────────────────

general_assistant = Agent(
    name="General Assistant",
    slug="general-assistant",
    description=(
        "Assistant IA polyvalent pour les tâches courantes : "
        "questions-réponses, rédaction, résumé, traduction, brainstorming."
    ),
    role=AgentRole.ASSISTANT,
    provider_id="default-openai",
    system_prompt=compose(
        "Tu es un assistant IA polyvalent et bienveillant.",
        CONCISE,
        FRENCH,
        MARKDOWN,
        NO_HALLUCINATION,
    ),
    welcome_message="Bonjour ! Comment puis-je vous aider ?",
    config=BALANCED,
)


## Test Fonctionnement de l'agent
if __name__ == "__main__":
    pass