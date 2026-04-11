"""
Notifications — Alertes et notifications pour les jobs et pipelines.

Fournit des fonctions utilitaires pour envoyer des notifications
(logs, Slack, email…) en cas de succès ou d'échec.

Actuellement, seule la notification par log est implémentée.
Les intégrations Slack/email/Teams sont préparées mais commentées.

Examples:
    >>> notify_success("ingestion-stripe-payments", details={"rows": 42})
    >>> notify_failure("transform-stg-payments", error="Connection timeout")
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.notifications")


def notify_success(
    job_name: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Notifie le succès d'un job.

    Args:
        job_name: Nom du job terminé avec succès.
        details: Détails supplémentaires (nombre de lignes, durée…).
    """
    _logger.info(
        "✓ Job '%s' terminé avec succès",
        job_name,
        extra={"job_name": job_name, "details": details or {}},
    )
    # TODO: intégrations futures
    # _notify_slack(f"✓ {job_name} — succès", details)
    # _notify_email(f"[SUCCESS] {job_name}", details)


def notify_failure(
    job_name: str,
    error: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Notifie l'échec d'un job.

    Args:
        job_name: Nom du job en échec.
        error: Message d'erreur.
        details: Détails supplémentaires.
    """
    _logger.error(
        "✗ Job '%s' en échec : %s",
        job_name,
        error,
        extra={"job_name": job_name, "error": error, "details": details or {}},
    )
    # TODO: intégrations futures
    # _notify_slack(f"🚨 {job_name} — ÉCHEC: {error}", details)
    # _notify_email(f"[FAILURE] {job_name}", {"error": error, **(details or {})})


def notify_pipeline_result(
    pipeline_name: str,
    success: bool,
    results: list[dict[str, Any]] | None = None,
) -> None:
    """Notifie le résultat global d'une pipeline.

    Args:
        pipeline_name: Nom de la pipeline.
        success: True si tous les jobs ont réussi.
        results: Résumé par job (nom, statut, durée…).
    """
    if success:
        _logger.info(
            "🏁 Pipeline '%s' terminée avec succès",
            pipeline_name,
            extra={"pipeline": pipeline_name, "results": results or []},
        )
    else:
        _logger.error(
            "🚨 Pipeline '%s' en échec",
            pipeline_name,
            extra={"pipeline": pipeline_name, "results": results or []},
        )


# ── Intégrations futures (à décommenter) ─────────────────────────────────

# def _notify_slack(message: str, details: dict[str, Any] | None = None) -> None:
#     """Envoie une notification Slack via webhook."""
#     import os
#     import requests
#     webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
#     if not webhook_url:
#         return
#     payload = {"text": message}
#     if details:
#         payload["text"] += f"\n```{details}```"
#     requests.post(webhook_url, json=payload, timeout=10)

# def _notify_email(subject: str, body: dict[str, Any] | None = None) -> None:
#     """Envoie un email via SMTP."""
#     pass
