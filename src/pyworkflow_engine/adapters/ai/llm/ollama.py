"""
adapters/ai/llm/ollama — Client LLM pour Ollama (modèles locaux).

Requiert: pip install ollama
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Iterator

try:
    import ollama
except ImportError as exc:
    raise ImportError(
        "Ollama client requires 'ollama' package. Install with: pip install ollama"
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


class OllamaClient(BaseLLMClient):
    """Client pour Ollama (modèles locaux hébergés)."""

    def __init__(self, provider_config: Any) -> None:
        super().__init__(provider_config)
        self.base_url = provider_config.api_base_url or "http://localhost:11434"
        self._client = ollama.Client(host=self.base_url)

    # ── BaseLLMClient interface ────────────────────────────────────────

    def complete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            messages = [self._message_to_ollama(m) for m in request.messages]
            options = self._build_options(request)
            response = self._client.chat(
                model=request.model or self.provider_config.default_model,
                messages=messages,
                options=options,
            )
            return self._convert_response(response, start_time)
        except Exception as exc:
            raise LLMError(f"Ollama API error: {exc}") from exc

    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        try:
            messages = [self._message_to_ollama(m) for m in request.messages]
            options = self._build_options(request)
            async_client = ollama.AsyncClient(host=self.base_url)
            response = await async_client.chat(
                model=request.model or self.provider_config.default_model,
                messages=messages,
                options=options,
            )
            return self._convert_response(response, start_time)
        except Exception:
            return self.complete(request)

    def stream(self, request: LLMRequest) -> Iterator[StreamChunk]:
        try:
            messages = [self._message_to_ollama(m) for m in request.messages]
            options = self._build_options(request)
            for chunk in self._client.chat(
                model=request.model or self.provider_config.default_model,
                messages=messages,
                options=options,
                stream=True,
            ):
                if "message" in chunk and "content" in chunk["message"]:
                    yield StreamChunk(delta=chunk["message"]["content"])
        except Exception as exc:
            raise LLMError(f"Ollama API error: {exc}") from exc

    async def astream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        try:
            messages = [self._message_to_ollama(m) for m in request.messages]
            options = self._build_options(request)
            async_client = ollama.AsyncClient(host=self.base_url)
            stream = await async_client.chat(
                model=request.model or self.provider_config.default_model,
                messages=messages,
                options=options,
                stream=True,
            )
            async for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    yield StreamChunk(delta=chunk["message"]["content"])
        except Exception:
            for chunk in self.stream(request):
                yield chunk

    # ── Helpers privés ─────────────────────────────────────────────────

    def _message_to_ollama(self, message: Message) -> dict[str, Any]:
        role_map = {
            MessageRole.SYSTEM: "system",
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
        }
        return {"role": role_map.get(message.role, "user"), "content": message.content}

    def _build_options(self, request: LLMRequest) -> dict[str, Any]:
        options: dict[str, Any] = {}
        t = request.temperature
        if t is None:
            t = self.provider_config.settings.temperature
        if t is not None:
            options["temperature"] = t
        return options

    def _convert_response(self, response: Any, start_time: float) -> LLMResponse:
        message = response.get("message", {}) if isinstance(response, dict) else {}
        content = (
            message.get("content", "")
            if isinstance(message, dict)
            else getattr(message, "content", "")
        )
        usage = None
        if isinstance(response, dict):
            if "eval_count" in response and "prompt_eval_count" in response:
                usage = TokenUsage(
                    prompt_tokens=response["prompt_eval_count"],
                    completion_tokens=response["eval_count"],
                    total_tokens=response["prompt_eval_count"] + response["eval_count"],
                )
        return LLMResponse(
            content=content,
            model=(
                response.get("model", self.provider_config.default_model)
                if isinstance(response, dict)
                else self.provider_config.default_model
            ),
            usage=usage,
            response_time_ms=(time.time() - start_time) * 1000,
        )
