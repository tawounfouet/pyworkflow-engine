"""
Notifications pipeline-level — Alertes à l'issue d'une pipeline complète.

Décore / complète ``jobs.shared.notifications`` avec des fonctions
spécifiques à l'orchestration des pipelines.

Examples:
    >>> from pipelines.shared.notifications import notify_pipeline
    >>> notify_pipeline(result)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jobs.shared.notifications import notify_pipeline_result

if TYPE_CHECKING:
    from pipelines.shared.runner import PipelineResult


def notify_pipeline(result: PipelineResult) -> None:
    """Envoie une notification pour le résultat d'une pipeline.

    Délègue à ``jobs.shared.notifications.notify_pipeline_result``
    en adaptant le format.
    """
    summaries = [
        {
            "job": jr.job_name,
            "status": jr.status.value,
            "duration_s": jr.duration_s,
            "error": jr.error,
        }
        for jr in result.job_results
    ]
    notify_pipeline_result(
        pipeline_name=result.pipeline_name,
        success=result.success,
        results=summaries,
    )
