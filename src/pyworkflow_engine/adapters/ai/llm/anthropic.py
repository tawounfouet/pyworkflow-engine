"""
adapters/ai/llm/anthropic — Client LLM pour l'API Anthropic (Claude).

Requiert: pip install anthropic
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Iterator

try:
    import anthropic
    from anthropic import Anthropic, AsyncAnthropic
    from anthropic.types import Message as AnthropicMessage
except ImportError as exc:
    raise ImportError(
        "Anthropic client requires 'anthropic' package. Install with: pip install anthropic"
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


class AnthropicClient(BaseLLMClient):
    """Client pour l'API Anthropic (Claude)."""

    def __init__(self, provider_config: Any) -> None:
        super().__init__(provider_config)

        api_key = provider_config.get_api_key_value()
        if not api_key:
            raise ValueError("Anthropic API key is required")

        client_cfg: dict[str, Any] = {
            "api_key": api_key,
            "timeout": provider_config.settings.timeout,
            "max_retries": provider_config.settings.max_retries,
        }
        if provider_config.api_base_url:
            client_cfg["base_url"] = provider_config.api_base_url

        self._sync_client = Anthropic(**client_cfg)
        self._async_client = AsyncAnthropic(**client_cfg)

    # ── BaseLLMClient interface ────────────────────────────────────────

    def complete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            completion = self._sync_client.messages.create(
                **self._prepare_request(request)
            )
            return self._convert_response(completion, start_time)
        except anthropic.AnthropicError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error in Anthropic client: {exc}") from exc

    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            completion = await self._async_client.messages.create(
                **self._prepare_request(request)
            )
            return self._convert_response(completion, start_time)
        except anthropic.AnthropicError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error in Anthropic client: {exc}") from exc

    def stream(self, request: LLMRequest) -> Iterator[StreamChunk]:
        try:
            with self._sync_client.messages.stream(
                **self._prepare_request(request)
            ) as s:
                for event in s:
                    chunk = self._convert_stream_event(event)
                    if chunk:
                        yield chunk
        except anthropic.AnthropicError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error in Anthropic client: {exc}") from exc

    async def astream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        try:
            async with self._async_client.messages.stream(
                **self._prepare_request(request)
            ) as s:
                async for event in s:
                    chunk = self._convert_stream_event(event)
                    if chunk:
                        yield chunk
        except anthropic.AnthropicError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Unexpected error in Anthropic client: {exc}") from exc

    # ── Helpers privés ─────────────────────────────────────────────────

    def _prepare_request(self, request: LLMRequest) -> dict[str, Any]:
        s = self.provider_config.settings
        system_message = None
        messages = []
        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                system_message = msg.content
            else:
                messages.append(self._message_to_anthropic(msg))

        req: dict[str, Any] = {
            "model": request.model or self.provider_config.default_model,
            "messages": messages,
            "temperature": (
                request.temperature
                if request.temperature is not None
                else s.temperature
            ),
            "max_tokens": request.max_tokens or s.max_tokens or 4096,
        }
        if system_message:
            req["system"] = system_message
        if request.top_p or s.top_p:
            req["top_p"] = request.top_p or s.top_p
        if request.stop:
            req["stop_sequences"] = request.stop
        if request.tools:
            req["tools"] = request.tools
            if request.tool_choice:
                req["tool_choice"] = request.tool_choice
        return req

    def _message_to_anthropic(self, message: Message) -> dict[str, Any]:
        role_map = {
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
            MessageRole.TOOL: "user",
        }
        return {"role": role_map.get(message.role, "user"), "content": message.content}

    def _convert_response(
        self, completion: AnthropicMessage, start_time: float
    ) -> LLMResponse:
        content = ""
        tool_calls = []
        for block in completion.content:
            if hasattr(block, "text"):
                content += block.text
            elif hasattr(block, "name"):
                tool_calls.append(
                    ToolCallRequest(
                        id=getattr(block, "id", ""),
                        function_name=block.name,
                        arguments=getattr(block, "input", {}),
                    )
                )
        usage = None
        if completion.usage:
            usage = TokenUsage(
                prompt_tokens=completion.usage.input_tokens,
                completion_tokens=completion.usage.output_tokens,
                total_tokens=completion.usage.input_tokens
                + completion.usage.output_tokens,
            )
        return LLMResponse(
            id=completion.id,
            content=content,
            model=completion.model,
            finish_reason=completion.stop_reason,
            tool_calls=tool_calls,
            usage=usage,
            response_time_ms=(time.time() - start_time) * 1000,
        )

    def _convert_stream_event(self, event: Any) -> StreamChunk | None:
        if hasattr(event, "type"):
            if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                return StreamChunk(delta=event.delta.text)
            if event.type == "message_stop":
                return StreamChunk(finish_reason="stop")
        return None
