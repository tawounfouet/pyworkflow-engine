"""
Notifications pipeline-level — Alertes à l'issue d'une pipeline complète.

Décore / complète ``jobs.shared.notifications`` avec des fonctions
spécifiques à l'orchestration des pipelines.

Accepte indifféremment :
- ``PipelineRun``    (ADR-014 / ADR-016) — attributs : ``.stage_runs``, ``.success``
- ``PipelineResult`` (legacy runner)     — attributs : ``.job_results``, ``.success``

Examples:
    >>> from pipelines.shared.notifications import notify_pipeline
    >>> notify_pipeline(result)
"""

from __future__ import annotations

from typing import Any

from jobs.shared.notifications import notify_pipeline_result


def notify_pipeline(result: Any) -> None:
    """Envoie une notification pour le résultat d'une pipeline.

    Accepte ``PipelineRun`` (nouveau modèle ADR-014) **et** l'ancien
    ``PipelineResult`` de ``pipelines.shared.runner`` (rétrocompatibilité).

    Délègue à ``jobs.shared.notifications.notify_pipeline_result``.
    """
    # --- Résoudre le nom de la pipeline ---------------------------------
    pipeline_name: str = getattr(result, "pipeline_name", "unknown")

    # --- Résoudre le succès global --------------------------------------
    success: bool = bool(getattr(result, "success", False))

    # --- Construire les résumés par stage / job -------------------------
    summaries: list[dict[str, Any]] = []

    # PipelineRun (ADR-014) — .stage_runs est une liste de StageRun
    if hasattr(result, "stage_runs"):
        for sr in result.stage_runs:
            dur = getattr(sr, "duration_ms", None)
            duration_s = (dur / 1000.0) if dur is not None else None
            error = getattr(sr, "error", None)
            # Tronquer le message d'erreur pour les notifications
            if error and len(error) > 200:
                error = error[:200] + "…"
            summaries.append(
                {
                    "job": getattr(sr, "job_name", "?"),
                    "status": getattr(sr.status, "value", str(sr.status)),
                    "duration_s": duration_s,
                    "error": error,
                }
            )

    # PipelineResult (legacy) — .job_results est une liste de JobResult
    elif hasattr(result, "job_results"):
        for jr in result.job_results:
            summaries.append(
                {
                    "job": getattr(jr, "job_name", "?"),
                    "status": getattr(jr.status, "value", str(jr.status)),
                    "duration_s": getattr(jr, "duration_s", None),
                    "error": getattr(jr, "error", None),
                }
            )

    notify_pipeline_result(
        pipeline_name=pipeline_name,
        success=success,
        results=summaries,
    )
