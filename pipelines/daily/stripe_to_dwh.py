"""
Pipeline quotidienne — Stripe → Data Lake → Staging → Mart Revenue.

Fréquence : quotidien (01h00 UTC)
Chaîne    : ingestion → staging → mart → quality check
Owner     : data-team@company.com

Exécute séquentiellement :
1. ``ingestion-stripe-payments`` — API Stripe → Data Lake (raw JSON)
2. ``transform-stg-payments``   — Raw → Staging DWH (nettoyage, typage)
3. ``transform-mart-finance-revenue`` — Staging → Mart agrégé
4. ``quality-check-completeness``     — Vérification post-pipeline

Examples:
    # Depuis la racine du projet :
    $ python -m pipelines.daily.stripe_to_dwh
    $ python -m pipelines.daily.stripe_to_dwh --date 2026-04-10
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from pyworkflow_engine.logging import get_logger

from jobs.shared.logging import configure_platform_logging
from jobs.ingestion.stripe.extract_payments import job as ingestion_job
from jobs.transformation.marts.finance.mart_revenue import job as mart_job
from jobs.transformation.quality.check_completeness import job as quality_job
from jobs.transformation.staging.stg_payments import job as staging_job
from pipelines.shared.notifications import notify_pipeline
from pipelines.shared.runner import PipelineRunner

_logger = get_logger("pipelines.daily.stripe_to_dwh")


def build_pipeline(date: str | None = None) -> PipelineRunner:
    """Construit la pipeline Stripe → DWH pour une date donnée.

    Args:
        date: Date au format ``YYYY-MM-DD``. Si ``None``, utilise la date du jour.

    Returns:
        ``PipelineRunner`` prêt à exécuter.
    """
    target_date = date or datetime.now(tz=UTC).strftime("%Y-%m-%d")

    runner = PipelineRunner("daily-stripe-to-dwh")

    # 1. Ingestion : API Stripe → Data Lake
    runner.add_job(
        ingestion_job,
        initial_context={"since_date": target_date},
    )

    # 2. Staging : Data Lake → DWH staging
    runner.add_job(
        staging_job,
        initial_context={"partition": target_date},
    )

    # 3. Mart : Staging → Mart finance revenue
    runner.add_job(mart_job)

    # 4. Quality : Vérification de complétude
    runner.add_job(quality_job)

    return runner


def main(date: str | None = None) -> None:
    """Point d'entrée principal de la pipeline."""
    configure_platform_logging()
    runner = build_pipeline(date)
    _logger.info("Démarrage de la pipeline '%s'", runner.name)

    result = runner.execute()

    # Afficher le résumé
    print(result.summary)  # noqa: T201

    # Envoyer les notifications
    notify_pipeline(result)

    # Code de sortie
    if not result.success:
        _logger.error("Pipeline '%s' terminée en ÉCHEC", runner.name)
        sys.exit(1)

    _logger.info("Pipeline '%s' terminée avec succès", runner.name)


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline Stripe → DWH")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date cible (YYYY-MM-DD). Défaut : aujourd'hui.",
    )
    args = parser.parse_args()
    main(date=args.date)
