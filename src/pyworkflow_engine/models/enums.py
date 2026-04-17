"""
Enums du système de workflow — types de base stdlib uniquement.

Définit tous les types énumérés utilisés dans le système de workflow
pour maintenir la cohérence et la validation des états.

Utilise ``enum.Enum`` de la stdlib — zero dépendance externe.
"""

from __future__ import annotations

from enum import Enum


class TriggerType(Enum):
    """Types de déclencheurs de workflow.

    Définit comment et quand un workflow peut être démarré.
    """

    MANUAL = "manual"
    """Déclenchement manuel par un utilisateur ou une API."""

    SCHEDULE = "schedule"
    """Déclenchement programmé (cron, interval)."""

    SIGNAL = "signal"
    """Déclenchement par signal/événement interne."""

    WEBHOOK = "webhook"
    """Déclenchement par webhook HTTP."""

    FILE_WATCHER = "file_watcher"
    """Déclenchement par surveillance de fichier."""

    AI = "ai"
    """Déclenchement par un agent IA ou une décision autonome (ADR-013)."""


class StepType(Enum):
    """Types de steps dans un workflow.

    Détermine le comportement d'exécution de chaque step.
    """

    FUNCTION = "function"
    """Exécute une fonction Python."""

    SUBPROCESS = "subprocess"
    """Exécute un processus système."""

    HTTP_REQUEST = "http_request"
    """Effectue une requête HTTP."""

    SQL_QUERY = "sql_query"
    """Exécute une requête SQL."""

    HUMAN_TASK = "human_task"
    """Tâche nécessitant une intervention humaine."""

    EXTERNAL_TASK = "external_task"
    """Tâche exécutée par un système externe."""

    SUB_WORKFLOW = "sub_workflow"
    """Exécute un sous-workflow."""

    CONNECTOR = "connector"
    """Exécute un connecteur externe via le bridge pyconnectors (ADR-016)."""

    # --- Types IA (ADR-013) ---

    LLM_CALL = "llm_call"
    """Appel à un modèle de langage (LLM) via un provider IA."""

    TOOL_CALL = "tool_call"
    """Appel à un outil IA (function calling / tool use)."""

    TOOL_RESULT = "tool_result"
    """Résultat d'un appel outil IA retourné au modèle."""

    AI_DECISION = "ai_decision"
    """Décision autonome prise par un agent IA."""

    SKILL_EXECUTION = "skill_execution"
    """Exécution d'une compétence (skill) d'un agent IA."""


class ExecutorType(Enum):
    """Types d'executors disponibles.

    Détermine où et comment les steps sont exécutés.
    ``WorkflowRunner._resolve_executor()`` route chaque step vers l'executor
    correspondant selon la priorité suivante :

    1. ``step.executor_name`` non-vide → ``ExecutorRegistry`` lookup (CUSTOM)
    2. ``ExecutorType.THREAD / PROCESS / ASYNC`` → executor dédié instancié
       à la volée
    3. ``ExecutorType.LOCAL`` (ou valeur par défaut) → exécution synchrone
       directe via ``_execute_function_step``

    Les types CELERY, KUBERNETES, HUMAN, EXTERNAL nécessitent un adapter
    externe et ne sont pas routés par le core.
    """

    LOCAL = "local"
    """Exécution synchrone dans le même processus (comportement par défaut).

    Utilise directement ``_execute_function_step`` — aucun overhead de pool.
    Adapté pour les steps CPU-light et les tests.
    """

    THREAD = "thread"
    """Exécution dans un ``ThreadPoolStepExecutor`` (concurrent.futures).

    Idéal pour les opérations I/O-bound (réseau, base de données, fichiers).
    Un nouvel executor est instancié par step ; pour réutiliser un pool,
    enregistrez un ``ThreadPoolStepExecutor`` dans l'``ExecutorRegistry``.
    """

    PROCESS = "process"
    """Exécution dans un ``ProcessPoolStepExecutor`` (concurrent.futures).

    Idéal pour les opérations CPU-bound. Le callable doit être picklable.
    Le contexte est passé comme dict sérialisé (non comme objet).
    """

    ASYNC = "async"
    """Exécution asynchrone via ``AsyncStepExecutor`` (asyncio).

    Le callable doit être une coroutine (``async def``).
    Compatible avec ``step.timeout`` via ``asyncio.wait_for``.
    """

    CUSTOM = "custom"
    """Executor personnalisé via ``ExecutorRegistry``.

    Combine avec ``step.executor_name`` pour router vers un executor
    enregistré : ``engine.register_executor("my_exec", MyExecutor())``.
    """

    CELERY = "celery"
    """Exécution via Celery (adapter requis : ``adapters/celery/``)."""

    KUBERNETES = "kubernetes"
    """Exécution sur cluster Kubernetes (adapter requis)."""

    HUMAN = "human"
    """Tâche humaine — déclenche une suspension du workflow."""

    EXTERNAL = "external"
    """Exécution par système externe — déclenche une suspension du workflow."""


class RunStatus(Enum):
    """États d'exécution des workflows et steps.

    Suit le cycle de vie complet d'une exécution.
    """

    PENDING = "pending"
    """En attente de démarrage."""

    RUNNING = "running"
    """En cours d'exécution."""

    SUCCESS = "success"
    """Terminé avec succès."""

    FAILED = "failed"
    """Échec d'exécution."""

    CANCELLED = "cancelled"
    """Annulé par l'utilisateur."""

    WAITING_HUMAN = "waiting_human"
    """En attente d'intervention humaine."""

    WAITING_EXTERNAL = "waiting_external"
    """En attente de système externe."""

    SUSPENDED = "suspended"
    """Suspendu (peut être repris)."""

    TIMEOUT = "timeout"
    """Dépassement du timeout configuré."""


class Priority(Enum):
    """Priorités d'exécution des workflows.

    Utilisé pour l'ordonnancement dans les queues.
    """

    LOW = 1
    """Priorité basse."""

    NORMAL = 5
    """Priorité normale (défaut)."""

    HIGH = 10
    """Priorité haute."""

    CRITICAL = 20
    """Priorité critique."""


# Ensembles d'états pour faciliter les vérifications
TERMINAL_STATUSES = {
    RunStatus.SUCCESS,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.TIMEOUT,
}
"""États terminaux - l'exécution est définitivement finie."""

SUSPENDED_STATUSES = {
    RunStatus.WAITING_HUMAN,
    RunStatus.WAITING_EXTERNAL,
    RunStatus.SUSPENDED,
}
"""États suspendus - l'exécution peut être reprise."""

ACTIVE_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING}
"""États actifs - l'exécution est en cours."""


def is_terminal(status: RunStatus) -> bool:
    """Vérifie si un statut est terminal (fini définitivement)."""
    return status in TERMINAL_STATUSES


def is_suspended(status: RunStatus) -> bool:
    """Vérifie si un statut est suspendu (peut être repris)."""
    return status in SUSPENDED_STATUSES


def is_active(status: RunStatus) -> bool:
    """Vérifie si un statut est actif (en cours)."""
    return status in ACTIVE_STATUSES


def can_resume(status: RunStatus) -> bool:
    """Vérifie si une exécution peut être reprise depuis ce statut."""
    return is_suspended(status)


def can_cancel(status: RunStatus) -> bool:
    """Vérifie si une exécution peut être annulée depuis ce statut."""
    return status in {RunStatus.PENDING, RunStatus.RUNNING} or is_suspended(status)
