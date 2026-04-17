"""
Agent — Code Reviewer (Coder).

Agent spécialisé dans la revue de code : détection de bugs, suggestions
d'amélioration, vérification des bonnes pratiques, refactoring.

Provider : default-openai
Outils   : code-executor, linter, formatter
"""

from __future__ import annotations

from pyworkflow_engine.models.ai.agent import Agent
from pyworkflow_engine.models.ai.types import AgentRole

from agents.shared.configs import CODE
from agents.shared.prompts.base_prompts import (
    CODE_BLOCKS,
    FRENCH,
    NO_HALLUCINATION,
    SOFTWARE_ENGINEERING,
    STEP_BY_STEP,
    compose,
)
from agents.shared.tool_sets import CODE_TOOLS

# ── Agent definition ─────────────────────────────────────────────────────

code_reviewer = Agent(
    name="Code Reviewer",
    slug="code-reviewer",
    description=(
        "Agent de revue de code : détection de bugs, suggestions "
        "d'amélioration, bonnes pratiques, refactoring."
    ),
    role=AgentRole.CODER,
    provider_id="default-openai",
    system_prompt=compose(
        SOFTWARE_ENGINEERING,
        "Tu effectues des revues de code rigoureuses.",
        "Pour chaque problème identifié, tu indiques :",
        "1. La sévérité (critique, majeur, mineur, suggestion)",
        "2. La localisation exacte (fichier, ligne)",
        "3. Une explication claire du problème",
        "4. Une proposition de correction avec le code corrigé",
        STEP_BY_STEP,
        CODE_BLOCKS,
        FRENCH,
        NO_HALLUCINATION,
    ),
    welcome_message="Bonjour ! Partagez-moi le code à reviewer.",
    config=CODE,
    tool_ids=CODE_TOOLS,
)
