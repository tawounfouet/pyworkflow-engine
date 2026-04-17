"""
adapters/ai/llm/groq — Client LLM pour l'API Groq (modèles ultra-rapides).

Requiert: pip install groq
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Iterator

try:
    from groq import AsyncGroq, Groq
except ImportError as exc:
    raise ImportError(
        "Groq client requires 'groq' package. Install with: pip install groq"
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
    ToolCallRequest,
)


class GroqClient(BaseLLMClient):
    """Client pour l'API Groq (interface compatible OpenAI)."""

    def __init__(self, provider_config: Any) -> None:
        super().__init__(provider_config)
        api_key = provider_config.get_api_key_value()
        if not api_key:
            raise ValueError("Groq API key is required")
        self._client = Groq(api_key=api_key)
        self._async_client = AsyncGroq(api_key=api_key)

    # ── BaseLLMClient interface ────────────────────────────────────────

    def complete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            completion = self._client.chat.completions.create(
                **self._prepare_request(request)
            )
            return self._convert_response(completion, start_time)
        except Exception as exc:
            raise LLMError(f"Groq API error: {exc}") from exc

    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            completion = await self._async_client.chat.completions.create(
                **self._prepare_request(request)
            )
            return self._convert_response(completion, start_time)
        except Exception as exc:
            raise LLMError(f"Groq API error: {exc}") from exc

    def stream(self, request: LLMRequest) -> Iterator[StreamChunk]:
        try:
            req = self._prepare_request(request)
            req["stream"] = True
            for chunk in self._client.chat.completions.create(**req):
                yield self._convert_stream_chunk(chunk)
        except Exception as exc:
            raise LLMError(f"Groq API error: {exc}") from exc

    async def astream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        try:
            req = self._prepare_request(request)
            req["stream"] = True
            stream = await self._async_client.chat.completions.create(**req)
            async for chunk in stream:
                yield self._convert_stream_chunk(chunk)
        except Exception as exc:
            raise LLMError(f"Groq API error: {exc}") from exc

    # ── Helpers privés ─────────────────────────────────────────────────

    def _prepare_request(self, request: LLMRequest) -> dict[str, Any]:
        s = self.provider_config.settings
        messages = [self._message_to_groq(m) for m in request.messages]
        req: dict[str, Any] = {
            "model": request.model or self.provider_config.default_model,
            "messages": messages,
            "temperature": (
                request.temperature
                if request.temperature is not None
                else s.temperature
            ),
        }
        if request.max_tokens or s.max_tokens:
            req["max_tokens"] = request.max_tokens or s.max_tokens
        if request.top_p or s.top_p:
            req["top_p"] = request.top_p or s.top_p
        if request.stop:
            req["stop"] = request.stop
        if request.tools:
            req["tools"] = request.tools
            if request.tool_choice:
                req["tool_choice"] = request.tool_choice
        return req

    def _message_to_groq(self, message: Message) -> dict[str, Any]:
        return {"role": message.role.value, "content": message.content}

    def _convert_response(self, completion: Any, start_time: float) -> LLMResponse:
        choice = completion.choices[0]
        msg = choice.message
        tool_calls = []
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls = [
                ToolCallRequest(
                    id=tc.id,
                    function_name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in msg.tool_calls
            ]
        usage = None
        if completion.usage:
            usage = TokenUsage(
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
                total_tokens=completion.usage.total_tokens,
            )
        return LLMResponse(
            id=completion.id,
            content=msg.content or "",
            model=completion.model,
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls,
            usage=usage,
            response_time_ms=(time.time() - start_time) * 1000,
        )

    def _convert_stream_chunk(self, chunk: Any) -> StreamChunk:
        if not chunk.choices:
            return StreamChunk()
        choice = chunk.choices[0]
        delta = choice.delta
        return StreamChunk(
            delta=getattr(delta, "content", "") or "",
            finish_reason=choice.finish_reason,
        )
