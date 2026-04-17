"""
Port IA — interface abstraite pour l'exécution d'un agent.

Tout runtime (natif, OpenAI Agents SDK, LangGraph, AutoGen) implémente
ce contrat.  Le code métier (CLI, tests, orchestrateurs) n'interagit
qu'avec ce port.

Architecture : ADR-022 (framework adapter integration patterns)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── Value object ───────────────────────────────────────────────────────────


@dataclass
class AgentResponse:
    """Réponse normalisée d'un runtime agent (framework-agnostic).

    Tous les runtimes (natif, OpenAI Agents SDK, LangGraph, AutoGen)
    convertissent leur réponse propriétaire vers cette dataclass commune.
    """

    content: str
    model: str = ""
    agent_slug: str = ""
    turn: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    response_time_ms: float = 0.0
    finish_reason: str | None = None
    tool_calls_made: list[str] = field(default_factory=list)
    handoff_target: str | None = None  # slug de l'agent ciblé par le handoff
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Port ABC ───────────────────────────────────────────────────────────────


class BaseAgentRuntime(ABC):
    """Interface abstraite pour exécuter un agent.

    Implémentations concrètes :
      - ``NativeAgentRuntime``    — wrap l'actuel ``AgentRunner``
      - ``OpenAIAgentsRuntime``   — OpenAI Agents SDK (optionnel)
      - ``LangGraphRuntime``      — LangGraph StateGraph (optionnel)
      - ``AutoGenRuntime``        — AutoGen GroupChat (optionnel)

    Usage::

        runtime: BaseAgentRuntime = get_agent_runtime(agent, runtime_type="native")
        response = runtime.run("Résume ce texte")
        print(response.content)
    """

    @abstractmethod
    def run(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution synchrone one-shot.

        Args:
            prompt: Message utilisateur.
            **kwargs: Options spécifiques au runtime.

        Returns:
            ``AgentResponse`` normalisée.
        """

    @abstractmethod
    async def arun(self, prompt: str, **kwargs: Any) -> AgentResponse:
        """Exécution asynchrone one-shot.

        Args:
            prompt: Message utilisateur.
            **kwargs: Options spécifiques au runtime.

        Returns:
            ``AgentResponse`` normalisée.
        """

    @abstractmethod
    def reset(self) -> None:
        """Réinitialise l'état interne (historique, mémoire de session)."""

    @property
    @abstractmethod
    def agent_slug(self) -> str:
        """Identifiant unique de l'agent exécuté."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Modèle LLM utilisé."""
