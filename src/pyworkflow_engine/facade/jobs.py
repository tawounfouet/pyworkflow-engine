"""
JobsFacade — sous-façade dédiée à la gestion des jobs et de leurs runs.

Regroupe les opérations de persistance (CRUD jobs/runs) et l'exécution
avec checkpoints (``run()``) dans un objet cohérent accessible via
``engine.jobs``.

Usage::

    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.adapters.storage.sqlite import SQLiteStorage

    engine = WorkflowEngine(storage=SQLiteStorage("workflow.db"))

    # CRUD jobs
    engine.jobs.save(my_job)
    job  = engine.jobs.get("my-job")
    jobs = engine.jobs.list(limit=20)
    engine.jobs.delete("old-job")

    # Exécution avec persistence et checkpoints intermédiaires
    job_run = engine.jobs.run(my_job, initial_context={"env": "prod"})

    # Consultation des runs
    run  = engine.jobs.get_run(job_run.job_run_id)
    runs = engine.jobs.list_runs(status="failed", limit=50)
    n    = engine.jobs.count_runs("my-job")

Compatibilité ascendante :
    Toutes les méthodes directes de ``WorkflowEngine`` (``save_job``,
    ``get_job``, ``run_with_storage``, etc.) restent disponibles.  Elles
    délèguent désormais à cette façade.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from pyworkflow_engine.engine.context import WorkflowContext
from pyworkflow_engine.engine.dag import DAGResolver
from pyworkflow_engine.engine.suspension import SuspensionManager
from pyworkflow_engine.exceptions import (
    DAGValidationError,
    WorkflowError,
    WorkflowFailed,
    WorkflowSuspended,
)
from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, JobRun, RunStatus
from pyworkflow_engine.ports.storage import BaseStorage, StorageError

_logger = get_logger("engine.facade.jobs")


class JobsFacade:
    """Sous-façade dédiée aux opérations de jobs et runs.

    Accessible via ``WorkflowEngine.jobs`` — ne pas instancier directement.

    Regroupe :
    - CRUD des définitions de jobs (save / get / list / delete)
    - Exécution avec checkpoints et persistence (``run()``)
    - Consultation des job runs (get_run / list_runs / count_runs)

    Args:
        storage: Backend de persistence.  Si ``None``, les méthodes qui
            requièrent le storage lèveront un ``WorkflowError``.
        job_registry: Registre en mémoire des handlers (préserve les callables
            que la sérialisation JSON ne peut pas stocker).
        runner: ``WorkflowRunner`` ou ``ParallelRunner`` à utiliser pour
            l'exécution.
        retry: ``RetryHandler`` — ``None`` désactive les retries.
        suspension: ``SuspensionManager`` partagé avec ``WorkflowEngine``.

    Examples:
        >>> engine = WorkflowEngine(storage=SQLiteStorage("wf.db"))
        >>> engine.jobs.save(my_job)
        >>> run = engine.jobs.run(my_job, initial_context={"batch": 42})
        >>> print(run.status)  # RunStatus.SUCCESS
    """

    def __init__(
        self,
        storage: BaseStorage | None,
        job_registry: dict[str, Job],
        runner: Any,
        retry: Any,
        suspension: SuspensionManager,
    ) -> None:
        self._storage = storage
        self._job_registry = job_registry
        self._runner = runner
        self._retry = retry
        self._suspension = suspension

    # ------------------------------------------------------------------
    # Storage sync — kept in sync with WorkflowEngine.storage setter
    # ------------------------------------------------------------------

    def _set_storage(self, backend: BaseStorage | None) -> None:
        """Met à jour le backend (appelé par WorkflowEngine.storage.setter)."""
        self._storage = backend

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_storage(self, operation: str) -> None:
        if not self._storage:
            raise WorkflowError(
                "No persistence backend configured",
                details={"operation": operation},
            )

    def _ensure_job_persisted(self, job: Job) -> None:
        """Sauvegarde le job dans le backend s'il n'y est pas encore.

        Garantit que la contrainte FK ``job_run → job`` est satisfaite avant
        le premier checkpoint du ``JobRun``.
        """
        try:
            existing = self._storage.get_job(job.name)  # type: ignore[union-attr]
            if not existing:
                self._storage.save_job(job)  # type: ignore[union-attr]
                _logger.debug("Auto-saved job '%s' before first checkpoint.", job.name)
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "Could not auto-save job '%s' before checkpoint: %s — "
                "FK constraint may fail on SQLite/SQLAlchemy backends.",
                job.name,
                exc,
            )

    def _checkpoint(self, job_run: JobRun) -> None:
        """Sauvegarde un checkpoint du JobRun sans jamais lever d'exception.

        Les erreurs de persistence sont loggées mais n'interrompent jamais
        l'exécution du workflow.
        """
        if not self._storage:
            return
        try:
            self._storage.save_job_run(job_run)
        except StorageError as exc:
            _logger.warning(
                "Checkpoint failed for run '%s' (non-fatal): %s",
                job_run.job_run_id,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.error(
                "Unexpected checkpoint error for run '%s': %s",
                job_run.job_run_id,
                exc,
            )

    # ------------------------------------------------------------------
    # Job registration (preserves handlers in-memory)
    # ------------------------------------------------------------------

    def register(self, job: Job) -> None:
        """Enregistre un job dans le registre en mémoire ET dans le backend.

        Le registre en mémoire préserve les callables (``Step.handler``) que
        la sérialisation JSON ne peut pas stocker.  Cela permet à
        ``run()`` de retrouver les handlers après un redémarrage via le nom.

        Args:
            job: Job à enregistrer.

        Raises:
            WorkflowError: Si le backend de persistence est absent.
        """
        self._job_registry[job.name] = job
        self._require_storage("register")
        try:
            self._storage.save_job(job)  # type: ignore[union-attr]
        except Exception as exc:
            raise WorkflowError(
                f"Failed to save job '{job.name}': {exc}",
                details={"operation": "save_job", "job_name": job.name},
            ) from exc

    # ------------------------------------------------------------------
    # Job CRUD
    # ------------------------------------------------------------------

    def save(self, job: Job) -> None:
        """Persiste une définition de job dans le backend.

        Équivaut à ``engine.save_job(job)``.

        Note:
            Préférer ``register()`` si les handlers doivent être préservés
            pour une utilisation ultérieure via ``run(name)``.
        """
        self._job_registry[job.name] = job
        self._require_storage("save_job")
        try:
            self._storage.save_job(job)  # type: ignore[union-attr]
        except Exception as exc:
            raise WorkflowError(
                f"Failed to save job '{job.name}': {exc}",
                details={"operation": "save_job", "job_name": job.name},
            ) from exc

    def get(self, job_name: str) -> Job | None:
        """Récupère une définition de job par son nom.

        Équivaut à ``engine.get_job(job_name)``.
        """
        self._require_storage("get_job")
        try:
            return self._storage.get_job(job_name)  # type: ignore[union-attr]
        except Exception as exc:
            raise WorkflowError(
                f"Failed to get job '{job_name}': {exc}",
                details={"operation": "get_job", "job_name": job_name},
            ) from exc

    def list(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        """Liste les définitions de jobs avec pagination optionnelle.

        Équivaut à ``engine.list_jobs(limit, offset)``.
        """
        self._require_storage("list_jobs")
        try:
            return self._storage.list_jobs(limit=limit, offset=offset)  # type: ignore[union-attr]
        except Exception as exc:
            raise WorkflowError(
                f"Failed to list jobs: {exc}", details={"operation": "list_jobs"}
            ) from exc

    def delete(self, job_name: str) -> bool:
        """Supprime une définition de job.

        Équivaut à ``engine.delete_job(job_name)``.

        Returns:
            ``True`` si supprimé, ``False`` s'il n'existait pas.
        """
        self._require_storage("delete_job")
        try:
            return self._storage.delete_job(job_name)  # type: ignore[union-attr]
        except Exception as exc:
            raise WorkflowError(
                f"Failed to delete job '{job_name}': {exc}",
                details={"operation": "delete_job", "job_name": job_name},
            ) from exc

    # ------------------------------------------------------------------
    # Execution with persistence (replaces engine.run_with_storage)
    # ------------------------------------------------------------------

    def run(
        self,
        job_or_name: Job | str,
        initial_context: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> JobRun:
        """Exécute un workflow et persiste l'état à chaque étape clé.

        Équivaut à ``engine.run_with_storage()``, avec un nom plus expressif
        dans le contexte de ``engine.jobs``.

        Effectue des **checkpoints intermédiaires** :

        1. Sauvegarde initiale (statut ``PENDING``) avant l'exécution.
        2. Checkpoint après chaque step (état + step_runs à jour).
        3. Sauvegarde finale (statut terminal ``SUCCESS`` / ``FAILED``).

        IMPORTANT — Idempotence requise :
            En cas de crash entre deux checkpoints, la reprise peut réexécuter
            un step déjà terminé.  Les handlers DOIVENT être idempotents.

        Args:
            job_or_name: Instance ``Job`` ou nom d'un job enregistré.
                Si un nom est fourni, le registre en mémoire est consulté
                en premier (handlers préservés), puis le backend.
            initial_context: Données initiales injectées dans le contexte.
            run_id: ID d'exécution.  Généré (UUID4) si non fourni.

        Returns:
            ``JobRun`` avec le résultat final et les step_runs persistés.

        Raises:
            WorkflowError: Si aucun backend de persistence n'est configuré,
                ou si le job n'est pas trouvable, ou si des handlers manquent.
            WorkflowFailed: Si le workflow échoue.
        """
        self._require_storage("run_with_storage")

        if isinstance(job_or_name, str):
            # Prefer in-memory registry: handlers are preserved there.
            # Persistence round-trips lose callables (Step.from_dict sets handler=None).
            job = self._job_registry.get(job_or_name) or self.get(job_or_name)
            if not job:
                raise WorkflowError(
                    f"Job '{job_or_name}' not found in persistence backend",
                    details={"job_name": job_or_name},
                )
        else:
            job = job_or_name
            self._ensure_job_persisted(job)

        # Validate handlers: steps loaded from storage have handler=None.
        missing = [
            s.name
            for s in job.steps
            if s.handler is None and not getattr(s, "executor_name", None)
        ]
        if missing:
            raise WorkflowError(
                f"Job '{job.name}' has steps without callable handlers: {missing}. "
                "Register the job via engine.jobs.register() before calling "
                "engine.jobs.run(), or pass the Job instance directly.",
                details={"job_name": job.name, "steps_missing_handlers": missing},
            )

        job_run = JobRun(
            job_run_id=run_id or str(uuid.uuid4()),
            job=job,
            job_name=job.name,
            job_version=job.version,
            status=RunStatus.PENDING,
            input_data=initial_context or {},
        )

        # Checkpoint initial — état PENDING
        self._checkpoint(job_run)

        try:
            try:
                resolver = DAGResolver(job)
                execution_order = resolver.get_execution_order()
            except DAGValidationError as exc:
                raise WorkflowFailed(
                    f"Workflow validation failed: {exc}",
                    job_name=job.name,
                    details=exc.details if hasattr(exc, "details") else {},
                ) from exc

            context = WorkflowContext(job_run)
            if initial_context:
                for key, value in initial_context.items():
                    context.set(key, value)

            job_run.start_execution()
            self._checkpoint(job_run)  # Checkpoint : RUNNING

            for step_name in execution_order:
                self._runner.execute(
                    job_run,
                    [step_name],
                    context,
                    retry_handler=self._retry,
                )
                self._checkpoint(job_run)  # Checkpoint intermédiaire

            job_run.complete_success()

        except WorkflowSuspended:
            self._suspension.suspend(job_run, "Workflow suspended by step execution")

        except Exception as exc:  # noqa: BLE001
            job_run.complete_failure(str(exc))
            _logger.error(
                "WORKFLOW ERROR [%s] %s: %s", job_run.job_run_id, job.name, exc
            )

        # Sauvegarde finale (état terminal)
        self._checkpoint(job_run)
        return job_run

    # ------------------------------------------------------------------
    # Job runs — consultation
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> JobRun | None:
        """Récupère un job run par son identifiant.

        Équivaut à ``engine.get_job_run(run_id)``.
        """
        self._require_storage("get_job_run")
        try:
            return self._storage.get_job_run(run_id)  # type: ignore[union-attr]
        except Exception as exc:
            raise WorkflowError(
                f"Failed to get job run '{run_id}': {exc}",
                details={"operation": "get_job_run", "run_id": run_id},
            ) from exc

    def list_runs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[JobRun]:
        """Liste les job runs avec filtrage optionnel.

        Équivaut à ``engine.list_job_runs()``.
        """
        self._require_storage("list_job_runs")
        try:
            return self._storage.list_job_runs(  # type: ignore[union-attr]
                job_name=job_name,
                status=status,
                limit=limit,
                offset=offset,
                since=since,
            )
        except Exception as exc:
            raise WorkflowError(
                f"Failed to list job runs: {exc}",
                details={"operation": "list_job_runs"},
            ) from exc

    def count_runs(self, job_name: str | None = None) -> int:
        """Retourne le nombre total de job runs sans charger les données.

        Équivaut à ``engine.count_job_runs()``.
        """
        self._require_storage("count_job_runs")
        try:
            return self._storage.get_job_run_count(job_name=job_name)  # type: ignore[union-attr]
        except Exception as exc:
            raise WorkflowError(
                f"Failed to count job runs: {exc}",
                details={"operation": "count_job_runs"},
            ) from exc
