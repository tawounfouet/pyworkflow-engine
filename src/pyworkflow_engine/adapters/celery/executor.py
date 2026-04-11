"""CeleryExecutor — exécution distribuée des workflow steps via Celery.

Implémente le port ``BaseExecutor`` en déléguant l'exécution à des workers
Celery via un broker (Redis ou RabbitMQ).

Contrainte critique — sérialisation des handlers :
    Les handlers de steps **doivent** être des fonctions top-level importables.
    Les lambdas, closures, et méthodes d'instance ne sont pas sérialisables
    via le nom qualifié. Si un handler ne peut pas être sérialisé, une
    ``SerializationError`` est levée avec un message explicatif.

Usage::

    from pyworkflow_engine.adapters.celery import CeleryExecutor

    executor = CeleryExecutor(broker_url="redis://localhost:6379/0")
    engine = WorkflowEngine()
    engine.register_executor("celery", executor)

    # Les steps avec executor_name="celery" seront routés vers cet executor.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from pyworkflow_engine.engine.context import WorkflowContext
    from pyworkflow_engine.models import Step

from pyworkflow_engine.exceptions import ExecutorError, StepExecutionError
from pyworkflow_engine.ports.executor import BaseExecutor

logger = logging.getLogger(__name__)


class SerializationError(ExecutorError):
    """Erreur de sérialisation d'un handler step pour Celery.

    Levée quand un handler ne peut pas être converti en référence
    importable (lambda, closure, méthode d'instance, etc.).
    """

    def __init__(self, message: str, handler: Any = None) -> None:
        handler_repr = repr(handler) if handler is not None else "unknown"
        super().__init__(
            message,
            executor_type="CeleryExecutor",
            executor_details={"handler": handler_repr},
        )


class CeleryExecutor(BaseExecutor):
    """Executor qui délègue l'exécution des steps à des Celery workers.

    Respecte le contrat ``BaseExecutor.execute(step, context)`` et
    envoie l'exécution à un worker Celery via le broker configuré.

    L'exécution est **synchrone du point de vue de l'appelant** :
    ``execute()`` attend le résultat via ``AsyncResult.get()``.
    Pour une exécution fire-and-forget, utilisez directement l'API Celery.

    Args:
        broker_url: URL du broker (Redis: ``redis://host:port/db``,
            RabbitMQ: ``amqp://user:pass@host:port/vhost``).
        result_backend: URL du backend de résultats. Requis pour que
            ``execute()`` puisse récupérer le résultat.
        task_timeout: Timeout en secondes pour l'attente du résultat.
            ``None`` = attente infinie (déconseillé en production).
        config: ``CeleryConfig`` complet. Si fourni, surcharge tous les
            autres paramètres individuels.

    Examples::

        # Configuration minimale
        executor = CeleryExecutor(
            broker_url="redis://localhost:6379/0",
            result_backend="redis://localhost:6379/1",
        )

        # Via CeleryConfig
        from pyworkflow_engine.adapters.celery import CeleryConfig
        config = CeleryConfig(
            broker_url="amqp://guest:guest@localhost:5672//",
            result_backend="redis://localhost:6379/0",
            task_timeout=120.0,
            task_default_queue="high_priority",
        )
        executor = CeleryExecutor(config=config)
    """

    def __init__(
        self,
        broker_url: str = "redis://localhost:6379/0",
        result_backend: str | None = None,
        task_timeout: float | None = None,
        task_serializer: str = "json",
        task_default_queue: str = "pyworkflow",
        config: Any | None = None,  # CeleryConfig (évite import circulaire)
    ) -> None:
        # CeleryConfig prend la priorité sur les kwargs individuels
        if config is not None:
            from pyworkflow_engine.adapters.celery.config import CeleryConfig

            if not isinstance(config, CeleryConfig):
                raise TypeError(f"config doit être un CeleryConfig, reçu {type(config)}")
            self._config = config
        else:
            from pyworkflow_engine.adapters.celery.config import CeleryConfig

            self._config = CeleryConfig(
                broker_url=broker_url,
                result_backend=result_backend,
                task_timeout=task_timeout,
                task_serializer=task_serializer,
                task_default_queue=task_default_queue,
            )

        self._celery_app: Any = None
        self._celery_task: Any = None

    # ── App Celery (lazy init) ────────────────────────────────────────────────

    def _get_app(self) -> Any:
        """Retourne l'app Celery, initialisée à la première utilisation."""
        if self._celery_app is None:
            from pyworkflow_engine.adapters.celery.app import get_celery_app

            cfg = self._config
            self._celery_app = get_celery_app(
                broker_url=cfg.broker_url,
                result_backend=cfg.result_backend,
                app_name=cfg.app_name,
                task_serializer=cfg.task_serializer,
                task_default_queue=cfg.task_default_queue,
                task_track_started=cfg.task_track_started,
                task_soft_time_limit=cfg.task_soft_time_limit,
                task_time_limit=cfg.task_time_limit,
            )

            # Enregistrer la task execute_step sur cette app
            from pyworkflow_engine.adapters.celery.tasks import make_celery_task

            self._celery_task = make_celery_task(self._celery_app)

        return self._celery_app

    # ── Sérialisation des handlers ───────────────────────────────────────────

    def _serialize_handler(self, handler: "Callable") -> str:
        """Sérialise un handler en référence qualifiée importable.

        Args:
            handler: Callable à sérialiser.

        Returns:
            Référence sous la forme ``"module.function_name"``.

        Raises:
            SerializationError: Si le handler n'est pas sérialisable
                (lambda, closure, méthode d'instance, etc.).
        """
        module = getattr(handler, "__module__", None)
        qualname = getattr(handler, "__qualname__", None)

        if not module or not qualname:
            raise SerializationError(
                f"Impossible de sérialiser le handler '{handler}' : "
                "il n'a pas de __module__ ou __qualname__.",
                handler=handler,
            )

        # Détecter les lambdas et closures (qualname contient "<lambda>" ou "<locals>")
        if "<lambda>" in qualname:
            raise SerializationError(
                f"Les lambdas ne peuvent pas être sérialisés pour Celery. "
                f"Handler : {handler}. "
                "Remplacez-le par une fonction top-level nommée.",
                handler=handler,
            )
        if "<locals>" in qualname:
            raise SerializationError(
                f"Les closures (fonctions définies dans une autre fonction) "
                f"ne peuvent pas être sérialisées pour Celery. "
                f"Handler : {handler}. "
                "Remplacez-le par une fonction top-level importable.",
                handler=handler,
            )

        return f"{module}.{qualname}"

    # ── Port principal ────────────────────────────────────────────────────────

    def execute(self, step: "Step", context: "WorkflowContext") -> Any:
        """Envoie l'exécution au broker Celery et attend le résultat.

        Args:
            step: Step à exécuter. Le ``handler`` doit être une fonction
                top-level importable (voir contrainte sérialisation).
            context: Contexte de workflow (sérialisé en dict via ``to_dict()``).

        Returns:
            Résultat retourné par le handler (dict).

        Raises:
            SerializationError: Si le handler n'est pas sérialisable.
            StepExecutionError: Si l'exécution Celery échoue ou timeout.
            RuntimeError: Si ``result_backend`` n'est pas configuré
                (nécessaire pour récupérer le résultat).
        """
        if not step.handler:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function",
                step_name=step.name,
            )

        if not self._config.result_backend:
            raise StepExecutionError(
                f"Step '{step.name}': CeleryExecutor nécessite un 'result_backend' "
                "pour récupérer les résultats. "
                "Configurez-le avec CeleryConfig(result_backend='redis://...').",
                step_name=step.name,
            )

        # Sérialiser le handler
        try:
            handler_ref = self._serialize_handler(step.handler)
        except SerializationError:
            raise
        except Exception as e:
            raise SerializationError(
                f"Erreur inattendue lors de la sérialisation du handler : {e}",
                handler=step.handler,
            ) from e

        # Sérialiser le contexte
        context_dict = context.to_dict()

        # Obtenir l'app et envoyer la task
        app = self._get_app()

        logger.debug(
            "CeleryExecutor: dispatch step '%s' → handler '%s' sur queue '%s'",
            step.name,
            handler_ref,
            self._config.task_default_queue,
        )

        try:
            async_result = app.send_task(
                "pyworkflow_engine.execute_step",
                args=[handler_ref, context_dict, step.name],
                queue=self._config.task_default_queue,
                serializer="json",
            )
        except Exception as e:
            raise StepExecutionError(
                f"Impossible d'envoyer la task Celery pour step '{step.name}': {e}",
                details={
                    "handler_ref": handler_ref,
                    "broker_url": self._config.broker_url,
                    "error_type": type(e).__name__,
                },
                step_name=step.name,
            ) from e

        # Attendre le résultat
        timeout = self._config.task_timeout
        # step.timeout prend la priorité sur le config-level timeout
        if step.timeout is not None:
            timeout = step.timeout.total_seconds()

        logger.debug(
            "CeleryExecutor: attente résultat step '%s' (timeout=%s)",
            step.name,
            timeout,
        )

        try:
            result = async_result.get(timeout=timeout, propagate=True)
        except Exception as e:
            error_type = type(e).__name__
            # Détecter le timeout Celery (celery.exceptions.TimeoutError)
            if "TimeoutError" in error_type or "Timeout" in error_type:
                raise StepExecutionError(
                    f"Step '{step.name}' Celery task timed out after {timeout}s",
                    details={
                        "handler_ref": handler_ref,
                        "timeout_seconds": timeout,
                        "error_type": error_type,
                        "task_id": getattr(async_result, "id", "unknown"),
                    },
                    step_name=step.name,
                ) from e
            raise StepExecutionError(
                f"Celery execution failed for step '{step.name}': {e}",
                details={
                    "handler_ref": handler_ref,
                    "error_type": error_type,
                    "task_id": getattr(async_result, "id", "unknown"),
                },
                step_name=step.name,
            ) from e

        logger.debug("CeleryExecutor: step '%s' terminé avec succès", step.name)
        return result

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Libère les ressources (connexion broker, etc.)."""
        if self._celery_app is not None:
            try:
                # Fermer les connexions au pool
                pool = getattr(self._celery_app, "pool", None)
                if pool is not None and hasattr(pool, "force_close_all"):
                    pool.force_close_all()
            except Exception:
                pass  # Ne pas propager les erreurs de shutdown
            finally:
                self._celery_app = None
                self._celery_task = None

    @property
    def config(self) -> Any:
        """Retourne la configuration active du CeleryExecutor."""
        return self._config

    def __repr__(self) -> str:
        return (
            f"CeleryExecutor("
            f"broker={self._config.broker_url!r}, "
            f"backend={self._config.result_backend!r}, "
            f"queue={self._config.task_default_queue!r})"
        )
