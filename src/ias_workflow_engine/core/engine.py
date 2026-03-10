"""
Moteur d'exécution de workflow — WorkflowEngine principal.

Le WorkflowEngine orchestre l'exécution des workflows, gère les états,
coordonne les steps, et fournit les capacités de suspension/reprise.

Utilise uniquement la stdlib Python — zero dépendance externe.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List, Set, Callable, Union
from datetime import datetime
import traceback
import uuid

from .models import Job, Step, JobRun, StepRun, StepLog, RunStatus, StepType
from .dag import DAGResolver
from .context import WorkflowContext
from .executors import BaseExecutor, ExecutorRegistry
from .exceptions import (
    WorkflowError,
    WorkflowSuspended,
    WorkflowFailed,
    StepExecutionError,
    DAGValidationError,
    ContextError,
)

# Constants
NO_PERSISTENCE_ERROR = "No persistence backend configured"
NO_PERSISTENCE_EXECUTION_ERROR = (
    "No persistence backend configured for persistent execution"
)


class WorkflowEngine:
    """Moteur d'exécution de workflow principal.

    Le WorkflowEngine gère l'exécution complète des workflows:
    - Résolution des dépendances avec DAGResolver
    - Exécution séquentielle des steps
    - Gestion des états et transitions
    - Suspension/reprise des workflows
    - Gestion des erreurs et retry
    - Logging et traçabilité

    L'engine est synchrone par design pour la simplicité. Les capacités
    asynchrones peuvent être ajoutées via des executors externes.

    Attributes:
        _default_executor: Executor par défaut pour les steps.
        _step_executors: Mapping type -> executor pour personnalisation.
        _suspended_workflows: Workflows en cours de suspension.

    Examples:
        >>> engine = WorkflowEngine()
        >>>
        >>> def hello():
        ...     return {"message": "Hello World!"}
        >>>
        >>> job = Job(name="Test", steps=[
        ...     Step(name="greet", callable=hello)
        ... ])
        >>>
        >>> result = engine.run(job)
        >>> assert result.status == RunStatus.SUCCESS
    """

    def __init__(
        self,
        default_executor: Optional[Callable] = None,
        step_executors: Optional[Dict[StepType, Callable]] = None,
        executor_registry: Optional[ExecutorRegistry] = None,
        persistence: Optional[Any] = None,
    ):
        """Initialise le moteur de workflow.

        Args:
            default_executor: Executor par défaut pour les steps.
            step_executors: Mapping personnalisé type -> executor.
            executor_registry: Registry for advanced executors.
            persistence: Persistence backend for storing workflow data.
        """
        self._default_executor = default_executor or self._execute_function_step
        self._step_executors = step_executors or {}
        self._executor_registry = executor_registry or ExecutorRegistry()
        self._suspended_workflows: Dict[str, JobRun] = {}
        self._persistence = persistence

    def run(
        self,
        job: Job,
        initial_context: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> JobRun:
        """Exécute un workflow complet.

        Args:
            job: Définition du job à exécuter.
            initial_context: Données initiales du contexte.
            run_id: ID d'exécution (généré si non fourni).

        Returns:
            JobRun avec le résultat de l'exécution.

        Raises:
            WorkflowError: En cas d'erreur d'exécution.
        """
        # Création du JobRun
        job_run = JobRun(
            job_run_id=run_id or str(uuid.uuid4()),
            job=job,
            job_name=job.name,
            job_version=job.version,
            status=RunStatus.PENDING,
            input_data=initial_context or {},
        )

        try:
            # Validation du DAG
            try:
                resolver = DAGResolver(job)
                execution_order = resolver.get_execution_order()
            except DAGValidationError as e:
                # Wrap DAG validation errors in WorkflowFailed
                raise WorkflowFailed(
                    f"Workflow validation failed: {e}",
                    job_name=job.name,
                    details=e.details if hasattr(e, "details") else {},
                ) from e

            # Initialisation du contexte
            context = WorkflowContext(job_run)
            if initial_context:
                for key, value in initial_context.items():
                    context.set(key, value)

            # Démarrage de l'exécution
            job_run.start_execution()

            # Exécution des steps dans l'ordre topologique
            self._execute_steps(job_run, execution_order, context)

            # Succès complet
            job_run.complete_success()

        except WorkflowSuspended:
            # Suspension demandée
            job_run.suspend("Workflow suspended by step execution")
            self._suspended_workflows[job_run.job_run_id] = job_run

        except Exception as e:
            # Échec du workflow
            job_run.complete_failure(str(e))

            # Log de l'erreur
            self._log_workflow_error(job, job_run, e)

            # Re-raise si c'est une WorkflowError, sinon wrap
            if isinstance(e, WorkflowError):
                raise
            else:
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

    def resume(
        self, run_id: str, step_outputs: Optional[Dict[str, Any]] = None
    ) -> JobRun:
        """Reprend un workflow suspendu.

        Args:
            run_id: ID du workflow à reprendre.
            step_outputs: Sorties des steps en attente.

        Returns:
            JobRun mis à jour après reprise.

        Raises:
            WorkflowError: Si le workflow n'est pas suspendu ou autres erreurs.
        """
        if run_id not in self._suspended_workflows:
            raise WorkflowError(
                f"No suspended workflow found with ID: {run_id}",
                details={"run_id": run_id},
            )

        job_run = self._suspended_workflows[run_id]

        try:
            self._apply_resume_outputs(job_run, step_outputs)
            context = self._restore_workflow_context(job_run)
            remaining_order = self._calculate_remaining_steps(job_run)

            # Reprend l'exécution
            job_run.status = RunStatus.RUNNING
            self._execute_steps(job_run, remaining_order, context)

            # Succès complet
            job_run.complete_success()
            del self._suspended_workflows[run_id]

        except WorkflowSuspended:
            # Re-suspension
            job_run.suspend("Re-suspended during resume")

        except Exception as e:
            # Échec à la reprise
            job_run.complete_failure(str(e))
            del self._suspended_workflows[run_id]

            if isinstance(e, WorkflowError):
                # Re-raise WorkflowError as-is
                raise
            else:
                raise WorkflowFailed(
                    f"Workflow resume failed: {e}",
                    details={"run_id": run_id, "error_type": type(e).__name__},
                ) from e

        return job_run

    def cancel(self, run_id: str) -> bool:
        """Annule un workflow en cours ou suspendu.

        Args:
            run_id: ID du workflow à annuler.

        Returns:
            True si le workflow a été annulé avec succès.
        """
        if run_id in self._suspended_workflows:
            job_run = self._suspended_workflows[run_id]
            job_run.cancel()
            del self._suspended_workflows[run_id]
            return True

        return False

    def get_status(self, run_id: str) -> Optional[RunStatus]:
        """Retourne le statut d'un workflow.

        Args:
            run_id: ID du workflow.

        Returns:
            Statut du workflow ou None si non trouvé.
        """
        if run_id in self._suspended_workflows:
            return self._suspended_workflows[run_id].status

        return None

    def list_suspended(self) -> List[str]:
        """Liste les IDs des workflows suspendus.

        Returns:
            Liste des IDs des workflows en cours de suspension.
        """
        return list(self._suspended_workflows.keys())

    def register_executor(self, name: str, executor: BaseExecutor) -> None:
        """Register an advanced executor.

        Args:
            name: Executor name.
            executor: Executor instance.
        """
        self._executor_registry.register(name, executor)

    def get_executor(self, name: str) -> Optional[BaseExecutor]:
        """Get registered executor by name.

        Args:
            name: Executor name.

        Returns:
            Executor instance or None if not found.
        """
        return self._executor_registry.get(name)

    def list_executors(self) -> List[str]:
        """List all registered executor names.

        Returns:
            List of executor names.
        """
        return self._executor_registry.list_executors()

    def shutdown_executors(self) -> None:
        """Shutdown all registered executors."""
        self._executor_registry.shutdown_all()

    def _apply_resume_outputs(
        self, job_run: JobRun, step_outputs: Optional[Dict[str, Any]]
    ) -> None:
        """Applique les sorties fournies lors de la reprise.

        Args:
            job_run: JobRun en cours de reprise.
            step_outputs: Sorties à appliquer.
        """
        if step_outputs:
            for step_name, output in step_outputs.items():
                step_run = self._find_step_run(job_run, step_name)
                if step_run and step_run.status == RunStatus.SUSPENDED:
                    step_run.complete_success(output)

    def _restore_workflow_context(self, job_run: JobRun) -> WorkflowContext:
        """Restaure le contexte de workflow depuis les étapes complétées.

        Args:
            job_run: JobRun à restaurer.

        Returns:
            Contexte de workflow restauré.
        """
        context = WorkflowContext(job_run)

        # Restaurer les sorties des steps déjà complétées dans le contexte
        for step_run in job_run.step_runs:
            if step_run.status == RunStatus.SUCCESS and step_run.output_data:
                context.set_step_output(step_run.step_name, step_run.output_data)

        return context

    def _calculate_remaining_steps(self, job_run: JobRun) -> List[str]:
        """Calcule les steps restants à exécuter lors d'une reprise.

        Args:
            job_run: JobRun en cours de reprise.

        Returns:
            Liste ordonnée des steps restants.
        """
        resolver = DAGResolver(job_run.job)

        # Trouve les steps non encore exécutés
        completed_steps = {
            sr.step_name for sr in job_run.step_runs if sr.status == RunStatus.SUCCESS
        }

        return [
            step_name
            for step_name in resolver.get_execution_order()
            if step_name not in completed_steps
        ]

    def _execute_steps(
        self, job_run: JobRun, execution_order: List[str], context: WorkflowContext
    ) -> None:
        """Exécute une série de steps dans l'ordre donné.

        Args:
            job_run: Instance JobRun en cours.
            execution_order: Liste ordonnée des noms de steps.
            context: Contexte d'exécution.

        Raises:
            WorkflowSuspended: Si un step demande une suspension.
            StepExecutionError: Si un step échoue.
        """
        # Index des steps par nom
        steps_by_name = {step.name: step for step in job_run.job.steps}

        for step_name in execution_order:
            step = steps_by_name[step_name]

            # Vérification des conditions d'exécution
            if not self._should_execute_step(step, context):
                continue

            # Création du StepRun
            step_run = StepRun(
                step_name=step.name,
                job_run_id=job_run.job_run_id,
                status=RunStatus.PENDING,
            )
            job_run.step_runs.append(step_run)

            try:
                # Exécution du step
                step_run.start_execution()
                result = self._execute_step(step, context)

                # Succès
                step_run.complete_success(result or {})

                # Mise à jour du contexte
                context.set_step_output(step.name, result)

            except WorkflowSuspended as e:
                # Suspension demandée
                step_run.suspend(str(e))
                raise

            except Exception as e:
                # Échec du step
                step_run.complete_failure(str(e))

                # Log détaillé de l'erreur
                self._log_step_error(step_run, e)

                # Gestion des retry
                if step.retry_count > 0:
                    # Implémenter le retry avec une approche simple
                    retry_success = self._retry_step_execution(step, step_run, context)
                    if retry_success:
                        continue  # Le retry a réussi, passer au step suivant
                    # Si le retry a échoué, continuer avec l'erreur originale

                # Propage l'erreur
                raise StepExecutionError(
                    f"Step '{step.name}' failed: {e}",
                    details={
                        "step_name": step.name,
                        "job_name": job_run.job.name,
                        "run_id": job_run.job_run_id,
                        "error_type": type(e).__name__,
                        "retry_count": step.retry_count,
                    },
                    job_name=job_run.job.name,
                    step_name=step.name,
                ) from e

    def _execute_step(self, step: Step, context: WorkflowContext) -> Any:
        """Exécute un step individuel.

        Args:
            step: Définition du step.
            context: Contexte d'exécution.

        Returns:
            Résultat de l'exécution du step.

        Raises:
            StepExecutionError: Si l'exécution échoue.
            WorkflowSuspended: Si le step demande une suspension.
        """
        # Check for custom executor name in step configuration
        if hasattr(step, "executor_name") and step.executor_name:
            advanced_executor = self._executor_registry.get(step.executor_name)
            if advanced_executor:
                return advanced_executor.execute(step, context)

        # Sélection de l'executor standard
        executor = self._step_executors.get(step.step_type, self._default_executor)

        # Exécution avec timeout si spécifié
        if step.timeout:
            return self._execute_with_timeout(step, context, executor)
        else:
            return executor(step, context)

    def _execute_with_timeout(
        self, step: Step, context: WorkflowContext, executor: Callable
    ) -> Any:
        """Exécute un step avec timeout.

        Args:
            step: Step à exécuter.
            context: Contexte d'exécution.
            executor: Executor à utiliser.

        Returns:
            Résultat de l'exécution.

        Raises:
            StepExecutionError: Si l'exécution échoue ou timeout.
        """
        import threading
        import time
        from queue import Queue, Empty

        result_queue = Queue()
        exception_queue = Queue()

        def target():
            """Thread target pour l'exécution du step."""
            try:
                result = executor(step, context)
                result_queue.put(result)
            except Exception as e:
                exception_queue.put(e)

        # Démarrer l'exécution dans un thread séparé
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

        # Attendre avec timeout
        timeout_seconds = step.timeout.total_seconds()
        thread.join(timeout_seconds)

        if thread.is_alive():
            # Timeout atteint
            raise StepExecutionError(
                f"Step '{step.name}' timed out after {timeout_seconds} seconds",
                details={
                    "step_name": step.name,
                    "timeout_seconds": timeout_seconds,
                    "error_type": "TimeoutError",
                },
                step_name=step.name,
            )

        # Vérifier le résultat
        if not exception_queue.empty():
            # Une exception s'est produite
            raise exception_queue.get()

        if not result_queue.empty():
            # Succès
            return result_queue.get()

        # Cas imprévu - ni résultat ni exception
        raise StepExecutionError(
            f"Step '{step.name}' completed unexpectedly without result",
            step_name=step.name,
        )

    def _execute_function_step(self, step: Step, context: WorkflowContext) -> Any:
        """Executor par défaut pour les steps FUNCTION.

        Args:
            step: Step à exécuter.
            context: Contexte d'exécution.

        Returns:
            Résultat de la fonction.

        Raises:
            StepExecutionError: Si la fonction échoue.
        """
        if not step.callable:
            raise StepExecutionError(
                f"Step '{step.name}' has no callable function", step_name=step.name
            )

        try:
            # Appel de la fonction avec le contexte
            if step.callable.__code__.co_argcount > 0:
                # Fonction accepte des arguments - passe le contexte
                return step.callable(context)
            else:
                # Fonction sans arguments
                return step.callable()

        except WorkflowSuspended:
            # WorkflowSuspended should be re-raised as-is
            raise
        except Exception as e:
            raise StepExecutionError(
                f"Function execution failed in step '{step.name}': {e}",
                details={
                    "function_name": getattr(step.callable, "__name__", "unknown"),
                    "error_type": type(e).__name__,
                },
                step_name=step.name,
            ) from e

    def _should_execute_step(self, step: Step, context: WorkflowContext) -> bool:
        """Détermine si un step doit être exécuté.

        Args:
            step: Step à évaluer.
            context: Contexte d'exécution.

        Returns:
            True si le step doit être exécuté.
        """
        if step.condition:
            try:
                # Évaluation de la condition
                context_data = context.to_dict()
                return bool(step.condition(context_data))
            except Exception as e:
                # En cas d'erreur dans la condition, on n'exécute pas
                self._log_condition_error(step, e)
                return False

        return True

    def _find_step_run(self, job_run: JobRun, step_name: str) -> Optional[StepRun]:
        """Trouve un StepRun par nom de step.

        Args:
            job_run: JobRun à chercher.
            step_name: Nom du step.

        Returns:
            StepRun correspondant ou None.
        """
        for step_run in job_run.step_runs:
            if step_run.step_name == step_name:
                return step_run
        return None

    def _retry_step_execution(
        self, step: Step, step_run: StepRun, context: WorkflowContext
    ) -> bool:
        """Tente de réexécuter un step avec retry.

        Args:
            step: Step à réexécuter.
            step_run: StepRun associé.
            context: Contexte de workflow.

        Returns:
            True si le retry a réussi, False sinon.
        """
        import time

        for _ in range(step.retry_count):
            # Attendre le délai de retry
            if step.retry_delay.total_seconds() > 0:
                time.sleep(step.retry_delay.total_seconds())

            # Incrémenter le compteur de retry
            step_run.retry_count += 1

            # Log de la tentative
            step_run.add_log(
                "INFO",
                f"Retrying step - attempt {step_run.retry_count}/{step.retry_count}",
            )

            # Réinitialiser pour retry
            step_run.status = RunStatus.RUNNING
            step_run.error = None

            try:
                # Tenter l'exécution
                output = self._execute_step(step, context)
                step_run.complete_success(output)
                context.set_step_output(step.name, output)
                return True  # Succès!

            except Exception as retry_error:
                # Échec du retry
                step_run.add_log(
                    "ERROR", f"Retry {step_run.retry_count} failed: {retry_error}"
                )

                # Si c'est la dernière tentative, garder l'erreur
                if step_run.retry_count >= step.retry_count:
                    step_run.complete_failure(str(retry_error))
                    self._log_step_error(step_run, retry_error)
                    return False

                # Sinon, continuer à la tentative suivante
                continue

        return False  # Tous les retries ont échoué

    def _log_workflow_error(self, job: Job, job_run: JobRun, error: Exception) -> None:
        """Log une erreur au niveau workflow.

        Args:
            job: Définition du job.
            job_run: JobRun en erreur.
            error: Exception capturée.
        """
        # Intégrer avec le système de logging
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"WORKFLOW ERROR [{job_run.job_run_id}] {job.name}: {error}")

    def _log_step_error(self, step_run: StepRun, error: Exception) -> None:
        """Log une erreur au niveau step.

        Args:
            step_run: StepRun en erreur.
            error: Exception capturée.
        """
        # Intégrer avec le système de logging
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"STEP ERROR [{step_run.step_name}]: {error}")

    def _log_condition_error(self, step: Step, error: Exception) -> None:
        """Log une erreur de condition.

        Args:
            step: Step avec la condition en erreur.
            error: Exception capturée.
        """
        # Intégrer avec le système de logging
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"CONDITION ERROR [{step.name}]: {error}")

    def validate_job(self, job: Job) -> List[str]:
        """Valide un job sans l'exécuter.

        Args:
            job: Job à valider.

        Returns:
            Liste des messages d'avertissement (vide si valide).

        Raises:
            DAGValidationError: Si le job est invalide.
        """
        warnings = []

        # Validation du DAG
        resolver = DAGResolver(job)

        # Vérifications additionnelles
        stats = resolver.get_graph_stats()

        if stats["entry_points"] == 0:
            warnings.append("Job has no entry points (all steps have dependencies)")

        if stats["exit_points"] == 0:
            warnings.append("Job has no exit points (unusual but valid)")

        # Vérification des callables pour les steps FUNCTION
        for step in job.steps:
            if step.step_type == StepType.FUNCTION and not step.callable:
                warnings.append(f"Step '{step.name}' has FUNCTION type but no callable")

        return warnings

    def get_execution_plan(self, job: Job) -> Dict[str, Any]:
        """Génère un plan d'exécution pour un job.

        Args:
            job: Job à analyser.

        Returns:
            Dictionnaire avec le plan d'exécution détaillé.
        """
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

    # ============================================================================
    # PERSISTENCE INTEGRATION
    # ============================================================================

    @property
    def persistence(self):
        """Get the current persistence backend."""
        return self._persistence

    @persistence.setter
    def persistence(self, backend):
        """Set the persistence backend."""
        self._persistence = backend

    def save_job(self, job: Job) -> None:
        """Save a job definition using the persistence backend.

        Args:
            job: Job to save.

        Raises:
            WorkflowError: If no persistence backend configured.
        """
        if not self._persistence:
            raise WorkflowError(
                NO_PERSISTENCE_ERROR,
                details={"operation": "save_job", "job_name": job.name},
            )

        try:
            self._persistence.save_job(job)
        except Exception as e:
            raise WorkflowError(
                f"Failed to save job '{job.name}': {e}",
                details={
                    "operation": "save_job",
                    "job_name": job.name,
                    "error": str(e),
                },
            ) from e

    def get_job(self, job_name: str) -> Optional[Job]:
        """Retrieve a job definition by name.

        Args:
            job_name: Name of the job to retrieve.

        Returns:
            Job if found, None otherwise.

        Raises:
            WorkflowError: If no persistence backend configured.
        """
        if not self._persistence:
            raise WorkflowError(
                NO_PERSISTENCE_ERROR,
                details={"operation": "get_job", "job_name": job_name},
            )

        try:
            return self._persistence.get_job(job_name)
        except Exception as e:
            raise WorkflowError(
                f"Failed to get job '{job_name}': {e}",
                details={"operation": "get_job", "job_name": job_name, "error": str(e)},
            ) from e

    def list_jobs(self, limit: Optional[int] = None, offset: int = 0) -> List[Job]:
        """List job definitions using the persistence backend.

        Args:
            limit: Maximum number of jobs to return.
            offset: Number of jobs to skip.

        Returns:
            List of jobs.

        Raises:
            WorkflowError: If no persistence backend configured.
        """
        if not self._persistence:
            raise WorkflowError(
                NO_PERSISTENCE_ERROR, details={"operation": "list_jobs"}
            )

        try:
            return self._persistence.list_jobs(limit=limit, offset=offset)
        except Exception as e:
            raise WorkflowError(
                f"Failed to list jobs: {e}",
                details={"operation": "list_jobs", "error": str(e)},
            ) from e

    def delete_job(self, job_name: str) -> bool:
        """Delete a job definition using the persistence backend.

        Args:
            job_name: Name of the job to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            WorkflowError: If no persistence backend configured.
        """
        if not self._persistence:
            raise WorkflowError(
                NO_PERSISTENCE_ERROR,
                details={"operation": "delete_job", "job_name": job_name},
            )

        try:
            return self._persistence.delete_job(job_name)
        except Exception as e:
            raise WorkflowError(
                f"Failed to delete job '{job_name}': {e}",
                details={
                    "operation": "delete_job",
                    "job_name": job_name,
                    "error": str(e),
                },
            ) from e

    def get_job_run(self, run_id: str) -> Optional[JobRun]:
        """Retrieve a job run by ID using the persistence backend.

        Args:
            run_id: ID of the job run to retrieve.

        Returns:
            JobRun if found, None otherwise.

        Raises:
            WorkflowError: If no persistence backend configured.
        """
        if not self._persistence:
            raise WorkflowError(
                NO_PERSISTENCE_ERROR,
                details={"operation": "get_job_run", "run_id": run_id},
            )

        try:
            return self._persistence.get_job_run(run_id)
        except Exception as e:
            raise WorkflowError(
                f"Failed to get job run '{run_id}': {e}",
                details={"operation": "get_job_run", "run_id": run_id, "error": str(e)},
            ) from e

    def list_job_runs(
        self,
        job_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        since: Optional[datetime] = None,
    ) -> List[JobRun]:
        """List job runs using the persistence backend.

        Args:
            job_name: Filter by job name.
            status: Filter by status.
            limit: Maximum number of runs to return.
            offset: Number of runs to skip.
            since: Only return runs created after this datetime.

        Returns:
            List of job runs.

        Raises:
            WorkflowError: If no persistence backend configured.
        """
        if not self._persistence:
            raise WorkflowError(
                NO_PERSISTENCE_ERROR,
                details={"operation": "list_job_runs"},
            )

        try:
            return self._persistence.list_job_runs(
                job_name=job_name,
                status=status,
                limit=limit,
                offset=offset,
                since=since,
            )
        except Exception as e:
            raise WorkflowError(
                f"Failed to list job runs: {e}",
                details={"operation": "list_job_runs", "error": str(e)},
            ) from e

    def run_with_persistence(
        self,
        job_or_name: Union[Job, str],
        initial_context: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> JobRun:
        """Run a workflow with automatic persistence of the job run.

        This method automatically saves the job run state to the persistence
        backend at key points during execution, enabling resume capabilities
        and workflow monitoring.

        Args:
            job_or_name: Job definition or name of saved job to execute.
            initial_context: Initial context data.
            run_id: Optional run ID (generated if not provided).

        Returns:
            JobRun with execution results.

        Raises:
            WorkflowError: If persistence is not configured or execution fails.
        """
        if not self._persistence:
            raise WorkflowError(
                NO_PERSISTENCE_EXECUTION_ERROR,
                details={"operation": "run_with_persistence"},
            )

        # Resolve job
        if isinstance(job_or_name, str):
            job = self.get_job(job_or_name)
            if not job:
                raise WorkflowError(
                    f"Job '{job_or_name}' not found in persistence backend",
                    details={"job_name": job_or_name},
                )
        else:
            job = job_or_name

        # Execute workflow with persistence
        try:
            job_run = self.run(job, initial_context=initial_context, run_id=run_id)

            # Save final job run state
            self._persistence.save_job_run(job_run)

            return job_run

        except Exception as e:
            # Try to save failed job run if it exists
            if "job_run" in locals():
                try:
                    self._persistence.save_job_run(job_run)
                except Exception:
                    # Don't fail workflow execution due to persistence errors
                    # Just log and continue (logging would be added here)
                    pass
            raise

    def _save_job_run_checkpoint(self, job_run: JobRun) -> None:
        """Save a checkpoint of the job run state.

        This is called internally during workflow execution to save
        intermediate states for resume capability.

        Args:
            job_run: Job run to checkpoint.
        """
        if self._persistence:
            try:
                self._persistence.save_job_run(job_run)
            except Exception:
                # Don't fail workflow execution due to persistence errors
                # Just log and continue (logging would be added here)
                pass
