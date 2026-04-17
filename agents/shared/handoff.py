"""
agents/shared/handoff — Protocole de délégation inter-agents.

Permet à un agent de déléguer explicitement une tâche à un autre agent
via un protocole synchrone et déterministe (pas de conversation émergente).

Chaque handoff :
  - Crée sa propre conversation dans ``ai_conversations`` (trace complète)
  - Effectue un seul appel LLM (coût contrôlé)
  - Retourne immédiatement la réponse (pas de boucle)

Architecture : ADR-021 (Phase 1)

Usage::

    from agents.shared.handoff import AgentHandoff

    handoff = AgentHandoff()
    result = handoff.execute(
        source_slug="pipeline-planner",
        target_slug="code-reviewer",
        message="Review this Python function:\\n\\ndef add(a, b): return a + b",
        context={"task_id": "task-123"},
    )
    print(result.response)
    print(result.tokens_used)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models.ai.agent import Agent

_log = get_logger("agents.handoff")


@dataclass
class HandoffRequest:
    """Demande de délégation d'un agent source vers un agent cible.

    Attributes:
        source_slug: Slug de l'agent qui délègue.
        target_slug: Slug de l'agent cible.
        message: Message / tâche à déléguer.
        context: Contexte additionnel (clés/valeurs arbitraires).
        reason: Raison de la délégation (pour la traçabilité).
    """

    source_slug: str
    target_slug: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class HandoffResult:
    """Résultat d'une délégation inter-agents.

    Attributes:
        source_slug: Slug de l'agent source.
        target_slug: Slug de l'agent cible.
        response: Réponse de l'agent cible.
        tokens_used: Total de tokens consommés.
        response_time_ms: Temps de réponse en millisecondes.
        success: True si la délégation a réussi.
        error: Message d'erreur si ``success=False``.
        conversation_id: ID de la conversation créée dans ``ai_conversations`` (traçabilité).
    """

    source_slug: str
    target_slug: str
    response: str = ""
    tokens_used: int = 0
    response_time_ms: float = 0.0
    success: bool = True
    error: str | None = None
    conversation_id: str | None = None  # ID de la conversation dans ai_conversations


class HandoffError(Exception):
    """Erreur lors d'une délégation inter-agents."""


class AgentHandoff:
    """Orchestre la délégation explicite entre agents.

    Charge l'agent cible depuis le manifest et l'exécute via ``AgentRunner``
    en mode one-shot.  La délégation est :
      - **Synchrone** — attend la réponse avant de retourner
      - **Déterministe** — un appel LLM, une réponse
      - **Traçable** — crée sa propre conversation dans ``ai_conversations``

    Args:
        persist: Active la persistence des runs (défaut: True).

    Usage::

        handoff = AgentHandoff()
        result = handoff.execute(
            source_slug="pipeline-planner",
            target_slug="doc-researcher",
            message="Research the latest Python packaging standards.",
        )
    """

    def __init__(self, *, persist: bool = True) -> None:
        self._persist = persist

    def execute(
        self,
        source_slug: str,
        target_slug: str,
        message: str,
        context: dict[str, Any] | None = None,
        reason: str = "",
        **runner_kwargs: Any,
    ) -> HandoffResult:
        """Exécute une délégation synchrone vers l'agent cible.

        Args:
            source_slug: Slug de l'agent qui délègue.
            target_slug: Slug de l'agent cible.
            message: Message / tâche à déléguer.
            context: Contexte additionnel (optionnel).
            reason: Raison de la délégation (optionnel, pour les logs).
            **runner_kwargs: Options supplémentaires pour ``AgentRunner``
                (ex: ``api_key``, ``model``).

        Returns:
            ``HandoffResult`` avec la réponse et les métriques.

        Raises:
            HandoffError: Si le chargement de l'agent cible échoue.
        """
        request = HandoffRequest(
            source_slug=source_slug,
            target_slug=target_slug,
            message=message,
            context=context or {},
            reason=reason,
        )
        return self._run(request, runner_kwargs)

    def from_request(
        self,
        request: HandoffRequest,
        **runner_kwargs: Any,
    ) -> HandoffResult:
        """Exécute une délégation depuis un ``HandoffRequest`` existant.

        Args:
            request: Objet ``HandoffRequest`` décrivant la délégation.
            **runner_kwargs: Options supplémentaires pour ``AgentRunner``.

        Returns:
            ``HandoffResult`` avec la réponse et les métriques.
        """
        return self._run(request, runner_kwargs)

    # ── Private ──────────────────────────────────────────────────────

    def _run(
        self, request: HandoffRequest, runner_kwargs: dict[str, Any]
    ) -> HandoffResult:
        """Charge l'agent cible et exécute le handoff."""
        from agents.shared.loader import AgentLoadError, load_agent_by_slug
        from agents.shared.runner import AgentRunner, AgentRunnerError

        _log.info(
            "Handoff : %s → %s (reason=%r)",
            request.source_slug,
            request.target_slug,
            request.reason,
            extra={
                "source_slug": request.source_slug,
                "target_slug": request.target_slug,
                "message_length": len(request.message),
                "reason": request.reason,
                "event": "handoff_start",
            },
        )

        # Charger l'agent cible depuis le manifest
        try:
            target_agent: Agent = load_agent_by_slug(request.target_slug)
        except (AgentLoadError, FileNotFoundError) as exc:
            err = f"Cannot load target agent '{request.target_slug}': {exc}"
            _log.error("Handoff failed: %s", err)
            return HandoffResult(
                source_slug=request.source_slug,
                target_slug=request.target_slug,
                success=False,
                error=err,
            )

        # Construire le message en ajoutant le contexte si fourni
        final_message = request.message
        if request.context:
            ctx_lines = "\n".join(f"  {k}: {v}" for k, v in request.context.items())
            final_message = f"{request.message}\n\n[Context]\n{ctx_lines}"

        # Exécuter via AgentRunner (one-shot)
        runner = AgentRunner(
            target_agent,
            persist=self._persist,
            triggered_by=f"handoff:{request.source_slug}",
            **runner_kwargs,
        )
        try:
            response = runner.ask(final_message)
            runner.finish(status="success")

            result = HandoffResult(
                source_slug=request.source_slug,
                target_slug=request.target_slug,
                response=response.content,
                tokens_used=(response.usage.total_tokens if response.usage else 0),
                response_time_ms=response.response_time_ms or 0.0,
                success=True,
                conversation_id=runner.conversation_id,
            )
            _log.info(
                "Handoff completed : %s → %s tokens=%d rt=%.0fms",
                request.source_slug,
                request.target_slug,
                result.tokens_used,
                result.response_time_ms,
                extra={
                    "source_slug": request.source_slug,
                    "target_slug": request.target_slug,
                    "tokens_used": result.tokens_used,
                    "response_time_ms": result.response_time_ms,
                    "conversation_id": result.conversation_id,
                    "event": "handoff_complete",
                },
            )
            return result

        except AgentRunnerError as exc:
            runner.finish(status="error", error=str(exc))
            err = f"AgentRunner error during handoff to '{request.target_slug}': {exc}"
            _log.error("Handoff error: %s", err)
            return HandoffResult(
                source_slug=request.source_slug,
                target_slug=request.target_slug,
                success=False,
                error=err,
                conversation_id=runner.conversation_id,
            )
