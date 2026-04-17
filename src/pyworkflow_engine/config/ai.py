"""
pyworkflow_engine.config.ai — Configuration du sous-système IA (ADR-013).

AISettings est un dataclass frozen intégrable dans WorkflowConfig.
Toutes les valeurs peuvent être surchargées par des variables d'environnement
préfixées ``PYWORKFLOW_AI_*``.

Usage::

    from pyworkflow_engine.config.ai import AISettings, ai_settings

    # Valeurs par défaut
    cfg = AISettings()

    # Programmatique
    cfg = AISettings(
        default_provider_type="anthropic",
        default_model="claude-3-5-sonnet-latest",
        max_tool_iterations=20,
    )

    # Singleton pré-configuré depuis l'environnement
    from pyworkflow_engine.config.ai import ai_settings
    print(ai_settings.default_model)

Variables d'environnement supportées::

    PYWORKFLOW_AI_DEFAULT_PROVIDER_TYPE=openai
    PYWORKFLOW_AI_DEFAULT_MODEL=gpt-4o
    PYWORKFLOW_AI_OPENAI_API_KEY=sk-...
    PYWORKFLOW_AI_ANTHROPIC_API_KEY=sk-ant-...
    PYWORKFLOW_AI_MAX_TOOL_ITERATIONS=10
    PYWORKFLOW_AI_DEFAULT_TEMPERATURE=0.7
    PYWORKFLOW_AI_DEFAULT_MAX_TOKENS=4096
    PYWORKFLOW_AI_DEFAULT_TIMEOUT=30
    PYWORKFLOW_AI_ENABLE_STREAMING=true
    PYWORKFLOW_AI_ENABLE_RAG=false
    PYWORKFLOW_AI_DEBUG=false
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool_env(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int_env(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _float_env(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _str_env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class AISettings:
    """Configuration du sous-système IA.

    Intégrable dans ``WorkflowConfig`` (phase 4) ou utilisé en standalone.

    Attributes:
        default_provider_type: Type de provider LLM par défaut (ex: "openai").
        default_model: Modèle LLM par défaut (ex: "gpt-4o").
        openai_api_key: Clé API OpenAI (convenience — peut aussi être définie par provider).
        anthropic_api_key: Clé API Anthropic.
        max_tool_iterations: Nombre max d'itérations outil par exécution.
        default_temperature: Température LLM par défaut (0.0–2.0).
        default_max_tokens: Nombre max de tokens de complétion par défaut.
        default_timeout: Timeout des appels LLM en secondes.
        enable_streaming: Active le streaming de tokens.
        enable_rag: Active le RAG (Retrieval-Augmented Generation) par défaut.
        debug: Mode debug — logs verbeux pour le sous-système IA.

    Examples:
        >>> cfg = AISettings()
        >>> cfg.default_provider_type
        'openai'
        >>> cfg.default_temperature
        0.7

        >>> cfg = AISettings(default_model="claude-3-5-sonnet-latest")
        >>> cfg.default_model
        'claude-3-5-sonnet-latest'
    """

    default_provider_type: str = field(
        default_factory=lambda: _str_env(
            "PYWORKFLOW_AI_DEFAULT_PROVIDER_TYPE", "openai"
        )
    )
    default_model: str = field(
        default_factory=lambda: _str_env("PYWORKFLOW_AI_DEFAULT_MODEL", "gpt-4o")
    )

    # ── API Keys (convenience) ─────────────────────────────────────────────────
    openai_api_key: str = field(
        default_factory=lambda: _str_env("PYWORKFLOW_AI_OPENAI_API_KEY", "")
    )
    anthropic_api_key: str = field(
        default_factory=lambda: _str_env("PYWORKFLOW_AI_ANTHROPIC_API_KEY", "")
    )

    # ── Execution ─────────────────────────────────────────────────────────────
    max_tool_iterations: int = field(
        default_factory=lambda: _int_env("PYWORKFLOW_AI_MAX_TOOL_ITERATIONS", 10)
    )
    default_temperature: float = field(
        default_factory=lambda: _float_env("PYWORKFLOW_AI_DEFAULT_TEMPERATURE", 0.7)
    )
    default_max_tokens: int = field(
        default_factory=lambda: _int_env("PYWORKFLOW_AI_DEFAULT_MAX_TOKENS", 4096)
    )
    default_timeout: int = field(
        default_factory=lambda: _int_env("PYWORKFLOW_AI_DEFAULT_TIMEOUT", 30)
    )

    # ── Features ──────────────────────────────────────────────────────────────
    enable_streaming: bool = field(
        default_factory=lambda: _bool_env("PYWORKFLOW_AI_ENABLE_STREAMING", True)
    )
    enable_rag: bool = field(
        default_factory=lambda: _bool_env("PYWORKFLOW_AI_ENABLE_RAG", False)
    )

    # ── Debug ─────────────────────────────────────────────────────────────────
    debug: bool = field(default_factory=lambda: _bool_env("PYWORKFLOW_AI_DEBUG", False))


# Singleton pré-configuré depuis l'environnement
ai_settings: AISettings = AISettings()
