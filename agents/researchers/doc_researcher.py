"""
Agent — Doc Researcher (Researcher).

Agent de recherche documentaire avec RAG. Spécialisé dans la synthèse
de documents, la vérification factuelle et la citation de sources.

Provider : default-openai
Outils   : web-search, url-fetch, html-parser, file-reader, csv-parser, json-parser
"""

from __future__ import annotations

from pyworkflow_engine.models.ai.agent import Agent
from pyworkflow_engine.models.ai.types import AgentRole

from agents.shared.configs import RAG_ENABLED
from agents.shared.prompts.base_prompts import (
    CITE_SOURCES,
    DETAILED,
    FRENCH,
    MARKDOWN,
    NO_HALLUCINATION,
    STEP_BY_STEP,
    compose,
)
from agents.shared.tool_sets import RESEARCHER_TOOLS

# ── Agent definition ─────────────────────────────────────────────────────

doc_researcher = Agent(
    name="Doc Researcher",
    slug="doc-researcher",
    description=(
        "Agent de recherche documentaire avec RAG. "
        "Synthèse de documents, vérification factuelle, citation de sources."
    ),
    role=AgentRole.RESEARCHER,
    provider_id="default-openai",
    system_prompt=compose(
        "Tu es un chercheur expert spécialisé dans la recherche documentaire.",
        "Tu analyses les documents fournis et les sources web pour répondre "
        "aux questions de manière exhaustive et vérifiable.",
        DETAILED,
        FRENCH,
        MARKDOWN,
        CITE_SOURCES,
        NO_HALLUCINATION,
        STEP_BY_STEP,
    ),
    welcome_message="Bonjour ! Sur quel sujet souhaitez-vous que je fasse des recherches ?",
    config=RAG_ENABLED,
    tool_ids=RESEARCHER_TOOLS,
    knowledge_base_ids=[],  # À remplir avec les IDs des bases documentaires
)
