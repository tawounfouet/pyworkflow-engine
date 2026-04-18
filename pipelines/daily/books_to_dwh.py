"""
Pipeline quotidienne — Books.toscrape.com → Data Lake → Staging → Mart Catalog.

Fréquence : quotidien (02h00 UTC)
Chaîne    : scraping → staging → mart → quality check
Owner     : data-team@company.com

Exécute séquentiellement :
1. ``ingestion-books-toscrape``         — Scraping → Data Lake (raw JSON)
2. ``transform-stg-books``             — Raw → Staging DWH (nettoyage, typage)
3. ``transform-mart-catalog-books``    — Staging → Mart agrégé par catégorie
4. ``quality-check-completeness``      — Vérification post-pipeline

Examples:
    # Depuis la racine du projet :
    $ python -m pipelines.daily.books_to_dwh
    $ python -m pipelines.daily.books_to_dwh --date 2026-04-12
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from pyworkflow_engine.logging import get_logger

from jobs.shared.logging import configure_platform_logging
from jobs.ingestion.books_toscrape.extract_books import job as ingestion_job
from jobs.transformation.marts.catalog.mart_books_by_category import job as mart_job
from jobs.transformation.quality.check_completeness import job as quality_job
from jobs.transformation.staging.stg_books import job as staging_job
from pipelines.shared.notifications import notify_pipeline
from pipelines.shared.runner import PipelineRunner

_logger = get_logger("pipelines.daily.books_to_dwh")


def build_pipeline(date: str | None = None) -> PipelineRunner:
    """Construit la pipeline Books → DWH pour une date donnée.

    Args:
        date: Date au format ``YYYY-MM-DD``. Si ``None``, utilise la date du jour.

    Returns:
        ``PipelineRunner`` prêt à exécuter.
    """
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    target_date = date or settings.today()
    _logger.info(
        "Construction de la pipeline books_to_dwh pour la date %s", target_date
    )
    runner = PipelineRunner("daily-books-to-dwh")

    # 1. Ingestion : Scraping → Data Lake
    runner.add_job(
        ingestion_job,
        initial_context={"ingest_date": target_date},
    )

    # 2. Staging : Data Lake → DWH staging
    runner.add_job(
        staging_job,
        initial_context={"partition": target_date},
    )

    # 3. Mart : Staging → Mart catalog par catégorie
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

    if not result.success:
        _logger.error("Pipeline '%s' terminée en ÉCHEC", runner.name)
        sys.exit(1)

    _logger.info("Pipeline '%s' terminée avec succès", runner.name)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline Books.toscrape → DWH")
    parser.add_argument(
        "--date", default=None, help="Date YYYY-MM-DD (défaut: aujourd'hui)"
    )
    args = parser.parse_args()
    main(date=args.date)
