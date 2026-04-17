"""
adapters/ai/frameworks/native — Runtime natif (wrap AgentRunner).

Adapter par défaut, aucune dépendance externe.
Délègue à ``AgentRunner`` existant et normalise la réponse en ``AgentResponse``.

Architecture : ADR-022
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.ports.ai.runtime import AgentResponse, BaseAgentRuntime


class NativeAgentRuntime(BaseAgentRuntime):
    """Runtime natif — délègue à ``AgentRunner`` existant.

    Usage::

        from agents.assistants.general_assistant import general_assistant
        from agents.shared.runner import AgentRunner
        from pyworkflow_engine.adapters.ai.frameworks.native import NativeAgentRuntime

        runner = AgentRunner(general_assistant)
        runtime = NativeAgentRuntime(runner)
        response = runtime.run("Bonjour")
        print(response.content)
    """

    def __init__(self, runner: Any) -> None:
        """
        Args:
            runner: Instance ``AgentRunner`` (import tardif pour éviter
                    la dépendance circulaire agents → src).
        """
        self._runner = runner

    # ── BaseAgentRuntime interface ──────────────────────────────────

    def run(self, prompt: str, **kwargs: Any) -> AgentResponse:
        resp = self._runner.ask(prompt, **kwargs)
        return self._to_agent_response(resp)

    async def arun(self, prompt: str, **kwargs: Any) -> AgentResponse:
        resp = await self._runner.aask(prompt, **kwargs)
        return self._to_agent_response(resp)

    def reset(self) -> None:
        self._runner.reset()

    @property
    def agent_slug(self) -> str:
        return self._runner.agent.slug

    @property
    def model(self) -> str:
        return self._runner.model

    # ── Accès au runner sous-jacent ─────────────────────────────────

    @property
    def runner(self) -> Any:
        """Retourne le ``AgentRunner`` sous-jacent (pour accès direct)."""
        return self._runner

    # ── Helpers ─────────────────────────────────────────────────────

    def _to_agent_response(self, resp: Any) -> AgentResponse:
        """Convertit un ``LLMResponse`` en ``AgentResponse`` normalisé."""
        return AgentResponse(
            content=resp.content,
            model=resp.model,
            agent_slug=self._runner.agent.slug,
            turn=self._runner._turn,
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
            total_tokens=resp.usage.total_tokens if resp.usage else 0,
            response_time_ms=resp.response_time_ms or 0.0,
            finish_reason=resp.finish_reason,
        )
