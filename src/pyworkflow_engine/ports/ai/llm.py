"""
Port IA — interface abstraite pour les clients LLM.

Définit le contrat pur que toute implémentation d'adaptateur LLM
(OpenAI, Anthropic, Ollama, …) doit respecter.  Aucune dépendance
sur les SDK tiers ici.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator
from uuid import uuid4

from pydantic import BaseModel, Field

from pyworkflow_engine.models.ai.types import MessageRole

if TYPE_CHECKING:
    from pyworkflow_engine.models.ai import LLMProviderConfig, Message


# ── Value objects ──────────────────────────────────────────────────────────


class TokenUsage(BaseModel):
    """Statistiques d'utilisation des tokens pour une complétion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ToolCallRequest(BaseModel):
    """Appel d'outil demandé par le LLM dans une réponse."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    function_name: str
    arguments: dict[str, Any]


class LLMRequest(BaseModel):
    """Requête envoyée à un LLM."""

    messages: list[Any]  # list[Message] — Any pour éviter l'import circulaire
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: list[str] | None = None


class LLMResponse(BaseModel):
    """Réponse d'un LLM."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    role: MessageRole = MessageRole.ASSISTANT
    model: str
    finish_reason: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    usage: TokenUsage | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    response_time_ms: float | None = None


class StreamChunk(BaseModel):
    """Chunk de données en streaming."""

    delta: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)


# ── Port principal ─────────────────────────────────────────────────────────


class BaseLLMClient(ABC):
    """Interface abstraite pour tous les clients LLM.

    Toute implémentation concrète (OpenAI, Anthropic, Ollama, …) doit
    sous-classer ``BaseLLMClient`` et implémenter les quatre méthodes
    abstraites.  Les méthodes utilitaires ``chat`` / ``achat`` sont
    fournies avec des implémentations par défaut.
    """

    def __init__(self, provider_config: LLMProviderConfig) -> None:
        self.provider_config = provider_config

    # ── Interface obligatoire ──────────────────────────────────────────

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Complétion synchrone.

        Raises:
            LLMError: En cas d'erreur côté provider.
        """

    @abstractmethod
    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        """Complétion asynchrone.

        Raises:
            LLMError: En cas d'erreur côté provider.
        """

    @abstractmethod
    def stream(self, request: LLMRequest) -> Iterator[StreamChunk]:
        """Streaming synchrone.

        Yields:
            StreamChunk — fragments de réponse.

        Raises:
            LLMError: En cas d'erreur côté provider.
        """

    @abstractmethod
    async def astream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Streaming asynchrone.

        Yields:
            StreamChunk — fragments de réponse.

        Raises:
            LLMError: En cas d'erreur côté provider.
        """

    # ── Helpers ────────────────────────────────────────────────────────

    def get_model(self) -> str:
        """Retourne le modèle par défaut du provider."""
        return self.provider_config.default_model

    def chat(
        self,
        messages: list[Any] | str,
        model: str | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Interface simplifiée pour une conversation synchrone."""
        if isinstance(messages, str):
            from pyworkflow_engine.models.ai.message import Message  # noqa: PLC0415

            messages = [Message(content=messages, role=MessageRole.USER)]

        return self.complete(
            LLMRequest(
                messages=messages, model=model, temperature=temperature, **kwargs
            )
        )

    async def achat(
        self,
        messages: list[Any] | str,
        model: str | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Interface simplifiée pour une conversation asynchrone."""
        if isinstance(messages, str):
            from pyworkflow_engine.models.ai.message import Message  # noqa: PLC0415

            messages = [Message(content=messages, role=MessageRole.USER)]

        return await self.acomplete(
            LLMRequest(
                messages=messages, model=model, temperature=temperature, **kwargs
            )
        )

    # ── Context manager ────────────────────────────────────────────────

    def __enter__(self) -> BaseLLMClient:
        return self

    def __exit__(self, *args: object) -> None:
        pass
