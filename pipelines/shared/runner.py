"""
PipelineRunner — Orchestration séquentielle de jobs.

.. deprecated::
    Cette implémentation est conservée pour rétrocompatibilité.
    La logique d'orchestration a été promue dans
    ``pyworkflow_engine.engine.pipeline_runner.PipelineRunner`` (ADR-014/ADR-016).

    Préférez utiliser l'API déclarative ``@pipeline`` / ``@stage`` +
    ``WorkflowEngine.run_pipeline()`` pour les nouveaux pipelines.

Exécute une séquence de jobs ``pyworkflow_engine.models.Job`` dans l'ordre,
propage le contexte entre les étapes et collecte les résultats.

Le runner est volontairement simple : chaque job est exécuté via
``WorkflowEngine.run()`` et le résultat est injecté dans le contexte du
job suivant.  En cas d'échec, l'exécution s'arrête (fail-fast) sauf si
``continue_on_failure=True``.

Examples:
    >>> from pipelines.shared.runner import PipelineRunner
    >>> runner = PipelineRunner("daily-stripe-to-dwh")
    >>> runner.add_job(ingestion_job, initial_context={"since_date": "2026-04-10"})
    >>> runner.add_job(staging_job, context_mapping={"partition": "since_date"})
    >>> runner.add_job(mart_job)
    >>> result = runner.execute()
    >>> assert result.success
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, RunStatus

_logger = get_logger("pipelines.shared.runner")


# ── Data structures ──────────────────────────────────────────────────────


@dataclass
class JobEntry:
    """Déclaration d'un job dans la pipeline."""

    job: Job
    initial_context: dict[str, Any] = field(default_factory=dict)
    context_mapping: dict[str, str] = field(default_factory=dict)
    """Mapping clé_destination → clé_source pour injecter les valeurs
    du contexte accumulé dans l'initial_context de ce job."""


@dataclass
class JobResult:
    """Résultat d'exécution d'un seul job dans la pipeline."""

    job_name: str
    status: RunStatus
    duration_s: float
    context: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class PipelineResult:
    """Résultat global de la pipeline."""

    pipeline_name: str
    success: bool
    total_duration_s: float
    job_results: list[JobResult] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Résumé lisible de l'exécution."""
        status = "✓ SUCCESS" if self.success else "✗ FAILED"
        lines = [
            f"Pipeline '{self.pipeline_name}' — {status} ({self.total_duration_s:.2f}s)",
            "",
        ]
        for jr in self.job_results:
            icon = "✓" if jr.status == RunStatus.SUCCESS else "✗"
            lines.append(
                f"  {icon} {jr.job_name}: {jr.status.value} ({jr.duration_s:.2f}s)"
            )
            if jr.error:
                lines.append(f"    └─ {jr.error}")
        return "\n".join(lines)


# ── Runner ───────────────────────────────────────────────────────────────


