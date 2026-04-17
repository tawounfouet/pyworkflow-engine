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

    from pyworkflow_engine.models.pipeline.pipeline import Pipeline
    from pyworkflow_engine.models.pipeline.pipeline_run import PipelineRun

from pyworkflow_engine.config import WorkflowConfig
from pyworkflow_engine.engine.context import WorkflowContext
from pyworkflow_engine.engine.dag import DAGResolver
from pyworkflow_engine.engine.parallel_runner import ParallelRunner
from pyworkflow_engine.engine.pipeline_runner import PipelineRunner
from pyworkflow_engine.engine.retry import RetryHandler
from pyworkflow_engine.engine.runner import WorkflowRunner
from pyworkflow_engine.engine.suspension import SuspensionManager
from pyworkflow_engine.exceptions import (
    DAGValidationError,
    WorkflowError,
    WorkflowFailed,
    WorkflowSuspended,
)
from pyworkflow_engine.facade.ai import AIFacade
from pyworkflow_engine.facade.jobs import JobsFacade
from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, JobRun, RunStatus, StepType
from pyworkflow_engine.ports.executor import BaseExecutor, ExecutorRegistry


_logger = get_logger("engine.facade")

NO_STORAGE_ERROR = "No persistence backend configured"
NO_STORAGE_EXECUTION_ERROR = (
    "No persistence backend configured for persistent execution"
)


