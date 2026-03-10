"""
Moteur d'exécution de workflow — WorkflowEngine principal.

Le WorkflowEngine orchestre l'exécution des workflows, gère les états,
coordonne les steps, et fournit les capacités de suspension/reprise.

Utilise uniquement la stdlib Python — zero dépendance externe.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List, Set, Callable
from datetime import datetime
import traceback
import uuid

from .models import Job, Step, JobRun, StepRun, StepLog, RunStatus, StepType
from .dag import DAGResolver
from .context import WorkflowContext
from .exceptions import (
    WorkflowError,
    WorkflowSuspended,
    WorkflowFailed,
    StepExecutionError,
    DAGValidationError,
    ContextError,
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
    ):
        """Initialise le moteur de workflow.

        Args:
            default_executor: Executor par défaut pour les steps.
            step_executors: Mapping personnalisé type -> executor.
        """
        self._default_executor = default_executor or self._execute_function_step
        self._step_executors = step_executors or {}
        self._suspended_workflows: Dict[str, JobRun] = {}

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
            # Applique les sorties fournies
            if step_outputs:
                for step_name, output in step_outputs.items():
                    step_run = self._find_step_run(job_run, step_name)
                    if step_run and step_run.status == RunStatus.SUSPENDED:
                        step_run.complete_success(output)

            # Continue l'exécution depuis la suspension
            context = WorkflowContext(job_run)

            # Restaurer les sorties des steps déjà complétées dans le contexte
            for step_run in job_run.step_runs:
                if step_run.status == RunStatus.SUCCESS and step_run.output_data:
                    context.set_step_output(step_run.step_name, step_run.output_data)

            resolver = DAGResolver(job_run.job)

            # Trouve les steps non encore exécutés
            completed_steps = {
                sr.step_name
                for sr in job_run.step_runs
                if sr.status == RunStatus.SUCCESS
            }

            remaining_order = [
                step_name
                for step_name in resolver.get_execution_order()
                if step_name not in completed_steps
            ]

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
                    # Retry sera implémenté dans une version future
                    # Pour l'instant, on ne fait pas de retry automatique
                    pass

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
        # Sélection de l'executor
        executor = self._step_executors.get(step.step_type, self._default_executor)

        # Exécution avec timeout si spécifié
        if step.timeout:
            # Timeout sera géré dans une version future
            # Pour l'instant, pas de timeout automatique
            pass

        return executor(step, context)

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

        try:
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
                    warnings.append(
                        f"Step '{step.name}' has FUNCTION type but no callable"
                    )

        except DAGValidationError:
            raise

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
