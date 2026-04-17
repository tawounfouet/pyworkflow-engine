"""
adapters/ai/llm/factory — Factory pour créer les clients LLM.

Résout le type de provider vers l'implémentation concrète appropriée.
Tous les SDK tiers sont lazy-importés pour ne pas casser l'import si une
dépendance optionnelle est absente.
"""

from __future__ import annotations

from pyworkflow_engine.exceptions import (
    MissingAIDependencyError,
    UnsupportedProviderError,
)
from pyworkflow_engine.models.ai.provider import LLMProviderConfig
from pyworkflow_engine.models.ai.types import ProviderType
from pyworkflow_engine.ports.ai.llm import BaseLLMClient


def get_llm_client(provider_config: LLMProviderConfig) -> BaseLLMClient:
    """Factory : crée un client LLM selon le type de provider.

    Args:
        provider_config: Configuration du provider LLM.

    Returns:
        Instance du client LLM approprié.

    Raises:
        UnsupportedProviderError: Si le type de provider n'est pas supporté.
        MissingAIDependencyError: Si le SDK tiers requis n'est pas installé.
    """
    ptype = provider_config.provider_type

    try:
        if ptype == ProviderType.OPENAI:
            from pyworkflow_engine.adapters.ai.llm.openai import (
                OpenAIClient,
            )  # noqa: PLC0415

            return OpenAIClient(provider_config)

        if ptype == ProviderType.ANTHROPIC:
            from pyworkflow_engine.adapters.ai.llm.anthropic import (
                AnthropicClient,
            )  # noqa: PLC0415

            return AnthropicClient(provider_config)

        if ptype == ProviderType.OLLAMA:
            from pyworkflow_engine.adapters.ai.llm.ollama import (
                OllamaClient,
            )  # noqa: PLC0415

            return OllamaClient(provider_config)

        if ptype == ProviderType.GROQ:
            from pyworkflow_engine.adapters.ai.llm.groq import (
                GroqClient,
            )  # noqa: PLC0415

            return GroqClient(provider_config)

        if ptype == ProviderType.GEMINI:
            from pyworkflow_engine.adapters.ai.llm.gemini import (
                GeminiClient,
            )  # noqa: PLC0415

            return GeminiClient(provider_config)

        raise UnsupportedProviderError(
            f"Unsupported provider type: {ptype}. "
            f"Supported: {', '.join(t.value for t in ProviderType if t != ProviderType.CUSTOM)}"
        )

    except ImportError as exc:
        provider_name = ptype.value if ptype else "unknown"
        raise MissingAIDependencyError(
            f"Missing SDK for provider '{provider_name}'. "
            f"Install with: pip install pyworkflow-engine[{provider_name}]"
        ) from exc


def list_available_providers() -> list[ProviderType]:
    """Liste les providers dont le SDK est installé dans l'environnement.

    Returns:
        Liste des ProviderType disponibles.
    """
    available: list[ProviderType] = []

    _checks: list[tuple[ProviderType, str]] = [
        (ProviderType.OPENAI, "openai"),
        (ProviderType.ANTHROPIC, "anthropic"),
        (ProviderType.GROQ, "groq"),
        (ProviderType.GEMINI, "google.generativeai"),
        (ProviderType.OLLAMA, "ollama"),
    ]

    for ptype, module_name in _checks:
        try:
            import importlib  # noqa: PLC0415

            importlib.import_module(module_name)
            available.append(ptype)
        except ImportError:
            pass

    return available
