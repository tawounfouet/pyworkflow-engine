"""
PipelineRunner — orchestration séquentielle de stages dans une Pipeline.

Ce module est le cœur d'exécution des pipelines (ADR-014/ADR-016).
Il promeut la logique de ``pipelines/shared/runner.py`` en composant
de première classe dans ``engine/``, agnostique de tout framework
applicatif.

Responsabilités :
- Exécuter chaque ``PipelineStage`` dans l'ordre déclaré
- Propager le contexte entre stages via ``context_mapping``
- Évaluer les conditions de skip (``condition``, ``enabled``)
- Gérer ``continue_on_failure`` par stage
- Retourner un ``PipelineRun`` entièrement tracé

L'engine utilise ``WorkflowEngine.run()`` ou ``run_with_storage()``
selon la disponibilité d'un backend de persistence.

Voir ADR-014 (Pipeline model) et ADR-016 (plan maître).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine
    from pyworkflow_engine.models.pipeline.pipeline import PipelineStage

from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, Pipeline, RunStatus
from pyworkflow_engine.models.pipeline.pipeline_run import PipelineRun, StageRun

_logger = get_logger("engine.pipeline_runner")


def _short_err(exc: BaseException | str, max_len: int = 120) -> str:
    """Extrait un message d'erreur court depuis une exception ou une chaîne.

    Prend le premier segment avant " | " (séparateur de contexte du moteur)
    et tronque à ``max_len`` caractères.
    """
    msg = str(exc).split(" | ")[0].strip()
    return msg if len(msg) <= max_len else msg[:max_len] + "…"


class PipelineRunner:
    """Orchestre l'exécution d'une ``Pipeline`` complète.

    Exécute séquentiellement chaque ``PipelineStage``, propage le contexte,
    et retourne un ``PipelineRun`` entièrement tracé.

    Args:
        engine: Instance ``WorkflowEngine`` utilisée pour exécuter les Jobs.
            Obligatoire — injecté par ``WorkflowEngine.run_pipeline()``.
        job_registry: Mapping ``{job_name: Job}`` pour résoudre les jobs par
            nom quand ``PipelineStage.job`` est ``None``.  La ``WorkflowEngine``
            maintient un tel registre en mémoire.

    Examples:
        >>> runner = PipelineRunner(engine=my_engine)
        >>> pipeline_run = runner.execute(pipeline, initial_context={"date": "2026-04-12"})
        >>> assert pipeline_run.status == RunStatus.SUCCESS
    """

    def __init__(
        self,
        engine: WorkflowEngine,
        job_registry: dict[str, Job] | None = None,
    ) -> None:
        self._engine = engine
        self._job_registry: dict[str, Job] = job_registry or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        pipeline: Pipeline,
        initial_context: dict[str, Any] | None = None,
        triggered_by: str = "manual",
    ) -> PipelineRun:
        """Exécute une pipeline complète et retourne le ``PipelineRun``.

        Args:
            pipeline: Définition de la pipeline à exécuter.
            initial_context: Contexte initial injecté dans le premier stage.
            triggered_by: Source du déclenchement (``"manual"``, ``"schedule"``,
                ``"ai"``, …).

        Returns:
            ``PipelineRun`` avec le statut global et la liste des
            ``StageRun`` renseignés.
        """
        pipeline_run = PipelineRun(
            pipeline_name=pipeline.name,
            pipeline_version=pipeline.version,
            status=RunStatus.PENDING,
            triggered_by=triggered_by,
        )

        accumulated_ctx: dict[str, Any] = dict(initial_context or {})
        pipeline_run.context = dict(accumulated_ctx)

        _logger.info(
            "Démarrage de la pipeline '%s' (run=%s, stages=%d)",
            pipeline.name,
            pipeline_run.pipeline_run_id[:8],
            len(pipeline.stages),
        )

        pipeline_run.start_execution()
        all_success = True

        for idx, stage_def in enumerate(pipeline.stages):
            stage_run = StageRun(
                pipeline_run_id=pipeline_run.pipeline_run_id,
                job_name=stage_def.job_name,
                stage_index=idx,
            )
            pipeline_run.add_stage_run(stage_run)

            if self._should_skip(stage_def, accumulated_ctx, stage_run, idx):
                continue

            job = self._resolve_job(stage_def)
            if job is None:
                err = f"Job '{stage_def.job_name}' not found in registry"
                _logger.error("  [%d] %s → ERROR: %s", idx, stage_def.job_name, err)
                stage_run.start_execution()
                stage_run.complete_failure(err)
                all_success = False
                if not stage_def.continue_on_failure:
                    break
                continue

            stage_ctx = self._build_stage_context(stage_def, accumulated_ctx)
            stage_run.start_execution()
            _logger.info("  [%d] %s → RUNNING…", idx, stage_def.job_name)

            ran_ok = self._run_stage(stage_run, stage_def, job, stage_ctx, idx)
            if ran_ok:
                accumulated_ctx.update(stage_run.job_run.context or {})
                pipeline_run.context = dict(accumulated_ctx)
            else:
                all_success = False
                if not stage_def.continue_on_failure:
                    break

        self._finalise(pipeline_run, all_success)
        _logger.info(
            "Pipeline '%s' terminée : %s (%.3fs)",
            pipeline.name,
            pipeline_run.status.value,
            pipeline_run.duration_s,
        )
        return pipeline_run

    # ------------------------------------------------------------------
    # Stage-level helpers (keep execute() complexity low)
    # ------------------------------------------------------------------

    def _should_skip(
        self,
        stage_def: PipelineStage,
        ctx: dict[str, Any],
        stage_run: StageRun,
        idx: int,
    ) -> bool:
        """Retourne ``True`` et met à jour ``stage_run`` si le stage doit être sauté."""
        if not stage_def.enabled:
            stage_run.mark_skipped("stage disabled")
            _logger.info("  [%d] %s → SKIPPED (disabled)", idx, stage_def.job_name)
            return True
        if stage_def.condition is not None:
            try:
                if not stage_def.condition(ctx):
                    stage_run.mark_skipped("condition returned False")
                    _logger.info(
                        "  [%d] %s → SKIPPED (condition)", idx, stage_def.job_name
                    )
                    return True
            except Exception as cond_err:  # noqa: BLE001
                _logger.warning(
                    "  [%d] %s — condition raised %s, skipping",
                    idx,
                    stage_def.job_name,
                    cond_err,
                )
                stage_run.mark_skipped(f"condition error: {cond_err}")
                return True
        return False

    @staticmethod
    def _build_stage_context(
        stage_def: PipelineStage,
        accumulated_ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """Construit le contexte d'entrée du stage en appliquant les mappings."""
        ctx = {**accumulated_ctx, **stage_def.initial_context}
        for dest_key, src_key in stage_def.context_mapping.items():
            if src_key in accumulated_ctx:
                ctx[dest_key] = accumulated_ctx[src_key]
        return ctx

    def _run_stage(
        self,
        stage_run: StageRun,
        stage_def: PipelineStage,
        job: Job,
        stage_ctx: dict[str, Any],
        idx: int,
    ) -> bool:
        """Exécute le job du stage et met à jour ``stage_run``.

        Returns:
            ``True`` si le job a réussi, ``False`` sinon.
        """
        try:
            job_run = self._run_job(job, stage_ctx)
            stage_run.job_run = job_run
            if job_run.status == RunStatus.SUCCESS:
                stage_run.complete_success()
                _logger.info(
                    "  [%d] %s → SUCCESS (%.3fs)",
                    idx,
                    stage_def.job_name,
                    stage_run.duration_s,
                )
                return True
            err = f"Job finished with status {job_run.status.value}"
            stage_run.complete_failure(err)
            _logger.warning(
                "  [%d] %s → %s", idx, stage_def.job_name, job_run.status.value
            )
            return False
        except Exception as exc:  # noqa: BLE001
            stage_run.complete_failure(str(exc))
            _logger.error(
                "  [%d] %s → FAILED: %s", idx, stage_def.job_name, _short_err(exc)
            )
            return False

    @staticmethod
    def _finalise(pipeline_run: PipelineRun, all_success: bool) -> None:
        """Applique le statut terminal au ``PipelineRun``."""
        if all_success:
            pipeline_run.complete_success()
        else:
            failed = next(
                (sr for sr in pipeline_run.stage_runs if sr.status == RunStatus.FAILED),
                None,
            )
            msg = (
                failed.error if failed and failed.error else "One or more stages failed"
            )
            pipeline_run.complete_failure(msg)

    def _resolve_job(self, stage_def: PipelineStage) -> Job | None:
        """Résout le ``Job`` d'un stage depuis la définition ou le registre."""
        if stage_def.job is not None:
            return stage_def.job
        return self._job_registry.get(stage_def.job_name)

    def _run_job(self, job: Job, ctx: dict[str, Any]):  # type: ignore[return]
        """Exécute un job avec persistence si disponible, sinon en mémoire."""
        if getattr(self._engine, "_storage", None) is not None:
            return self._engine.run_with_storage(job, initial_context=ctx)
        return self._engine.run(job, initial_context=ctx)
