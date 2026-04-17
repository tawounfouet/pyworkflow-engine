"""
agents.shared.configs — Presets réutilisables d'AgentConfig.

Chaque preset est un AgentConfig pré-configuré pour un cas d'usage courant.
Les agents concrets peuvent les utiliser directement ou les surcharger via
``AgentConfig.model_copy(update={...})``.

Architecture : ADR-019
"""

from __future__ import annotations

from pyworkflow_engine.models.ai.agent import AgentConfig

# ── Créatif ──────────────────────────────────────────────────────────────
# Haute température, beaucoup d'itérations.
# Idéal pour : brainstorming, génération de contenu, exploration.
CREATIVE = AgentConfig(
    temperature=1.2,
    max_iterations=15,
    max_tokens_per_run=12_000,
    enable_memory=True,
    enable_tools=True,
)

# ── Précis ───────────────────────────────────────────────────────────────
# Basse température, peu d'itérations.
# Idéal pour : extraction factuelle, classification, parsing structuré.
PRECISE = AgentConfig(
    temperature=0.1,
    max_iterations=5,
    max_tokens_per_run=4_000,
    enable_memory=True,
    enable_tools=True,
)

# ── Équilibré ────────────────────────────────────────────────────────────
# Défauts raisonnables pour usage général.
BALANCED = AgentConfig(
    temperature=0.7,
    max_iterations=10,
    max_tokens_per_run=8_000,
    enable_memory=True,
    enable_tools=True,
)

# ── RAG ──────────────────────────────────────────────────────────────────
# Recherche documentaire activée, température basse pour fidélité aux sources.
# Idéal pour : Q&A sur documentation, synthèse, fact-checking.
RAG_ENABLED = AgentConfig(
    temperature=0.3,
    max_iterations=10,
    max_tokens_per_run=10_000,
    enable_memory=True,
    enable_tools=True,
    enable_rag=True,
)

# ── Code ─────────────────────────────────────────────────────────────────
# Température à zéro, beaucoup d'itérations, outils activés.
# Idéal pour : génération de code, refactoring, review, debugging.
CODE = AgentConfig(
    temperature=0.0,
    max_iterations=20,
    max_tokens_per_run=12_000,
    enable_memory=True,
    enable_tools=True,
)

# ── Minimal ──────────────────────────────────────────────────────────────
# Single-shot, pas de mémoire, pas d'outils.
# Idéal pour : tâches simples, transformations textuelles, one-liners.
MINIMAL = AgentConfig(
    temperature=0.0,
    max_iterations=1,
    max_tokens_per_run=2_000,
    enable_memory=False,
    enable_tools=False,
)
