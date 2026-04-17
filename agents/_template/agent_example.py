"""
Agent — [NOM] ([RÔLE]).

Description : TODO
Provider    : TODO (ex: default-openai, default-anthropic)
Outils      : TODO (ex: web-search, sql-query)
Owner       : TODO

Ce fichier sert de template pour créer un nouvel agent IA.
Copiez-le dans le dossier correspondant au rôle et remplacez les TODO.

Architecture : ADR-019
Checklist    : agents/README.md
"""

from __future__ import annotations

from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.types import AgentRole

# ── Agent definition ─────────────────────────────────────────────────────

agent_example = Agent(
    name="TODO Agent Name",
    slug="todo-agent-name",
    description="TODO: Description détaillée de la responsabilité de l'agent.",
    role=AgentRole.ASSISTANT,  # TODO: choisir le rôle (ASSISTANT, RESEARCHER, CODER, ANALYST, ORCHESTRATOR…)
    provider_id="TODO-provider-id",  # Résolu au runtime — slug ou UUID du provider
    model=None,  # None = utiliser le default_model du provider
    system_prompt=(
        "TODO: Écris ici le system prompt de l'agent.\n"
        "Tu peux composer à partir des fragments de agents/shared/prompts/base_prompts.py."
    ),
    welcome_message="TODO: Message d'accueil optionnel.",
    config=AgentConfig(
        max_iterations=10,
        temperature=0.7,
        enable_memory=True,
        enable_tools=True,
        enable_rag=False,  # True si l'agent utilise une knowledge base
    ),
    tool_ids=[],  # TODO: IDs des outils autorisés
    skill_ids=[],  # TODO: IDs des compétences
    knowledge_base_ids=[],  # TODO: IDs des bases de connaissance (RAG)
)
