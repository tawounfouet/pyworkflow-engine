"""
adapters/ai/llm — Clients LLM concrets.

Factory et implémentations pour OpenAI, Anthropic, Gemini, Groq, Ollama.
Tous dépendent de sdks tiers installés optionnellement.

Usage::

    from pyworkflow_engine.adapters.ai.llm import get_llm_client
    from pyworkflow_engine.models.ai import LLMProviderConfig, ProviderType

    cfg = LLMProviderConfig(
        name="gpt-4o",
        provider_type=ProviderType.OPENAI,
        default_model="gpt-4o",
        api_key="sk-...",
    )
    client = get_llm_client(cfg)
    response = client.chat("Hello!")
"""

from __future__ import annotations

from pyworkflow_engine.adapters.ai.llm.factory import (
    get_llm_client,
    list_available_providers,
)
from pyworkflow_engine.ports.ai.llm import (
    BaseLLMClient,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TokenUsage,
    ToolCallRequest,
)

__all__ = [
    "BaseLLMClient",
    "LLMRequest",
    "LLMResponse",
    "StreamChunk",
    "TokenUsage",
    "ToolCallRequest",
    "get_llm_client",
    "list_available_providers",
]
