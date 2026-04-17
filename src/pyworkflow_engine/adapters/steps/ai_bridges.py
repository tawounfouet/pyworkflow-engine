"""
adapters/steps/ai_bridges — Bridges IA pour le système de workflow (ADR-016 Phase 4).

Ce module expose trois bridges :

``AIStep``
    Exécute un agent IA comme step de workflow.
    Reçoit le message depuis le contexte, retourne la réponse comme output.

``AgentExecutor``
    Executor ``BaseExecutor`` wrappant ``AgentService`` pour utilisation
    via ``ExecutorRegistry``.

``JobAsTool``
    Expose un Job workflow comme ``BaseTool`` pour qu'un agent LLM puisse
    déclencher des workflows depuis un tool-call.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pyworkflow_engine.exceptions import StepExecutionError
from pyworkflow_engine.models.ai.types import ToolType
from pyworkflow_engine.ports.ai.tool import BaseTool

if TYPE_CHECKING:
    from pyworkflow_engine.engine.ai.agent_service import AgentService
    from pyworkflow_engine.engine.context import WorkflowContext
    from pyworkflow_engine.models import Step

logger = logging.getLogger(__name__)


# ── AIStep ────────────────────────────────────────────────────────────────────


class AIStep:
    """Exécute un agent IA comme step de workflow.

    Instancier dans la définition de step, puis appeler ``run(context)``
    depuis l'executor ou le runner.

    Args:
        agent_service: Service d'agents IA.
        agent_id: ID de l'agent à utiliser.
        message_key: Clé dans le contexte contenant le message utilisateur
            (défaut : ``"message"``).
        conversation_id_key: Clé dans le contexte pour passer/stocker l'ID
            de conversation (défaut : ``"ai_conversation_id"``).

    Example::

        ai_step = AIStep(
            agent_service=service,
            agent_id="my-agent-id",
            message_key="user_input",
        )

        @step(name="ai_response")
        def ask_agent(context):
            return ai_step.run(context)
    """

    def __init__(
        self,
        agent_service: AgentService,
        agent_id: str,
        message_key: str = "message",
        conversation_id_key: str = "ai_conversation_id",
    ) -> None:
        self.agent_service = agent_service
        self.agent_id = agent_id
        self.message_key = message_key
        self.conversation_id_key = conversation_id_key

    def run(self, context: WorkflowContext) -> dict[str, Any]:
        """Exécute l'agent sur le message présent dans le contexte.

        Returns:
            Dict contenant ``response`` (str) et ``conversation_id`` (str).

        Raises:
            StepExecutionError: Si le message est absent ou si l'agent échoue.
        """
        message = context.get(self.message_key)
        if not message:
            raise StepExecutionError(
                f"AIStep: message key '{self.message_key}' not found in context.",
                step_name=f"ai_step:{self.agent_id}",
            )

        conversation_id: str | None = context.get(self.conversation_id_key)

        try:
            reply, conversation = self.agent_service.chat(
                agent_id=self.agent_id,
                message=str(message),
                conversation_id=conversation_id,
            )
        except Exception as exc:
            raise StepExecutionError(
                f"AIStep: agent '{self.agent_id}' raised: {exc}",
                step_name=f"ai_step:{self.agent_id}",
            ) from exc

        return {
            "response": reply.content,
            "conversation_id": conversation.id,
        }


# ── AgentExecutor ─────────────────────────────────────────────────────────────


class AgentExecutor:
    """Executor ``BaseExecutor``-compatible wrappant ``AgentService``.

    Permet d'enregistrer un agent IA dans l'``ExecutorRegistry`` du workflow
    engine et d'exécuter des steps de type ``AI`` via l'interface standard.

    Args:
        agent_service: Service d'agents IA.
        default_agent_id: ID de l'agent par défaut (peut être surchargé
            via ``step.metadata["agent_id"]``).

    Usage::

        executor = AgentExecutor(agent_service=service, default_agent_id="assistant")
        registry.register("ai", executor)
    """

    def __init__(
        self,
        agent_service: AgentService,
        default_agent_id: str = "",
    ) -> None:
        self.agent_service = agent_service
        self.default_agent_id = default_agent_id

    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Exécute le step via l'agent IA.

        L'agent_id est résolu depuis ``step.metadata["agent_id"]`` ou
        ``default_agent_id``.  Le message est extrait depuis
        ``step.metadata["message_key"]`` (défaut: ``"message"``).

        Returns:
            Dict ``{"response": str, "conversation_id": str}``.

        Raises:
            StepExecutionError: Si aucun agent_id n'est disponible.
        """
        metadata = getattr(step, "metadata", {}) or {}
        agent_id = metadata.get("agent_id", self.default_agent_id)
        if not agent_id:
            raise StepExecutionError(
                "AgentExecutor: no agent_id provided (set step.metadata['agent_id'] "
                "or pass default_agent_id to AgentExecutor).",
                step_name=step.name,
            )
        message_key = metadata.get("message_key", "message")
        ai_step = AIStep(
            agent_service=self.agent_service,
            agent_id=agent_id,
            message_key=message_key,
        )
        return ai_step.run(context)


# ── JobAsTool ─────────────────────────────────────────────────────────────────


class JobAsTool(BaseTool):
    """Expose un Job workflow comme BaseTool pour le function-calling LLM.

    Permet à un agent IA de déclencher l'exécution d'un workflow via
    un tool-call.  Le résultat est le statut de la run créée.

    Args:
        job_name: Nom du Job à exécuter.
        facade: Instance de ``PyWorkflowFacade`` (ou tout objet ayant
            ``run_job(name, input_data)``).
        description: Description du tool pour le LLM.

    Example::

        job_tool = JobAsTool(
            job_name="send_report",
            facade=workflow_facade,
            description="Triggers the send_report workflow with the given data.",
        )
        registry.register_tool(job_tool.definition, job_tool.run)
    """

    key = ""  # défini dynamiquement dans __init__
    _dynamic_key = True  # skip __init_subclass__ key check
    tool_type = ToolType.WORKFLOW

    def __init__(
        self,
        job_name: str,
        facade: Any,
        description: str = "",
        parameters_schema: dict[str, Any] | None = None,
    ) -> None:
        # Contournement de la vérification __init_subclass__ (key vide sur BaseTool)
        self.key = f"job:{job_name}"
        self.name = f"Run Job: {job_name}"
        self.description = description or f"Triggers the '{job_name}' workflow job."
        self.parameters_schema = parameters_schema or {
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "object",
                    "description": "Input data to pass to the job.",
                },
            },
        }
        self._job_name = job_name
        self._facade = facade

    def run(self, input_data: dict[str, Any] | None = None, **_: Any) -> str:  # type: ignore[override]
        """Déclenche l'exécution du job.

        Args:
            input_data: Données d'entrée passées au job.

        Returns:
            Résumé de l'exécution (job_run_id + statut).
        """
        try:
            job_run = self._facade.run_job(self._job_name, input_data=input_data or {})
            return (
                f"Job '{self._job_name}' triggered successfully. "
                f"job_run_id={job_run.job_run_id}, status={job_run.status.value}"
            )
        except Exception as exc:
            logger.warning("JobAsTool '%s' failed: %s", self._job_name, exc)
            return f"Error triggering job '{self._job_name}': {exc}"
