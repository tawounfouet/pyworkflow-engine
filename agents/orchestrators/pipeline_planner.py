"""
Agent — Pipeline Planner (Orchestrator).

Agent orchestrateur capable de décomposer une tâche complexe en sous-tâches,
de planifier leur exécution et de déléguer à d'autres agents spécialisés.

Provider : default-openai
Outils   : aucun (coordination via le graph multi-agents)
"""

from __future__ import annotations

from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.types import AgentRole

from agents.shared.prompts.base_prompts import (
    FRENCH,
    MARKDOWN,
    NO_HALLUCINATION,
    STEP_BY_STEP,
    compose,
)

# ── Agent definition ─────────────────────────────────────────────────────

pipeline_planner = Agent(
    name="Pipeline Planner",
    slug="pipeline-planner",
    description=(
        "Agent orchestrateur qui décompose une tâche complexe en sous-tâches "
        "et planifie leur exécution via des agents spécialisés."
    ),
    role=AgentRole.ORCHESTRATOR,
    provider_id="default-openai",
    model=None,  # Utiliser le modèle le plus capable du provider
    system_prompt=compose(
        "Tu es un orchestrateur de tâches expert.",
        "Ta mission est de :",
        "1. Analyser la demande de l'utilisateur",
        "2. La décomposer en sous-tâches atomiques et ordonnées",
        "3. Identifier quel agent spécialisé est le mieux adapté pour chaque sous-tâche",
        "4. Planifier l'ordre d'exécution (séquentiel ou parallèle)",
        "5. Synthétiser les résultats de chaque sous-tâche",
        "",
        "Agents disponibles :",
        "- general-assistant : Q&A, rédaction, résumé",
        "- doc-researcher : recherche documentaire, RAG",
        "- code-reviewer : revue de code, debugging",
        "- data-analyst : SQL, analyse de données, visualisation",
        "",
        "Formate ton plan comme un tableau Markdown avec les colonnes :",
        "| # | Sous-tâche | Agent | Dépendances | Statut |",
        STEP_BY_STEP,
        MARKDOWN,
        FRENCH,
        NO_HALLUCINATION,
    ),
    welcome_message="Bonjour ! Décrivez-moi la tâche complexe que vous souhaitez accomplir.",
    config=AgentConfig(
        temperature=0.3,
        max_iterations=25,
        max_tokens_per_run=16_000,
        enable_memory=True,
        enable_tools=True,
    ),
)
