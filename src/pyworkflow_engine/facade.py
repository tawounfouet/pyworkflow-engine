"""
WorkflowEngine — façade principale d'orchestration.

Point d'entrée unique pour les utilisateurs. Compose les composants
spécialisés :

- ``engine.runner``     — WorkflowRunner (exécution des steps)
- ``engine.retry``      — RetryHandler (retry)
- ``engine.suspension`` — SuspensionManager (suspension / reprise)

L'API publique est inchangée depuis v0.2.
"""

from __future__ import annotations

import traceback
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

from pyworkflow_engine.engine.context import WorkflowContext
from pyworkflow_engine.engine.dag import DAGResolver
from pyworkflow_engine.engine.parallel_runner import ParallelRunner
from pyworkflow_engine.engine.retry import RetryHandler
from pyworkflow_engine.engine.runner import WorkflowRunner
from pyworkflow_engine.engine.suspension import SuspensionManager
from pyworkflow_engine.exceptions import DAGValidationError, WorkflowError, WorkflowFailed, WorkflowSuspended
from pyworkflow_engine.ports.executor import BaseExecutor, ExecutorRegistry
from pyworkflow_engine.ports.storage import StorageError
from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, JobRun, RunStatus, StepType
from pyworkflow_engine.config import WorkflowConfig

_logger = get_logger("engine.facade")

NO_STORAGE_ERROR = "No persistence backend configured"
NO_STORAGE_EXECUTION_ERROR = (
    "No persistence backend configured for persistent execution"
)


