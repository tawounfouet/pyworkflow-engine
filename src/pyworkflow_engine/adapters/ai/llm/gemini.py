"""
adapters/ai/llm/gemini — Client LLM pour l'API Google Gemini.

Requiert: pip install google-generativeai
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Iterator

try:
    import google.generativeai as genai
except ImportError as exc:
    raise ImportError(
        "Gemini client requires 'google-generativeai' package. "
        "Install with: pip install google-generativeai"
    ) from exc

from pyworkflow_engine.exceptions import LLMError
from pyworkflow_engine.models.ai.message import Message
from pyworkflow_engine.models.ai.types import MessageRole
from pyworkflow_engine.ports.ai.llm import (
    BaseLLMClient,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TokenUsage,
)


class GeminiClient(BaseLLMClient):
    """Client pour l'API Google Gemini."""

    def __init__(self, provider_config: Any) -> None:
        super().__init__(provider_config)
        api_key = provider_config.get_api_key_value()
        if not api_key:
            raise ValueError("Gemini API key is required")
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(provider_config.default_model)

    # ── BaseLLMClient interface ────────────────────────────────────────

    def complete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            prompt = self._prepare_prompt(request.messages)
            gen_cfg = genai.types.GenerationConfig(
                temperature=request.temperature
                or self.provider_config.settings.temperature,
                max_output_tokens=request.max_tokens
                or self.provider_config.settings.max_tokens,
            )
            response = self._model.generate_content(prompt, generation_config=gen_cfg)
            return self._convert_response(response, start_time)
        except Exception as exc:
            raise LLMError(f"Gemini API error: {exc}") from exc

    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        # Gemini SDK async support is limited; fall back to sync
        return self.complete(request)

    def stream(self, request: LLMRequest) -> Iterator[StreamChunk]:
        try:
            prompt = self._prepare_prompt(request.messages)
            gen_cfg = genai.types.GenerationConfig(
                temperature=request.temperature
                or self.provider_config.settings.temperature,
                max_output_tokens=request.max_tokens
                or self.provider_config.settings.max_tokens,
            )
            for chunk in self._model.generate_content(
                prompt, generation_config=gen_cfg, stream=True
            ):
                if chunk.text:
                    yield StreamChunk(delta=chunk.text)
        except Exception as exc:
            raise LLMError(f"Gemini API error: {exc}") from exc

    async def astream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        for chunk in self.stream(request):
            yield chunk

    # ── Helpers privés ─────────────────────────────────────────────────

    def _prepare_prompt(self, messages: list[Message]) -> str:
        parts = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                parts.append(f"System: {msg.content}")
            elif msg.role == MessageRole.USER:
                parts.append(f"Human: {msg.content}")
            elif msg.role == MessageRole.ASSISTANT:
                parts.append(f"Assistant: {msg.content}")
        return "\n\n".join(parts)

    def _convert_response(self, response: Any, start_time: float) -> LLMResponse:
        content = response.text or ""
        usage = None
        if hasattr(response, "usage_metadata"):
            m = response.usage_metadata
            usage = TokenUsage(
                prompt_tokens=getattr(m, "prompt_token_count", 0),
                completion_tokens=getattr(m, "candidates_token_count", 0),
                total_tokens=getattr(m, "total_token_count", 0),
            )
        return LLMResponse(
            content=content,
            model=self.provider_config.default_model,
            usage=usage,
            response_time_ms=(time.time() - start_time) * 1000,
        )
