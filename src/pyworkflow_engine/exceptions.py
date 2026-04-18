"""
Exceptions du système de workflow — gestion d'erreurs avancée.

Définit toutes les exceptions spécifiques au workflow pour permettre
une gestion d'erreur granulaire et informative.

Inclut également les exceptions du sous-système IA (ADR-013), fusionnées
depuis ai_engine/exceptions.py pour éviter la duplication.

Utilise la hiérarchie d'exceptions standard Python — zero dépendance externe.
"""

from __future__ import annotations

from typing import Any


class WorkflowError(Exception):
    """Exception de base pour tous les erreurs de workflow.

    Classe de base pour toutes les exceptions spécifiques au workflow.
    Permet de capturer toutes les erreurs workflow avec un seul except.

    Attributes:
        message: Message d'erreur descriptif.
        details: Détails additionnels sur l'erreur.
        job_name: Nom du job concerné (optionnel).
        step_name: Nom du step concerné (optionnel).
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        job_name: str | None = None,
        step_name: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.job_name = job_name
        self.step_name = step_name

    def __str__(self) -> str:
        """Représentation string enrichie avec contexte."""
        parts = [self.message]

        if self.job_name:
            parts.append(f"Job: {self.job_name}")
        if self.step_name:
            parts.append(f"Step: {self.step_name}")
        if self.details:
            parts.append(f"Details: {self.details}")

        return " | ".join(parts)


class WorkflowValidationError(WorkflowError):
    """Erreur de validation de définition de workflow.

    Levée quand une définition de Job ou Step est invalide.

    Examples:
        >>> raise WorkflowValidationError(
        ...     "Step dependency 'nonexistent' not found",
        ...     job_name="my_job",
        ...     step_name="my_step"
        ... )
    """


class WorkflowExecutionError(WorkflowError):
    """Erreur d'exécution de workflow.

    Erreur générale pendant l'exécution d'un workflow.
    Classe de base pour les erreurs d'exécution spécifiques.
    """


class StepExecutionError(WorkflowExecutionError):
    """Erreur d'exécution d'une étape spécifique.

    Levée quand l'exécution d'une Step échoue.

    Attributes:
        original_exception: Exception originale qui a causé l'échec.
        step_run_id: ID de l'exécution de l'étape.
        retry_count: Nombre de tentatives déjà effectuées.
    """

    def __init__(
        self,
        message: str,
        step_name: str,
        job_name: str | None = None,
        original_exception: Exception | None = None,
        step_run_id: str | None = None,
        retry_count: int = 0,
        **kwargs,
    ):
        super().__init__(message, job_name=job_name, step_name=step_name, **kwargs)
        self.original_exception = original_exception
        self.step_run_id = step_run_id
        self.retry_count = retry_count

    def __str__(self) -> str:
        """Représentation enrichie avec infos sur l'exception originale."""
        base_str = super().__str__()

        if self.original_exception:
            base_str += f" | Original: {type(self.original_exception).__name__}: {self.original_exception}"
        if self.step_run_id:
            base_str += f" | StepRunID: {self.step_run_id}"
        if self.retry_count > 0:
            base_str += f" | Retry: {self.retry_count}"

        return base_str