class PipelineRunner:
    """Orchestre une séquence de jobs de bout en bout.

    Args:
        name: Nom de la pipeline (pour logs et notifications).
        engine: Instance ``WorkflowEngine``. Un engine par défaut est créé
            si non fourni.
        continue_on_failure: Si ``True``, continue malgré un échec.
    """

    def __init__(
        self,
        name: str,
        engine: WorkflowEngine | None = None,
        continue_on_failure: bool = False,
    ) -> None:
        self.name = name
        self._engine = engine or self._default_engine()
        self._continue_on_failure = continue_on_failure
        self._jobs: list[JobEntry] = []

    @staticmethod
    def _default_engine() -> WorkflowEngine:
        """Retourne un engine avec persistence configurée si disponible."""
        try:
            from jobs.shared.logging import get_engine  # noqa: PLC0415

            return get_engine()
        except Exception:  # noqa: BLE001
            return WorkflowEngine()

    # ── Pipeline definition export ────────────────────────────────────

    def to_pipeline(self) -> Any:
        """Retourne un objet ``Pipeline`` (ADR-014) décrivant cette pipeline.

        Permet d'enregistrer la définition dans le backend de persistence
        (``pl_pipelines``) sans exécuter la pipeline.

        Returns:
            Instance ``Pipeline`` avec un ``PipelineStage`` par job.
        """
        from pyworkflow_engine.models.pipeline.pipeline import (
            Pipeline,
            PipelineStage,
        )  # noqa: PLC0415

        stages = [
            PipelineStage(
                job_name=entry.job.name,
                initial_context=entry.initial_context or {},
                context_mapping=entry.context_mapping or {},
            )
            for entry in self._jobs
        ]
        return Pipeline(name=self.name, stages=stages)

    # ── Registration ─────────────────────────────────────────────────

    def add_job(
        self,
        job: Job,
        initial_context: dict[str, Any] | None = None,
        context_mapping: dict[str, str] | None = None,
    ) -> PipelineRunner:
        """Ajoute un job à la pipeline.

        Args:
            job: Instance ``Job`` à exécuter.
            initial_context: Contexte initial fixe pour ce job.
            context_mapping: Mapping ``{clé_job: clé_pipeline_ctx}`` pour
                injecter dynamiquement des valeurs du contexte accumulé.

        Returns:
            ``self`` pour chaînage fluent.
        """
        self._jobs.append(
            JobEntry(
                job=job,
                initial_context=initial_context or {},
                context_mapping=context_mapping or {},
            )
        )
        return self

    # ── Execution ────────────────────────────────────────────────────

    def _run_job(self, job: Job, ctx: dict[str, Any]):  # type: ignore[return]
        """Exécute un job avec persistence si disponible, sinon en mémoire.

        Utilise ``run_with_storage()`` quand un backend de stockage est
        configuré (jobs + runs visibles dans la GUI / workflow.db).
        Retombe sur ``run()`` si aucune persistence n'est disponible.
        """
        if getattr(self._engine, "_storage", None) is not None:
            _logger.debug("Exécution avec persistence : %s", job.name)
            return self._engine.run_with_storage(job, initial_context=ctx)
        _logger.debug("Exécution sans persistence : %s", job.name)
        return self._engine.run(job, initial_context=ctx)

    def execute(
        self,
        pipeline_context: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Exécute la pipeline séquentiellement.

        Args:
            pipeline_context: Contexte global injecté dans tous les jobs.

        Returns:
            ``PipelineResult`` avec le statut global et les résultats par job.
        """
        accumulated_ctx: dict[str, Any] = dict(pipeline_context or {})
        job_results: list[JobResult] = []
        pipeline_start = time.monotonic()
        all_success = True

        for entry in self._jobs:
            # Construire le contexte du job
            ctx = {**accumulated_ctx, **entry.initial_context}
            for dest_key, src_key in entry.context_mapping.items():
                if src_key in accumulated_ctx:
                    ctx[dest_key] = accumulated_ctx[src_key]

            # Exécuter — avec persistence si le backend est configuré
            job_start = time.monotonic()
            try:
                run = self._run_job(entry.job, ctx)
                duration = time.monotonic() - job_start

                jr = JobResult(
                    job_name=entry.job.name,
                    status=run.status,
                    duration_s=round(duration, 3),
                    context=dict(run.context) if run.context else {},
                )

                if run.status != RunStatus.SUCCESS:
                    all_success = False
                    jr.error = f"Job finished with status {run.status.value}"
                else:
                    # Propager le contexte pour les jobs suivants
                    accumulated_ctx.update(run.context or {})

            except Exception as exc:  # noqa: BLE001
                duration = time.monotonic() - job_start
                all_success = False
                jr = JobResult(
                    job_name=entry.job.name,
                    status=RunStatus.FAILED,
                    duration_s=round(duration, 3),
                    error=str(exc),
                )

            job_results.append(jr)

            if not all_success and not self._continue_on_failure:
                break

        total_duration = round(time.monotonic() - pipeline_start, 3)

        return PipelineResult(
            pipeline_name=self.name,
            success=all_success,
            total_duration_s=total_duration,
            job_results=job_results,
        )


# ---------------------------------------------------------------------------
# Bridge vers engine/pipeline_runner.py (ADR-014 / ADR-016)
# ---------------------------------------------------------------------------


def run_pipeline(
    pipeline: Any,
    initial_context: dict | None = None,
    engine: Any | None = None,
    triggered_by: str = "manual",
) -> Any:
    """Exécute une ``Pipeline`` (objet ADR-014) via le ``PipelineRunner`` engine.

    Pont de rétrocompatibilité : délègue à
    ``pyworkflow_engine.engine.pipeline_runner.PipelineRunner``.

    Préférez appeler directement ``WorkflowEngine.run_pipeline()`` dans
    les nouveaux pipelines.

    Args:
        pipeline: Instance ``Pipeline`` ou résultat de ``@pipeline.build()``.
        initial_context: Contexte initial.
        engine: Instance ``WorkflowEngine``. Crée un engine par défaut si
            non fourni.
        triggered_by: Source du déclenchement.

    Returns:
        ``PipelineRun`` (ADR-014) avec le statut global et les ``StageRun``.
    """
    if engine is None:
        try:
            from jobs.shared.logging import get_engine  # noqa: PLC0415

            engine = get_engine()
        except Exception:  # noqa: BLE001
            from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415

            engine = WorkflowEngine()

    # Délègue à WorkflowEngine.run_pipeline() — c'est lui qui appelle
    # _storage.save_pipeline_run() après l'exécution, ce qui persiste
    # le PipelineRun dans pl_pipeline_runs + pl_stage_runs.
    return engine.run_pipeline(
        pipeline, initial_context=initial_context, triggered_by=triggered_by
    )
