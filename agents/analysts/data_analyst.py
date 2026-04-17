"""
Agent — Data Analyst (Analyst).

Agent spécialisé dans l'analyse de données : requêtes SQL, exploration
de schémas, agrégations, visualisation, interprétation de résultats.

Provider : default-openai
Outils   : sql-query, schema-inspector, csv-parser, json-parser
"""

from __future__ import annotations

from pyworkflow_engine.models.ai.agent import Agent
from pyworkflow_engine.models.ai.types import AgentRole

from agents.shared.configs import BALANCED
from agents.shared.prompts.base_prompts import (
    CODE_BLOCKS,
    DATA_ENGINEERING,
    FRENCH,
    MARKDOWN,
    NO_HALLUCINATION,
    STEP_BY_STEP,
    compose,
)
from agents.shared.tool_sets import ANALYST_TOOLS

# ── Agent definition ─────────────────────────────────────────────────────

data_analyst = Agent(
    name="Data Analyst",
    slug="data-analyst",
    description=(
        "Agent d'analyse de données : requêtes SQL, exploration de schémas, "
        "agrégations, visualisation, interprétation de résultats."
    ),
    role=AgentRole.ANALYST,
    provider_id="default-openai",
    system_prompt=compose(
        DATA_ENGINEERING,
        "Tu es un analyste de données expert.",
        "Tu aides à explorer les données, écrire des requêtes SQL performantes, "
        "interpréter les résultats et proposer des visualisations pertinentes.",
        "Quand tu écris du SQL, utilise les bonnes pratiques :",
        "- CTEs plutôt que sous-requêtes imbriquées",
        "- Alias explicites pour toutes les colonnes calculées",
        "- Commentaires pour les jointures complexes",
        STEP_BY_STEP,
        CODE_BLOCKS,
        MARKDOWN,
        FRENCH,
        NO_HALLUCINATION,
    ),
    welcome_message="Bonjour ! Quelles données souhaitez-vous analyser ?",
    config=BALANCED.model_copy(update={"temperature": 0.3}),
    tool_ids=ANALYST_TOOLS,
)
