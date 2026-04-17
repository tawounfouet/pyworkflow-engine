"""
Agents — Catalogue d'agents IA concrets.

Ce package contient l'ensemble des agents IA organisés par rôle (AgentRole) :
- ``assistants/``      — Agents conversationnels généralistes (Q&A)
- ``researchers/``     — Agents de recherche documentaire (RAG, synthèse)
- ``coders/``          — Agents de génération / review de code
- ``analysts/``        — Agents d'analyse de données
- ``orchestrators/``   — Agents multi-agents / planificateurs
- ``_template/``       — Template pour créer un nouvel agent
- ``shared/``          — Utilitaires partagés (configs, prompts, tool sets)

Architecture : ADR-019
Modèle source : src/pyworkflow_engine/models/ai/agent.py → Agent, AgentConfig
"""
