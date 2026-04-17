"""
adapters/ai/llm/openai — Client LLM pour l'API OpenAI.

Requiert: pip install openai
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Iterator

try:
    import openai
    from openai import AsyncOpenAI, OpenAI
    from openai.types.chat import ChatCompletion, ChatCompletionChunk
except ImportError as exc:
    raise ImportError(
        "OpenAI client requires 'openai' package. Install with: pip install openai"
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


class OpenAIClient(BaseLLMClient):
    """Client pour l'API OpenAI (ChatGPT, GPT-4, …)."""

    def __init__(self, provider_config: Any) -> None:
        super().__init__(provider_config)

        api_key = provider_config.get_api_key_value()
        if not api_key:
            raise ValueError("OpenAI API key is required")

        client_cfg: dict[str, Any] = {
            "api_key": api_key,
            "timeout": provider_config.settings.timeout,
            "max_retries": provider_config.settings.max_retries,
        }
        if provider_config.api_base_url:
            client_cfg["base_url"] = provider_config.api_base_url

        self._sync_client = OpenAI(**client_cfg)
        self._async_client = AsyncOpenAI(**client_cfg)

    # ── BaseLLMClient interface ────────────────────────────────────────

    def complete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            completion = self._sync_client.chat.completions.create(
                **self._prepare_request(request)
            )
            return self._convert_response(completion, start_time)
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error in OpenAI client: {exc}") from exc

    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            completion = await self._async_client.chat.completions.create(
                **self._prepare_request(request)
            )
            return self._convert_response(completion, start_time)
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error in OpenAI client: {exc}") from exc

    def stream(self, request: LLMRequest) -> Iterator[StreamChunk]:
        try:
            req = self._prepare_request(request)
            req["stream"] = True
            for chunk in self._sync_client.chat.completions.create(**req):
                yield self._convert_stream_chunk(chunk)
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error in OpenAI client: {exc}") from exc

    async def astream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        try:
            req = self._prepare_request(request)
            req["stream"] = True
            async for chunk in await self._async_client.chat.completions.create(**req):
                yield self._convert_stream_chunk(chunk)
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error in OpenAI client: {exc}") from exc

    # ── Helpers privés ─────────────────────────────────────────────────

    def _prepare_request(self, request: LLMRequest) -> dict[str, Any]:
        base = self._base_config()
        messages = [self._message_to_openai(msg) for msg in request.messages]
        req: dict[str, Any] = {
            "model": request.model or base["model"],
            "messages": messages,
            "temperature": (
                request.temperature
                if request.temperature is not None
                else base["temperature"]
            ),
        }
        if request.max_tokens or base["max_tokens"]:
            req["max_tokens"] = request.max_tokens or base["max_tokens"]
        if request.top_p or base["top_p"]:
            req["top_p"] = request.top_p or base["top_p"]
        if request.frequency_penalty or base["frequency_penalty"]:
            req["frequency_penalty"] = (
                request.frequency_penalty or base["frequency_penalty"]
            )
        if request.presence_penalty or base["presence_penalty"]:
            req["presence_penalty"] = (
                request.presence_penalty or base["presence_penalty"]
            )
        if request.stop:
            req["stop"] = request.stop
        if request.tools:
            req["tools"] = request.tools
            if request.tool_choice:
                req["tool_choice"] = request.tool_choice
        return req

    def _base_config(self) -> dict[str, Any]:
        s = self.provider_config.settings
        return {
            "model": self.provider_config.default_model,
            "temperature": s.temperature,
            "max_tokens": s.max_tokens,
            "top_p": s.top_p,
            "frequency_penalty": s.frequency_penalty,
            "presence_penalty": s.presence_penalty,
        }

    def _message_to_openai(self, message: Message) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "role": message.role.value,
            "content": message.content,
        }
        if message.role == MessageRole.ASSISTANT and message.metadata:
            if tc := message.metadata.get("tool_calls"):
                msg["tool_calls"] = tc
        if message.role == MessageRole.TOOL and message.metadata:
            if tc_id := message.metadata.get("tool_call_id"):
                msg["tool_call_id"] = tc_id
        return msg

    def _convert_response(
        self, completion: ChatCompletion, start_time: float
    ) -> LLMResponse:
        choice = completion.choices[0]
        message = choice.message
        tool_calls = []
        if message.tool_calls:
            tool_calls = [
                ToolCallRequest(
                    id=tc.id,
                    function_name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in message.tool_calls
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
            content=message.content or "",
            model=completion.model,
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls,
            usage=usage,
            response_time_ms=(time.time() - start_time) * 1000,
        )

    def _convert_stream_chunk(self, chunk: ChatCompletionChunk) -> StreamChunk:
        if not chunk.choices:
            return StreamChunk()
        choice = chunk.choices[0]
        delta = choice.delta
        content = delta.content or ""
        tool_calls = []
        if delta.tool_calls:
            tool_calls = [
                ToolCallRequest(
                    id=tc.id or "",
                    function_name=tc.function.name or "" if tc.function else "",
                    arguments=tc.function.arguments or {} if tc.function else {},
                )
                for tc in delta.tool_calls
                if tc.function
            ]
        return StreamChunk(
            delta=content, finish_reason=choice.finish_reason, tool_calls=tool_calls
        )
