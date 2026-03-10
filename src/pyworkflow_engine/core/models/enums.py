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


class ExecutorType(Enum):
    """Types d'executors disponibles.

    Détermine où et comment les steps sont exécutés.
    """

    LOCAL = "local"
    """Exécution synchrone dans le même processus."""

    THREAD = "thread"
    """Exécution dans un ThreadPoolExecutor."""

    PROCESS = "process"
    """Exécution dans un ProcessPoolExecutor."""

    ASYNC = "async"
    """Exécution asynchrone avec asyncio."""

    CELERY = "celery"
    """Exécution via Celery (adapter requis)."""

    KUBERNETES = "kubernetes"
    """Exécution sur cluster Kubernetes (adapter requis)."""

    HUMAN = "human"
    """Exécution par un humain (suspension)."""

    EXTERNAL = "external"
    """Exécution par système externe (suspension)."""


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