class WorkflowFailed(WorkflowExecutionError):
    """Erreur d'échec complet de workflow.

    Levée quand un workflow échoue complètement et ne peut pas
    être repris ou récupéré.

    Attributes:
        traceback_info: Information de traceback pour le debug.
        error_step: Nom du step qui a causé l'échec.
    """

    def __init__(
        self,
        message: str,
        error_step: str | None = None,
        traceback_info: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.error_step = error_step
        self.traceback_info = traceback_info


class WorkflowSuspended(WorkflowError):
    """Exception pour suspension de workflow.

    Levée quand un workflow doit être suspendu pour attendre
    une intervention externe (humaine ou système).

    Cette exception n'est pas vraiment une "erreur" mais un
    mécanisme de contrôle de flux pour suspendre l'exécution.

    Attributes:
        reason: Raison de la suspension.
        suspend_data: Données nécessaires pour reprendre l'exécution.
        resume_callback: Callback optionnel pour la reprise.
    """

    def __init__(
        self,
        message: str,
        reason: str | None = None,
        suspend_data: dict[str, Any] | None = None,
        resume_callback: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.reason = reason or message  # Default reason to message if not provided
        self.suspend_data = suspend_data or {}
        self.resume_callback = resume_callback


class WorkflowSuspendedHuman(WorkflowSuspended):
    """Suspension pour intervention humaine.

    Levée quand un workflow attend une action humaine.

    Examples:
        >>> raise WorkflowSuspendedHuman(
        ...     "Manual approval required",
        ...     reason="approval_needed",
        ...     suspend_data={"approval_form": "user-123", "deadline": "2024-01-01"},
        ...     job_name="user_onboarding",
        ...     step_name="approval_step"
        ... )
    """


class WorkflowSuspendedExternal(WorkflowSuspended):
    """Suspension pour système externe.

    Levée quand un workflow attend une réponse d'un système externe.

    Examples:
        >>> raise WorkflowSuspendedExternal(
        ...     "Waiting for API callback",
        ...     reason="api_callback",
        ...     suspend_data={"callback_url": "/webhook/xyz", "timeout": "3600"},
        ...     job_name="api_integration",
        ...     step_name="api_call"
        ... )
    """


class WorkflowTimeoutError(WorkflowExecutionError):
    """Erreur de timeout de workflow ou step.

    Levée quand un timeout configuré est dépassé.

    Attributes:
        timeout_seconds: Durée du timeout en secondes.
        elapsed_seconds: Durée écoulée avant le timeout.
    """

    def __init__(
        self, message: str, timeout_seconds: float, elapsed_seconds: float, **kwargs
    ):
        super().__init__(message, **kwargs)
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = elapsed_seconds

    def __str__(self) -> str:
        """Représentation avec infos de timing."""
        base_str = super().__str__()
        return f"{base_str} | Timeout: {self.timeout_seconds}s | Elapsed: {self.elapsed_seconds}s"


class WorkflowCancelled(WorkflowError):
    """Exception pour annulation de workflow.

    Levée quand un workflow est annulé par l'utilisateur ou le système.

    Attributes:
        cancelled_by: Qui a annulé le workflow.
        cancel_reason: Raison de l'annulation.
    """

    def __init__(
        self,
        message: str,
        cancelled_by: str = "system",
        cancel_reason: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.cancelled_by = cancelled_by
        self.cancel_reason = cancel_reason


class DAGValidationError(WorkflowValidationError):
    """Erreur de validation du graphe de dépendances (DAG).

    Levée quand le graphe de dépendances des steps est invalide.

    Attributes:
        cycle_steps: Steps impliqués dans un cycle (si applicable).
        orphan_steps: Steps orphelins sans dépendances (si applicable).
    """

    def __init__(
        self,
        message: str,
        cycle_steps: list[str] | None = None,
        orphan_steps: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.cycle_steps = cycle_steps or []
        self.orphan_steps = orphan_steps or []


class ExecutorError(WorkflowExecutionError):
    """Erreur liée à l'executor.

    Levée quand un executor ne peut pas exécuter une step.

    Attributes:
        executor_type: Type de l'executor qui a échoué.
        executor_details: Détails sur l'état de l'executor.
    """

    def __init__(
        self,
        message: str,
        executor_type: str,
        executor_details: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.executor_type = executor_type
        self.executor_details = executor_details or {}


class StorageError(WorkflowError):
    """Erreur de persistence.

    Levée quand la sauvegarde ou le chargement d'un JobRun échoue.

    Attributes:
        operation: Opération qui a échoué ('save', 'load', 'delete').
        storage_type: Type de backend de persistence.
    """

    def __init__(self, message: str, operation: str, storage_type: str, **kwargs):
        super().__init__(message, **kwargs)
        self.operation = operation
        self.storage_type = storage_type


class ContextError(WorkflowError):
    """Erreur liée au contexte de workflow.

    Levée quand l'accès ou la manipulation du contexte échoue.

    Attributes:
        context_key: Clé du contexte concernée.
        context_operation: Opération qui a échoué.
    """

    def __init__(
        self,
        message: str,
        context_key: str | None = None,
        context_operation: str = "access",
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.context_key = context_key
        self.context_operation = context_operation


# Fonctions utilitaires pour créer des exceptions communes
def create_step_failed_error(
    step_name: str,
    job_name: str,
    original_exception: Exception,
    step_run_id: str | None = None,
    retry_count: int = 0,
) -> StepExecutionError:
    """Crée une StepExecutionError standardisée."""
    return StepExecutionError(
        f"Step '{step_name}' execution failed: {original_exception}",
        step_name=step_name,
        job_name=job_name,
        original_exception=original_exception,
        step_run_id=step_run_id,
        retry_count=retry_count,
    )


def create_timeout_error(
    entity_name: str,
    entity_type: str,
    timeout_seconds: float,
    elapsed_seconds: float,
    job_name: str | None = None,
    step_name: str | None = None,
) -> WorkflowTimeoutError:
    """Crée une WorkflowTimeoutError standardisée."""
    return WorkflowTimeoutError(
        f"{entity_type.title()} '{entity_name}' timed out after {elapsed_seconds:.2f}s",
        timeout_seconds=timeout_seconds,
        elapsed_seconds=elapsed_seconds,
        job_name=job_name,
        step_name=step_name,
    )


def create_validation_error(
    message: str,
    job_name: str | None = None,
    step_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> WorkflowValidationError:
    """Crée une WorkflowValidationError standardisée."""
    return WorkflowValidationError(
        message, details=details, job_name=job_name, step_name=step_name
    )


# ══════════════════════════════════════════════════════════════════════════════
# Exceptions IA — fusionnées depuis ai_engine/exceptions.py (ADR-013)
# ══════════════════════════════════════════════════════════════════════════════


class AIError(WorkflowError):
    """Exception de base pour tout le sous-système IA."""


# ── Provider ──────────────────────────────────────────────────────────────────


class ProviderError(AIError):
    """Erreur liée à un provider LLM."""


class LLMError(ProviderError):
    """Erreur lors de l'appel à un LLM."""


class ProviderNotFoundError(ProviderError):
    """Provider introuvable."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"Provider '{provider_id}' not found.")


class UnsupportedProviderError(ProviderError):
    """Type de provider non supporté."""

    def __init__(self, provider_type: str, available: list[str] | None = None) -> None:
        self.provider_type = provider_type
        self.available = available or []
        msg = f"Provider type '{provider_type}' is not supported."
        if self.available:
            msg += f" Available types: {', '.join(self.available)}"
        super().__init__(msg)


class APIKeyMissingError(ProviderError):
    """Clé API manquante pour un provider."""

    def __init__(self, provider_name: str, env_var: str | None = None) -> None:
        self.provider_name = provider_name
        self.env_var = env_var
        msg = f"API key missing for provider '{provider_name}'."
        if env_var:
            msg += f" Set it via provider config or environment variable '{env_var}'."
        super().__init__(msg)


# ── Agent ─────────────────────────────────────────────────────────────────────


class AgentError(AIError):
    """Erreur liée aux agents."""


class AgentNotFoundError(AgentError):
    """Agent introuvable."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' not found.")


class AgentDisabledError(AgentError):
    """Agent désactivé."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"Agent '{identifier}' is disabled.")


# ── Conversation ──────────────────────────────────────────────────────────────


class ConversationError(AIError):
    """Erreur liée à une conversation."""


class ConversationNotFoundError(ConversationError):
    """Conversation introuvable."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"Conversation '{conversation_id}' not found.")


# ── Graph ─────────────────────────────────────────────────────────────────────


class AIGraphError(AIError):
    """Erreur liée à un graph IA."""


class AIGraphNotFoundError(AIGraphError):
    """Graph IA introuvable."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"AI Graph '{identifier}' not found.")


# ── Execution IA ──────────────────────────────────────────────────────────────


class AIExecutionError(AIError):
    """Erreur liée à une exécution IA."""


class AIExecutionNotFoundError(AIExecutionError):
    """Exécution IA introuvable."""

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        super().__init__(f"AI Execution '{execution_id}' not found.")


# ── Tool IA ───────────────────────────────────────────────────────────────────


class AIToolError(AIError):
    """Erreur liée à un tool IA."""


class AIToolNotFoundError(AIToolError):
    """Tool IA introuvable."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"AI Tool '{identifier}' not found.")


class AIToolExecutionError(AIToolError):
    """Erreur lors de l'exécution d'un tool IA."""

    def __init__(self, tool_name: str, detail: str) -> None:
        self.tool_name = tool_name
        self.detail = detail
        super().__init__(f"Error executing AI tool '{tool_name}': {detail}")


# ── Skill ─────────────────────────────────────────────────────────────────────


class SkillError(AIError):
    """Erreur liée à un skill IA."""


class SkillNotFoundError(SkillError):
    """Skill introuvable dans le registre."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"Skill '{identifier}' not found in registry.")


class SkillExecutionError(SkillError):
    """Erreur lors de l'exécution d'un skill."""

    def __init__(self, skill_key: str, detail: str) -> None:
        self.skill_key = skill_key
        self.detail = detail
        super().__init__(f"Error executing skill '{skill_key}': {detail}")


class SkillConfigurationError(SkillError):
    """Erreur de configuration d'un skill."""


# ── Knowledge / RAG ───────────────────────────────────────────────────────────


class KnowledgeError(AIError):
    """Erreur liée à une source de connaissance."""


class KnowledgeSourceNotFoundError(KnowledgeError):
    """Source de connaissance introuvable."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"Knowledge source '{identifier}' not found.")


# ── Dependency ────────────────────────────────────────────────────────────────


class MissingAIDependencyError(AIError):
    """Dépendance optionnelle IA manquante."""

    def __init__(self, package: str, extra: str) -> None:
        self.package = package
        self.extra = extra
        super().__init__(
            f"Package '{package}' is required for this AI feature. "
            f"Install it with: pip install pyworkflow-engine[{extra}]"
        )
