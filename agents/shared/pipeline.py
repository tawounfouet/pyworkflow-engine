"""
agents/shared/pipeline — Orchestration séquentielle déterministe d'agents.

Alternative légère au paradigme AutoGen : chaque stage exécute un agent
et passe son output comme input au suivant (pattern pipe-and-filter).

Propriétés :
  - **Déterministe** : 1 appel LLM par stage, N stages = N appels
  - **Traçable** : chaque stage crée sa propre conversation dans ``ai_conversations``
  - **Coût contrôlé** : pas de boucles conversationnelles émergentes
  - **Observabilité** : outputs de chaque stage disponibles dans le résultat

Architecture : ADR-021 (Phase 3)

Usage::

    from agents.shared.pipeline import AgentPipeline, AgentStage

    pipeline = AgentPipeline(stages=[
        AgentStage("code-reviewer",
                   prompt_template="Review this code:\\n{input}"),
        AgentStage("doc-researcher",
                   prompt_template="Document the reviewed code:\\n{input}"),
    ])
    result = pipeline.run("def add(a, b): return a + b")
    print(result.outputs["doc-researcher"])
    print(f"Total tokens: {result.total_tokens}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models.ai.agent import Agent

_log = get_logger("agents.pipeline")


@dataclass
class AgentStage:
    """Un agent dans le pipeline d'orchestration séquentielle.

    Attributes:
        agent_slug: Slug de l'agent à exécuter à ce stage.
        prompt_template: Template du prompt. Variables disponibles :
            - ``{input}`` : output du stage précédent (ou input initial)
            - ``{original}`` : input initial du pipeline (jamais transformé)
            - ``{stage_index}`` : index 0-based du stage courant
        max_turns: Nombre d'appels LLM par stage (défaut: 1).
        stop_on_error: Interrompre le pipeline si ce stage échoue.
        name: Nom optionnel pour l'affichage (défaut: agent_slug).
        metadata: Données arbitraires associées à ce stage.
    """

    agent_slug: str
    prompt_template: str = "{input}"
    max_turns: int = 1
    stop_on_error: bool = True
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.agent_slug


@dataclass
class AgentPipelineResult:
    """Résultat d'exécution d'un pipeline d'agents.

    Attributes:
        stages_completed: Nombre de stages exécutés avec succès.
        outputs: Mapping ``{agent_slug: output_text}`` pour chaque stage.
        total_tokens: Total de tokens consommés sur tous les stages.
        total_response_time_ms: Temps de réponse cumulé en ms.
        success: True si tous les stages obligatoires ont réussi.
        error: Message d'erreur si ``success=False``.
        final_output: Output du dernier stage exécuté.
    """

    stages_completed: int = 0
    outputs: dict[str, str] = field(default_factory=dict)
    total_tokens: int = 0
    total_response_time_ms: float = 0.0
    success: bool = True
    error: str | None = None
    final_output: str = ""


class AgentPipeline:
    """Orchestration séquentielle d'agents — alternative maison à AutoGen.

    Exécute les stages dans l'ordre, en passant l'output d'un stage
    comme input au suivant via le ``prompt_template``.

    Comparaison avec AutoGen :
      - AutoGen : agents qui débattent, émergent, coût explosif (×15-30)
      - AgentPipeline : séquentiel, déterministe, coût = N appels LLM

    Args:
        stages: Liste ordonnée de ``AgentStage`` à exécuter.
        name: Nom du pipeline (pour les logs).
        persist: Active la persistence des runs agent (défaut: True).

    Usage::

        pipeline = AgentPipeline(
            name="code-review-pipeline",
            stages=[
                AgentStage("code-reviewer"),
                AgentStage("doc-researcher",
                           prompt_template="Write docs for:\\n{input}"),
            ],
        )
        result = pipeline.run("def factorial(n): ...")
        if result.success:
            print(result.final_output)
    """

    def __init__(
        self,
        stages: list[AgentStage],
        name: str = "agent-pipeline",
        *,
        persist: bool = True,
    ) -> None:
        if not stages:
            raise ValueError("AgentPipeline requires at least one stage.")
        self.stages = stages
        self.name = name
        self._persist = persist

    def run(self, initial_input: str, **runner_kwargs: Any) -> AgentPipelineResult:
        """Exécute chaque stage séquentiellement.

        Args:
            initial_input: Input initial (string) passé au premier stage.
            **runner_kwargs: Options transmises à chaque ``AgentRunner``
                (ex: ``api_key``, ``model``).

        Returns:
            ``AgentPipelineResult`` avec les outputs de chaque stage et
            les métriques cumulées.
        """
        from agents.shared.loader import AgentLoadError, load_agent_by_slug
        from agents.shared.runner import AgentRunner, AgentRunnerError

        result = AgentPipelineResult()
        current_input = initial_input

        _log.info(
            "AgentPipeline '%s' starting : %d stages, input_len=%d",
            self.name,
            len(self.stages),
            len(initial_input),
            extra={
                "pipeline_name": self.name,
                "stage_count": len(self.stages),
                "stages": [s.agent_slug for s in self.stages],
                "event": "pipeline_start",
            },
        )

        for idx, stage in enumerate(self.stages):
            # Construire le prompt à partir du template
            try:
                prompt = stage.prompt_template.format(
                    input=current_input,
                    original=initial_input,
                    stage_index=idx,
                )
            except KeyError as exc:
                err = (
                    f"Stage '{stage.name}' prompt_template uses unknown "
                    f"variable {exc}. Available: {{input}}, {{original}}, "
                    f"{{stage_index}}"
                )
                result.success = False
                result.error = err
                _log.error("AgentPipeline template error: %s", err)
                if stage.stop_on_error:
                    break
                continue

            # Charger l'agent cible
            try:
                agent: Agent = load_agent_by_slug(stage.agent_slug)
            except (AgentLoadError, FileNotFoundError) as exc:
                err = f"Stage '{stage.name}': cannot load agent '{stage.agent_slug}': {exc}"
                result.success = False
                result.error = err
                _log.error("AgentPipeline load error: %s", err)
                if stage.stop_on_error:
                    break
                continue

            # Exécuter le stage
            runner = AgentRunner(
                agent,
                persist=self._persist,
                triggered_by=f"pipeline:{self.name}",
                **runner_kwargs,
            )
            try:
                response = runner.ask(prompt)
                runner.finish(status="success")

                output = response.content
                current_input = output
                result.outputs[stage.agent_slug] = output
                result.final_output = output
                result.stages_completed += 1

                if response.usage:
                    result.total_tokens += response.usage.total_tokens or 0
                if response.response_time_ms:
                    result.total_response_time_ms += response.response_time_ms

                _log.info(
                    "AgentPipeline '%s' stage %d/%d '%s' completed : tokens=%d",
                    self.name,
                    idx + 1,
                    len(self.stages),
                    stage.name,
                    response.usage.total_tokens if response.usage else 0,
                    extra={
                        "pipeline_name": self.name,
                        "stage_index": idx,
                        "stage_name": stage.name,
                        "agent_slug": stage.agent_slug,
                        "tokens": response.usage.total_tokens if response.usage else 0,
                        "response_time_ms": response.response_time_ms or 0,
                        "event": "stage_complete",
                    },
                )

            except AgentRunnerError as exc:
                runner.finish(status="error", error=str(exc))
                err = f"Stage '{stage.name}' ({stage.agent_slug}) failed: {exc}"
                result.success = False
                result.error = err
                _log.error(
                    "AgentPipeline '%s' stage %d failed: %s",
                    self.name,
                    idx,
                    exc,
                    extra={
                        "pipeline_name": self.name,
                        "stage_index": idx,
                        "stage_name": stage.name,
                        "agent_slug": stage.agent_slug,
                        "error": str(exc),
                        "event": "stage_error",
                    },
                )
                if stage.stop_on_error:
                    break

        _log.info(
            "AgentPipeline '%s' finished : stages=%d/%d success=%s tokens=%d",
            self.name,
            result.stages_completed,
            len(self.stages),
            result.success,
            result.total_tokens,
            extra={
                "pipeline_name": self.name,
                "stages_completed": result.stages_completed,
                "total_stages": len(self.stages),
                "success": result.success,
                "total_tokens": result.total_tokens,
                "total_response_time_ms": result.total_response_time_ms,
                "event": "pipeline_finish",
            },
        )

        return result

    async def arun(
        self, initial_input: str, **runner_kwargs: Any
    ) -> AgentPipelineResult:
        """Version asynchrone de ``run``."""
        from agents.shared.loader import AgentLoadError, load_agent_by_slug
        from agents.shared.runner import AgentRunner, AgentRunnerError

        result = AgentPipelineResult()
        current_input = initial_input

        for idx, stage in enumerate(self.stages):
            try:
                prompt = stage.prompt_template.format(
                    input=current_input,
                    original=initial_input,
                    stage_index=idx,
                )
            except KeyError as exc:
                err = f"Stage '{stage.name}' template error: {exc}"
                result.success = False
                result.error = err
                if stage.stop_on_error:
                    break
                continue

            try:
                agent: Agent = load_agent_by_slug(stage.agent_slug)
            except (AgentLoadError, FileNotFoundError) as exc:
                err = f"Stage '{stage.name}': cannot load '{stage.agent_slug}': {exc}"
                result.success = False
                result.error = err
                if stage.stop_on_error:
                    break
                continue

            runner = AgentRunner(
                agent,
                persist=self._persist,
                triggered_by=f"pipeline:{self.name}",
                **runner_kwargs,
            )
            try:
                response = await runner.aask(prompt)
                runner.finish(status="success")

                output = response.content
                current_input = output
                result.outputs[stage.agent_slug] = output
                result.final_output = output
                result.stages_completed += 1

                if response.usage:
                    result.total_tokens += response.usage.total_tokens or 0
                if response.response_time_ms:
                    result.total_response_time_ms += response.response_time_ms

            except AgentRunnerError as exc:
                runner.finish(status="error", error=str(exc))
                result.success = False
                result.error = f"Stage '{stage.name}' failed: {exc}"
                if stage.stop_on_error:
                    break

        return result

    def __repr__(self) -> str:
        stage_names = " → ".join(s.agent_slug for s in self.stages)
        return f"AgentPipeline({self.name!r}: {stage_names})"