def _bootstrap_from_config(
    config: "WorkflowConfig",
    explicit_storage: Any | None,
) -> Any:
    """Auto-provisionne persistence et logging depuis ``WorkflowConfig``.

    Appelé une seule fois dans ``WorkflowEngine.__init__``. Utilise des
    imports lazy pour éviter les dépendances circulaires avec les adapters.

    Returns:
        Instance de persistence à utiliser (``explicit_storage`` si
        fourni, sinon instance auto-créée depuis ``config.storage``).
    """
    persistence = explicit_storage

    # ── Persistence ──────────────────────────────────────────────────────
    if backend is None and config.storage.db_path:
        from pyworkflow_engine.adapters.storage.sqlite import SQLiteStorage  # noqa: PLC0415
        persistence = SQLiteStorage(database_path=config.storage.db_path)
        _logger.debug(
            "SQLiteStorage auto-configuré depuis WorkflowConfig",
            extra={"db_path": config.storage.db_path},
        )

    # ── Logging ──────────────────────────────────────────────────────────
    log_cfg = config.logging
    needs_setup = (
        log_cfg.level != "INFO"
        or log_cfg.format != "text"
        or log_cfg.log_dir is not None
        or log_cfg.log_to_db
    )
    if needs_setup:
        import logging as _stdlib_logging  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        from pyworkflow_engine.logging.config import LoggingConfig as _LC  # noqa: PLC0415
        from pyworkflow_engine.logging.logger import configure_logging  # noqa: PLC0415

        log_file: str | None = None
        if log_cfg.log_dir:
            log_dir = Path(log_cfg.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = str(log_dir / "pyworkflow.log")

        configure_logging(
            _LC(
                level=log_cfg.level,
                json_output=(log_cfg.format == "json"),
                log_file=log_file,
                log_file_max_bytes=log_cfg.log_file_max_mb * 1024 * 1024,
                log_file_backup_count=log_cfg.log_file_backup_count,
            )
        )

        if log_cfg.log_to_db and config.storage.db_path:
            from pyworkflow_engine.logging.handlers import SQLiteLogHandler  # noqa: PLC0415

            db_handler = SQLiteLogHandler(
                db_path=config.storage.db_path, batch_size=1
            )
            db_handler.setLevel(getattr(_stdlib_logging, log_cfg.level))
            _stdlib_logging.getLogger("pyworkflow_engine").addHandler(db_handler)
            _logger.debug(
                "SQLiteLogHandler auto-configuré depuis WorkflowConfig",
                extra={"db": config.storage.db_path, "table": "workflow_logs"},
            )

    return backend


class WorkflowEngine:
    """Façade principale du moteur de workflow PyWorkflow.

    Compose WorkflowRunner (ou ParallelRunner), RetryHandler et SuspensionManager.
    L'utilisateur n'interagit qu'avec cette classe.

    Args:
        config: Configuration complète du moteur. Si fourni, ``parallel`` et
            ``max_workers`` sont lus depuis ``config.engine``.
        parallel: Si ``True``, utilise ``ParallelRunner``. Ignoré si ``config``
            est fourni.
        max_workers: Nombre maximum de threads par groupe parallèle. Ignoré si
            ``config`` est fourni.

    Examples:
        >>> engine = WorkflowEngine()
        >>> def hello(): return {"message": "Hello!"}
        >>> job = Job(name="Test", steps=[Step(name="greet", handler=hello)])
        >>> result = engine.run(job)
        >>> assert result.status == RunStatus.SUCCESS

        >>> # Via WorkflowConfig
        >>> from pyworkflow_engine.config import WorkflowConfig, EngineConfig
        >>> cfg = WorkflowConfig(engine=EngineConfig(parallel=True, max_workers=4))
        >>> engine = WorkflowEngine(config=cfg)

        >>> # Paramètres directs (inchangé)
        >>> engine = WorkflowEngine(parallel=True, max_workers=4)
    """

    def __init__(
        self,
        config: WorkflowConfig | None = None,
        default_executor: Callable | None = None,
        step_executors: dict[StepType, Callable] | None = None,
        executor_registry: ExecutorRegistry | None = None,
        storage: Any | None = None,
        parallel: bool = False,
        max_workers: int | None = None,
    ):
        # config prend le dessus sur les paramètres directs
        _engine_cfg = config.engine if config is not None else None
        _use_parallel = _engine_cfg.parallel if _engine_cfg else parallel
        _workers = _engine_cfg.max_workers if _engine_cfg else max_workers

        self._config = config or WorkflowConfig()

        # Auto-provision persistence + logging depuis WorkflowConfig
        backend = _bootstrap_from_config(self._config, storage)

        self._storage = backend
        self._executor_registry = executor_registry or ExecutorRegistry()
        runner_kwargs: dict[str, Any] = {
            "executor_registry": self._executor_registry,
            "default_executor": default_executor,
            "step_executors": step_executors or {},
        }
        self._runner: WorkflowRunner = (
            ParallelRunner(max_workers=_workers, **runner_kwargs)
            if _use_parallel
            else WorkflowRunner(**runner_kwargs)
        )
        self._retry = RetryHandler()
        self._suspension = SuspensionManager(backend)
        self._job_registry: dict[str, Job] = {}  # in-memory cache preserving handlers

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def run(
        self,
        job: Job,
        initial_context: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> JobRun:
        """Exécute un workflow complet — exécution pure sans persistence.

        Cette méthode est **sans side-effects de persistence** : elle ne lit
        ni n'écrit dans aucun backend. Tout l'état reste en mémoire dans le
        ``JobRun`` retourné.

        Utilisez :meth:`run_with_storage` si vous souhaitez sauvegarder
        automatiquement le résultat.

        Args:
            job: Définition du job à exécuter.
            initial_context: Données initiales injectées dans le
                ``WorkflowContext`` avant le premier step.
            run_id: ID d'exécution. Généré (UUID4) si non fourni.

        Returns:
            ``JobRun`` avec le résultat final. Le statut est l'un de :
            ``SUCCESS``, ``FAILED``, ou ``SUSPENDED``.

        Raises:
            WorkflowFailed: Si un step échoue sans retry réussi.
            DAGValidationError: Si le graphe de dépendances est invalide.
        """
        job_run = JobRun(
            job_run_id=run_id or str(uuid.uuid4()),
            job=job,
            job_name=job.name,
            job_version=job.version,
            status=RunStatus.PENDING,
            input_data=initial_context or {},
        )

        try:
            try:
                resolver = DAGResolver(job)
                execution_order = resolver.get_execution_order()
            except DAGValidationError as e:
                raise WorkflowFailed(
                    f"Workflow validation failed: {e}",
                    job_name=job.name,
                    details=e.details if hasattr(e, "details") else {},
                ) from e

            context = WorkflowContext(job_run)
            if initial_context:
                for key, value in initial_context.items():
                    context.set(key, value)

            job_run.start_execution()
            self._runner.execute(
                job_run, execution_order, context, retry_handler=self._retry
            )
            job_run.complete_success()

        except WorkflowSuspended:
            self._suspension.suspend(job_run, "Workflow suspended by step execution")

        except Exception as e:
            job_run.complete_failure(str(e))
            _logger.error("WORKFLOW ERROR [%s] %s: %s", job_run.job_run_id, job.name, e)
            if isinstance(e, WorkflowError):
                raise
            raise WorkflowFailed(
                f"Workflow '{job.name}' failed: {e}",
                details={
                    "job_name": job.name,
                    "run_id": job_run.job_run_id,
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                },
            ) from e

        return job_run

    def resume(self, run_id: str, step_outputs: dict[str, Any] | None = None) -> JobRun:
        """Reprend un workflow suspendu."""
        job_run = self._suspension.get_suspended(run_id)
        if job_run is None:
            raise WorkflowError(
                f"No suspended workflow found with ID: {run_id}",
                details={"run_id": run_id},
            )

        try:
            self._suspension.apply_resume_outputs(job_run, step_outputs)
            context = self._suspension.restore_context(job_run, extra_data=step_outputs)
            remaining = self._suspension.calculate_remaining_steps(job_run)

            job_run.status = RunStatus.RUNNING
            self._runner.execute(job_run, remaining, context, retry_handler=self._retry)
            job_run.complete_success()
            self._suspension.remove(run_id)

        except WorkflowSuspended:
            job_run.suspend("Re-suspended during resume")

        except Exception as e:
            job_run.complete_failure(str(e))
            self._suspension.remove(run_id)
            if isinstance(e, WorkflowError):
                raise
            raise WorkflowFailed(
                f"Workflow resume failed: {e}",
                details={"run_id": run_id, "error_type": type(e).__name__},
            ) from e

        return job_run

    def cancel(self, run_id: str) -> bool:
        """Annule un workflow suspendu."""
        if self._suspension.has_suspended(run_id):
            job_run = self._suspension.get_suspended(run_id)
            job_run.cancel()
            self._suspension.remove(run_id)
            return True
        return False

    def get_status(self, run_id: str) -> RunStatus | None:
        job_run = self._suspension.get_suspended(run_id)
        return job_run.status if job_run else None

    def list_suspended(self) -> list[str]:
        return self._suspension.list_suspended()

    # ------------------------------------------------------------------
    # Executor management
    # ------------------------------------------------------------------

    def register_executor(self, name: str, executor: BaseExecutor) -> None:
        self._executor_registry.register(name, executor)

    def get_executor(self, name: str) -> BaseExecutor | None:
        return self._executor_registry.get(name)

    def list_executors(self) -> list[str]:
        return self._executor_registry.list_executors()

    def shutdown_executors(self) -> None:
        self._executor_registry.shutdown_all()

    # ------------------------------------------------------------------
    # Job validation / planning
    # ------------------------------------------------------------------

    def validate_job(self, job: Job) -> list[str]:
        """Valide un job sans l'exécuter. Retourne les avertissements."""
        warnings: list[str] = []
        resolver = DAGResolver(job)
        stats = resolver.get_graph_stats()
        if stats["entry_points"] == 0:
            warnings.append("Job has no entry points")
        if stats["exit_points"] == 0:
            warnings.append("Job has no exit points (unusual but valid)")
        for step in job.steps:
            if step.step_type == StepType.FUNCTION and not step.handler:
                warnings.append(f"Step '{step.name}' has FUNCTION type but no callable")
        return warnings

    def get_execution_plan(self, job: Job) -> dict[str, Any]:
        """Génère un plan d'exécution pour un job."""
        resolver = DAGResolver(job)
        return {
            "job_name": job.name,
            "execution_order": resolver.get_execution_order(),
            "parallel_groups": resolver.get_parallel_groups(),
            "critical_path": resolver.get_critical_path(),
            "entry_points": resolver.get_entry_points(),
            "exit_points": resolver.get_exit_points(),
            "stats": resolver.get_graph_stats(),
            "validation_warnings": self.validate_job(job),
        }

    # ------------------------------------------------------------------
    # Persistence facade
    # ------------------------------------------------------------------

    @property
    def storage(self):
        return self._storage

    @storage.setter
    def persistence(self, backend):
        self._storage = backend
        self._suspension.storage = backend

    def save_job(self, job: Job) -> None:
        self._job_registry[job.name] = job  # preserve handlers for run_with_storage
        self._require_storage("save_job")
        try:
            self._storage.save_job(job)
        except Exception as e:
            raise WorkflowError(
                f"Failed to save job '{job.name}': {e}",
                details={"operation": "save_job", "job_name": job.name},
            ) from e

    def get_job(self, job_name: str) -> Job | None:
        self._require_storage("get_job")
        try:
            return self._storage.get_job(job_name)
        except Exception as e:
            raise WorkflowError(
                f"Failed to get job '{job_name}': {e}",
                details={"operation": "get_job", "job_name": job_name},
            ) from e

    def list_jobs(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        self._require_storage("list_jobs")
        try:
            return self._storage.list_jobs(limit=limit, offset=offset)
        except Exception as e:
            raise WorkflowError(
                f"Failed to list jobs: {e}", details={"operation": "list_jobs"}
            ) from e

    def delete_job(self, job_name: str) -> bool:
        self._require_storage("delete_job")
        try:
            return self._storage.delete_job(job_name)
        except Exception as e:
            raise WorkflowError(
                f"Failed to delete job '{job_name}': {e}",
                details={"operation": "delete_job", "job_name": job_name},
            ) from e

    def get_job_run(self, run_id: str) -> JobRun | None:
        self._require_storage("get_job_run")
        try:
            return self._storage.get_job_run(run_id)
        except Exception as e:
            raise WorkflowError(
                f"Failed to get job run '{run_id}': {e}",
                details={"operation": "get_job_run", "run_id": run_id},
            ) from e

    def list_job_runs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[JobRun]:
        self._require_storage("list_job_runs")
        try:
            return self._storage.list_job_runs(
                job_name=job_name,
                status=status,
                limit=limit,
                offset=offset,
                since=since,
            )
        except Exception as e:
            raise WorkflowError(
                f"Failed to list job runs: {e}",
                details={"operation": "list_job_runs"},
            ) from e

    def run_with_storage(
        self,
        job_or_name: Job | str,
        initial_context: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> JobRun:
        """Exécute un workflow et persiste l'état à chaque étape clé.

        Contrairement à :meth:`run`, cette méthode effectue des **checkpoints
        intermédiaires** :

        1. Sauvegarde initiale du ``JobRun`` (statut ``RUNNING``) avant
           l'exécution des steps.
        2. Checkpoint après chaque step (statut courant + step_runs à jour).
        3. Sauvegarde finale avec le statut terminal (``SUCCESS`` ou
           ``FAILED``).

        En cas d'exception, une dernière tentative de sauvegarde est effectuée
        pour conserver l'état d'échec.

        Args:
            job_or_name: Instance ``Job`` ou nom d'un job enregistré dans
                le backend de persistence.
            initial_context: Données initiales du contexte.
            run_id: ID d'exécution. Généré si non fourni.

        Returns:
            ``JobRun`` avec le résultat final et les step_runs persistés.

        Raises:
            WorkflowError: Si aucun backend de persistence n'est configuré,
                ou si le job est introuvable par nom.
            WorkflowFailed: Si le workflow échoue.
        """
        self._require_storage("run_with_storage")

        if isinstance(job_or_name, str):
            # Prefer in-memory registry: handlers are preserved there.
            # Persistence round-trips lose callables (Step.from_dict sets handler=None).
            job = self._job_registry.get(job_or_name) or self.get_job(job_or_name)
            if not job:
                raise WorkflowError(
                    f"Job '{job_or_name}' not found in persistence backend",
                    details={"job_name": job_or_name},
                )
        else:
            job = job_or_name
            # Auto-save du job si absent du backend — évite les violations FK
            # sur SQLite/SQLAlchemy lors des checkpoints du JobRun.
            self._ensure_job_persisted(job)

        job_run = JobRun(
            job_run_id=run_id or str(uuid.uuid4()),
            job=job,
            job_name=job.name,
            job_version=job.version,
            status=RunStatus.PENDING,
            input_data=initial_context or {},
        )

        # Checkpoint initial — état PENDING enregistré avant tout step
        self._save_job_run_checkpoint(job_run)

        try:
            try:
                resolver = DAGResolver(job)
                execution_order = resolver.get_execution_order()
            except DAGValidationError as e:
                raise WorkflowFailed(
                    f"Workflow validation failed: {e}",
                    job_name=job.name,
                    details=e.details if hasattr(e, "details") else {},
                ) from e

            context = WorkflowContext(job_run)
            if initial_context:
                for key, value in initial_context.items():
                    context.set(key, value)

            job_run.start_execution()
            # Checkpoint : RUNNING
            self._save_job_run_checkpoint(job_run)

            for step_name in execution_order:
                self._runner.execute(
                    job_run,
                    [step_name],
                    context,
                    retry_handler=self._retry,
                )
                # Checkpoint intermédiaire après chaque step
                self._save_job_run_checkpoint(job_run)

            job_run.complete_success()

        except WorkflowSuspended:
            self._suspension.suspend(job_run, "Workflow suspended by step execution")

        except Exception as e:
            job_run.complete_failure(str(e))
            _logger.error("WORKFLOW ERROR [%s] %s: %s", job_run.job_run_id, job.name, e)

        # Sauvegarde finale (état terminal)
        self._save_job_run_checkpoint(job_run)
        return job_run

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_storage(self, operation: str) -> None:
        if not self._storage:
            raise WorkflowError(NO_STORAGE_ERROR, details={"operation": operation})

    def _ensure_job_persisted(self, job: Job) -> None:
        """Sauvegarde le job dans le backend s'il n'y est pas encore.

        Appelé automatiquement par ``run_with_storage()`` pour garantir
        que la contrainte FK (job_run → job) est satisfaite avant le premier
        checkpoint du ``JobRun``.
        """
        try:
            existing = self._storage.get_job(job.name)
            if not existing:
                self._storage.save_job(job)
                _logger.debug("Auto-saved job '%s' before first checkpoint.", job.name)
        except Exception as e:
            _logger.warning(
                "Could not auto-save job '%s' before checkpoint: %s — "
                "FK constraint may fail on SQLite/SQLAlchemy backends.",
                job.name,
                e,
            )

    def _save_job_run_checkpoint(self, job_run: JobRun) -> None:
        """Sauvegarde un checkpoint du JobRun dans le backend de persistence.

        Ne lève jamais d'exception : les erreurs attendues (``StorageError``)
        sont loggées en WARNING, les erreurs inattendues en ERROR. Cela garantit
        que l'exécution du workflow n'est jamais interrompue par un échec de
        persistence.
        """
        if not self._storage:
            return
        try:
            self._storage.save_job_run(job_run)
        except StorageError as e:
            _logger.warning(
                "Checkpoint failed for run '%s' (non-fatal): %s",
                job_run.job_run_id,
                e,
            )
        except Exception as e:
            _logger.error(
                "Unexpected checkpoint error for run '%s': %s",
                job_run.job_run_id,
                e,
            )
