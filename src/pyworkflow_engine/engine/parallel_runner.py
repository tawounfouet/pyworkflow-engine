"""
ParallelRunner — exécution parallèle des steps d'un workflow.

Utilise ``DAGResolver.get_parallel_groups()`` pour identifier les steps
sans dépendances entre eux et ``concurrent.futures.ThreadPoolExecutor``
pour les exécuter simultanément groupe par groupe.

Zéro dépendance externe — stdlib uniquement (concurrent.futures, threading).
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from pyworkflow_engine.exceptions import StepExecutionError, WorkflowSuspended
from pyworkflow_engine.models import JobRun, RunStatus, StepRun
from pyworkflow_engine.engine.dag import DAGResolver
from pyworkflow_engine.engine.runner import WorkflowRunner

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext
    from pyworkflow_engine.engine.retry import RetryHandler


class ParallelRunner(WorkflowRunner):
    """Exécute les steps d'un workflow par groupes parallèles.

    Remplace ``WorkflowRunner`` en exploitant les groupes parallèles du DAG :
    chaque groupe contient des steps sans dépendances mutuelles et peut donc
    être exécuté simultanément via ``ThreadPoolExecutor``.

    Le séquencement *entre* groupes reste strict : le groupe N+1 ne démarre
    que lorsque tous les futures du groupe N sont résolus.

    Thread-safety : les mutations partagées (``job_run.step_runs``,
    ``context.set_step_output``) sont protégées par un ``threading.Lock``.

    Args:
        max_workers: Nombre maximum de threads par groupe. ``None`` laisse
            Python choisir (``min(32, os.cpu_count() + 4)``).
        **kwargs: Transmis à ``WorkflowRunner.__init__``.

    Examples:
        >>> runner = ParallelRunner(max_workers=4)
        >>> engine = WorkflowEngine(runner=runner)
        >>> result = engine.run(job)
    """

    def __init__(self, max_workers: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._max_workers = max_workers
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API (override)
    # ------------------------------------------------------------------

    def execute(
        self,
        job_run: JobRun,
        execution_order: list[str],
        context: WorkflowContext,
        retry_handler: RetryHandler | None = None,
    ) -> None:
        """Exécute les steps par groupes parallèles.

        Les groupes sont calculés depuis ``job_run.job`` via ``DAGResolver``.
        Le paramètre ``execution_order`` est utilisé comme filtre : seuls les
        steps présents dans cette liste sont exécutés. Cela permet la reprise
        correcte après une suspension sans ré-exécuter les steps déjà terminés.

        Un unique ``ThreadPoolExecutor`` est créé pour toute la durée
        d'exécution du workflow afin d'éviter le coût de création/destruction
        d'un pool par groupe parallèle.

        Args:
            job_run: Instance JobRun en cours.
            execution_order: Liste des noms de steps à exécuter. Peut être un
                sous-ensemble du DAG complet (ex. steps restants lors d'une reprise).
            context: Contexte d'exécution partagé entre les steps.
            retry_handler: RetryHandler optionnel.

        Raises:
            WorkflowSuspended: Si un step demande une suspension.
            StepExecutionError: Si un step échoue (premier échec rapporté).
        """
        resolver = DAGResolver(job_run.job)
        parallel_groups = resolver.get_parallel_groups()
        steps_by_name = {step.name: step for step in job_run.job.steps}

        # N'exécuter que les steps présents dans execution_order.
        # En exécution normale : tous les steps. En reprise : steps restants seulement.
        remaining = set(execution_order)

        # Pool unique partagé sur tous les groupes — évite la création/destruction
        # répétée (coût ~5-10 ms par pool) pour les workflows à nombreux groupes.
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            for group in parallel_groups:
                # Filtrer le groupe aux steps qui restent à exécuter
                filtered_group = [s for s in group if s in remaining]
                if not filtered_group:
                    # Groupe entièrement terminé (ou hors-scope) — on passe
                    continue
                self._execute_group(
                    job_run=job_run,
                    group=filtered_group,
                    steps_by_name=steps_by_name,
                    context=context,
                    retry_handler=retry_handler,
                    pool=pool,
                )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_group(
        self,
        job_run: JobRun,
        group: list[str],
        steps_by_name: dict,
        context: WorkflowContext,
        retry_handler: RetryHandler | None,
        pool: ThreadPoolExecutor,
    ) -> None:
        """Exécute un groupe de steps en parallèle et attend leur complétion.

        Args:
            pool: Pool de threads partagé fourni par ``execute()``.
        """
        if len(group) == 1:
            # Optimisation : groupe singleton → exécution directe, sans overhead de pool.
            step_name = group[0]
            step = steps_by_name[step_name]
            if self._should_execute_step(step, context):
                self._run_single_step(job_run, step, context, retry_handler)
            return

        futures: dict[Future, str] = {}
        first_suspension: WorkflowSuspended | None = None
        errors: list[StepExecutionError] = []

        for step_name in group:
            step = steps_by_name[step_name]
            if not self._should_execute_step(step, context):
                continue
            future = pool.submit(
                self._run_single_step, job_run, step, context, retry_handler
            )
            futures[future] = step_name

        for future in as_completed(futures):
            try:
                future.result()
            except WorkflowSuspended as exc:
                if first_suspension is None:
                    first_suspension = exc
            except StepExecutionError as exc:
                errors.append(exc)

        if first_suspension is not None:
            raise first_suspension
        if errors:
            raise errors[0]

    def _run_single_step(
        self,
        job_run: JobRun,
        step,
        context: WorkflowContext,
        retry_handler: RetryHandler | None,
    ) -> None:
        """Exécute un step individuel de manière thread-safe."""
        step_run = StepRun(
            step_name=step.name,
            job_run_id=job_run.job_run_id,
            status=RunStatus.PENDING,
        )

        with self._lock:
            job_run.step_runs.append(step_run)

        try:
            step_run.start_execution()
            result = self.execute_single(step, context)

            with self._lock:
                step_run.complete_success(result or {})
                context.set_step_output(step.name, result)

        except WorkflowSuspended as e:
            step_run.suspend(str(e))
            raise

        except Exception as e:
            step_run.complete_failure(str(e))
            self._log_step_error(step_run, e)

            if retry_handler and step.retry_count > 0:
                success = retry_handler.attempt(
                    step, step_run, context, self.execute_single
                )
                if success:
                    return

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