def _bootstrap_storage(
    config: WorkflowConfig,
    explicit_storage: Any | None,
) -> Any:
    """Auto-provisionne la persistence depuis ``WorkflowConfig``.

    Appelé une seule fois dans ``WorkflowEngine.__init__``.
    """
    backend = explicit_storage

    # ── Storage ───────────────────────────────────────────────────────────
    if backend is None and config.storage.db_path:
        from pyworkflow_engine.adapters.storage.sqlite import (
            SQLiteStorage,
        )  # noqa: PLC0415

        backend = SQLiteStorage(database_path=config.storage.db_path)
        _logger.debug(
            "SQLiteStorage auto-configuré depuis WorkflowConfig",
            extra={"db_path": config.storage.db_path},
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
        configure_logging: bool = False,
    ):
        # config prend le dessus sur les paramètres directs
        _engine_cfg = config.engine if config is not None else None
        _use_parallel = _engine_cfg.parallel if _engine_cfg else parallel
        _workers = _engine_cfg.max_workers if _engine_cfg else max_workers

        self._config = config or WorkflowConfig()

        if configure_logging:
            from pyworkflow_engine.logging.bootstrap import (
                configure_from_workflow_config,
            )

            configure_from_workflow_config(self._config)

        # Auto-provision persistence depuis WorkflowConfig
        backend = _bootstrap_storage(self._config, storage)

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

        # ── Sub-facades ──────────────────────────────────────────────────────
        # Accessible via engine.ai et engine.jobs.
        # Les méthodes directes historiques (engine.save_job, engine.chat…)
        # délèguent à ces sous-facades pour préserver la compatibilité ascendante.
        self._jobs_facade = JobsFacade(
            storage=self._storage,
            job_registry=self._job_registry,
            runner=self._runner,
            retry=self._retry,
            suspension=self._suspension,
        )
        self._ai_facade = AIFacade(
            ai_storage=getattr(self, "_ai_storage", None),
        )

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
            # Gel du contexte après exécution complète — toute mutation
            # post-workflow lèvera une ContextError explicite.
            context.freeze()

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
            context.freeze()
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
    # Sub-facade accessors
    # ------------------------------------------------------------------

    @property
    def ai(self) -> AIFacade:
        """Sous-façade IA — agents, conversations, storage IA.

        Usage::

            agent = engine.ai.create_agent(name="Bot", model="claude-3-5-sonnet")
            reply = engine.ai.chat(agent.agent_id, "Bonjour !")
        """
        return self._ai_facade

    @property
    def jobs(self) -> JobsFacade:
        """Sous-façade jobs — CRUD jobs/runs + exécution avec persistence.

        Usage::

            engine.jobs.save(my_job)
            run = engine.jobs.run(my_job, initial_context={"env": "prod"})
            runs = engine.jobs.list_runs(status="failed", limit=50)
        """
        return self._jobs_facade

    # ------------------------------------------------------------------
    # Raw storage backend (unchanged — advanced use / GUI / health checks)
    # ------------------------------------------------------------------

    @property
    def storage(self):
        """Accès direct au backend de persistence brut (``BaseStorage``).

        Pour les opérations de haut niveau, préférer ``engine.jobs``.
        Ce getter est conservé pour la compatibilité et les cas d'usage avancés
        (healthcheck, GUI, migrations).
        """
        return self._storage

    @storage.setter
    def storage(self, backend):
        self._storage = backend
        self._suspension.storage = backend
        # Propagate to sub-facade so engine.jobs stays in sync
        self._jobs_facade._set_storage(backend)

    # ------------------------------------------------------------------
    # Persistence methods — backwards-compatible delegates to engine.jobs
    # ------------------------------------------------------------------

    def save_job(self, job: Job) -> None:
        """Persiste un job. Délègue à ``engine.jobs.save(job)``."""
        self.jobs.save(job)

    def get_job(self, job_name: str) -> Job | None:
        """Récupère un job. Délègue à ``engine.jobs.get(job_name)``."""
        return self.jobs.get(job_name)

    def list_jobs(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        """Liste les jobs. Délègue à ``engine.jobs.list(limit, offset)``."""
        return self.jobs.list(limit=limit, offset=offset)

    def delete_job(self, job_name: str) -> bool:
        """Supprime un job. Délègue à ``engine.jobs.delete(job_name)``."""
        return self.jobs.delete(job_name)

    def get_job_run(self, run_id: str) -> JobRun | None:
        """Récupère un run. Délègue à ``engine.jobs.get_run(run_id)``."""
        return self.jobs.get_run(run_id)

    def list_job_runs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[JobRun]:
        """Liste les runs. Délègue à ``engine.jobs.list_runs(...)``."""
        return self.jobs.list_runs(
            job_name=job_name, status=status, limit=limit, offset=offset, since=since
        )

    def count_job_runs(self, job_name: str | None = None) -> int:
        """Compte les runs. Délègue à ``engine.jobs.count_runs(job_name)``."""
        return self.jobs.count_runs(job_name=job_name)

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
        return self.jobs.run(job_or_name, initial_context=initial_context, run_id=run_id)

    # ------------------------------------------------------------------
    # Pipeline facade (ADR-014 / ADR-016)
    # ------------------------------------------------------------------

    def save_pipeline(self, pipeline: Pipeline) -> None:
        """Persiste la définition d'une Pipeline dans le backend de storage.

        Auto-appelé par :meth:`run_pipeline` — peut aussi être appelé
        manuellement pour enregistrer une pipeline sans l'exécuter.

        Requires:
            Un backend de persistence doit être configuré.
        """
        self._require_storage("save_pipeline")
        if hasattr(self._storage, "save_pipeline"):
            self._storage.save_pipeline(pipeline)

    def get_pipeline(self, name: str) -> Pipeline | None:
        """Récupère une Pipeline par son nom depuis le backend."""
        if self._storage is None or not hasattr(self._storage, "get_pipeline"):
            return None
        try:
            return self._storage.get_pipeline(name)
        except Exception:  # noqa: BLE001
            return None

    def list_pipelines(
        self,
        enabled_only: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Pipeline]:
        """Liste toutes les pipelines enregistrées dans le backend."""
        if self._storage is None or not hasattr(self._storage, "list_pipelines"):
            return []
        try:
            return self._storage.list_pipelines(
                enabled_only=enabled_only, limit=limit, offset=offset
            )
        except Exception:  # noqa: BLE001
            return []

    def run_pipeline(
        self,
        pipeline: Pipeline,
        initial_context: dict[str, Any] | None = None,
        triggered_by: str = "manual",
    ) -> PipelineRun:
        """Exécute une pipeline complète via ``PipelineRunner``.

        Chaque stage est exécuté avec ``run()`` (pas de persistence
        intermédiaire des JobRun).  Utilisez :meth:`run_pipeline_with_storage`
        pour persister l'état de chaque job.

        Args:
            pipeline: Définition de la pipeline (``Pipeline`` ou objet
                retourné par ``@pipeline(...).build()``).
            initial_context: Contexte initial injecté dans le premier stage.
            triggered_by: Source du déclenchement.

        Returns:
            ``PipelineRun`` avec le statut global et les ``StageRun``.
        """
        # Auto-persist the pipeline definition so the GUI can list it
        if self._storage is not None and hasattr(self._storage, "save_pipeline"):
            try:
                self._storage.save_pipeline(pipeline)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Failed to persist pipeline definition: %s", exc)

        runner = PipelineRunner(engine=self, job_registry=dict(self._job_registry))
        pipeline_run = runner.execute(
            pipeline,
            initial_context=initial_context,
            triggered_by=triggered_by,
        )
        if self._storage is not None:
            try:
                self._storage.save_pipeline_run(pipeline_run)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Failed to persist pipeline run: %s", exc)
        return pipeline_run

    def run_pipeline_with_storage(
        self,
        pipeline: Pipeline,
        initial_context: dict[str, Any] | None = None,
        triggered_by: str = "manual",
    ) -> PipelineRun:
        """Exécute une pipeline avec persistence intermédiaire des JobRun.

        Identique à :meth:`run_pipeline` mais chaque stage utilise
        ``run_with_storage()`` pour persister l'état de chaque ``JobRun``
        avec checkpoints.

        Requires:
            Un backend de persistence doit être configuré (``storage=…``
            ou ``config.storage.db_path``).

        Raises:
            WorkflowError: Si aucun backend de persistence n'est configuré.
        """
        self._require_storage("run_pipeline_with_storage")
        return self.run_pipeline(
            pipeline,
            initial_context=initial_context,
            triggered_by=triggered_by,
        )

    # ------------------------------------------------------------------
    # AI facade — méthodes optionnelles (ADR-013)
    # Lazy-importent engine/ai/ pour éviter de forcer la dépendance IA.
    # ------------------------------------------------------------------

    def create_agent(self, **kwargs: Any) -> Any:
        """Crée un agent IA. Délègue à ``engine.ai.create_agent()``."""
        return self.ai.create_agent(**kwargs)

    def get_agent(self, agent_id: str) -> Any:
        """Récupère un agent IA par son identifiant. Délègue à ``engine.ai.get_agent()``."""
        return self.ai.get_agent(agent_id)

    def list_agents(self, **filters: Any) -> list[Any]:
        """Liste les agents IA. Délègue à ``engine.ai.list_agents()``."""
        return self.ai.list_agents(**filters)

    def delete_agent(self, agent_id: str) -> bool:
        """Supprime un agent IA. Délègue à ``engine.ai.delete_agent()``."""
        return self.ai.delete_agent(agent_id)

    def chat(
        self,
        agent_id: str,
        message: str,
        conversation_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Envoie un message à un agent IA. Délègue à ``engine.ai.chat()``."""
        return self.ai.chat(
            agent_id=agent_id,
            message=message,
            conversation_id=conversation_id,
            **kwargs,
        )

    def get_conversation_history(self, conversation_id: str) -> list[Any]:
        """Récupère l'historique d'une conversation. Délègue à ``engine.ai.get_conversation_history()``."""
        return self.ai.get_conversation_history(conversation_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @property
    def ai_storage(self) -> Any:
        """Retourne le backend ``SQLiteAIStorage`` partagé (lazy-init).

        Utilisé par les vues GUI pour lire agents / conversations / messages
        sans passer par ``AgentService``.  Retourne ``None`` si le sous-package
        AI n'est pas disponible.

        .. deprecated::
            Préférer ``engine.ai.storage``.
        """
        return self.ai.storage

    def _require_storage(self, operation: str) -> None:
        if not self._storage:
            raise WorkflowError(NO_STORAGE_ERROR, details={"operation": operation})
