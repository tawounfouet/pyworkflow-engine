"""Configuration du Celery adapter — dataclass immuable.

Tous les champs ont des valeurs par défaut raisonnables pour un Redis local.
Passer un ``CeleryConfig`` explicite à ``CeleryExecutor`` pour surcharger.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CeleryConfig:
    """Configuration pour le CeleryExecutor.

    Tous les champs ont des valeurs par défaut raisonnables.
    L'utilisateur peut surcharger via passage explicite.

    Examples::

        # Configuration minimale (Redis local par défaut)
        config = CeleryConfig()

        # Configuration personnalisée
        config = CeleryConfig(
            broker_url="redis://redis-host:6379/0",
            result_backend="redis://redis-host:6379/1",
            task_timeout=300.0,
            task_default_queue="workflows",
        )
    """

    broker_url: str = "redis://localhost:6379/0"
    """URL du broker Celery (Redis ou RabbitMQ)."""

    result_backend: str | None = None
    """Backend de stockage des résultats. ``None`` → désactivé."""

    task_serializer: str = "json"
    """Sérialiseur pour les arguments des tasks."""

    result_serializer: str = "json"
    """Sérialiseur pour les résultats des tasks."""

    accept_content: tuple[str, ...] = ("json",)
    """Types de contenu acceptés par les workers."""

    timezone: str = "UTC"
    """Timezone pour la planification Celery."""

    enable_utc: bool = True
    """Utiliser UTC pour toutes les dates."""

    task_track_started: bool = True
    """Activer le suivi de l'état STARTED des tasks."""

    task_timeout: float | None = None
    """Timeout en secondes pour l'attente du résultat (``None`` = infini)."""

    task_default_queue: str = "pyworkflow"
    """Queue Celery par défaut pour les tasks pyworkflow."""

    worker_concurrency: int | None = None
    """Nombre de workers concurrents (``None`` = auto selon CPUs)."""

    worker_prefetch_multiplier: int = 4
    """Nombre de messages pré-chargés par worker."""

    app_name: str = "pyworkflow_engine"
    """Nom de l'application Celery (apparaît dans Flower/logs)."""

    task_soft_time_limit: float | None = None
    """Soft time limit (lève SoftTimeLimitExceeded côté worker)."""

    task_time_limit: float | None = None
    """Hard time limit (tue le worker si dépassé)."""
