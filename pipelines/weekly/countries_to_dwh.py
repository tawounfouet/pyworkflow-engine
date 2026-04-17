"""
Pipeline hebdomadaire — REST Countries API → Data Lake → Staging → Mart Catalog.

Réécrite avec l'API déclarative ``@pipeline`` / ``@stage`` (ADR-014 / ADR-016).
Supersède l'ancienne implémentation basée sur ``PipelineRunner`` impératif.

Fréquence : hebdomadaire (dimanche 01h00 UTC)
Chaîne    : ingestion API → staging → mart → quality check
Owner     : data-team@company.com

Examples:
    # Depuis la racine du projet :
    $ python -m pipelines.weekly.countries_to_dwh
    $ python -m pipelines.weekly.countries_to_dwh --date 2026-04-13

    # Programmatique :
    >>> from pipelines.weekly.countries_to_dwh import countries_to_dwh
    >>> p = countries_to_dwh.build()
    >>> from pyworkflow_engine import WorkflowEngine
    >>> engine = WorkflowEngine()
    >>> pipeline_run = engine.run_pipeline(p, initial_context={"ingest_date": "2026-04-13"})
    >>> print(pipeline_run.summary)
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from pyworkflow_engine.decorators import pipeline, stage
from pyworkflow_engine.logging import get_logger

from jobs.ingestion.restcountries.extract_countries import (
    ingest_restcountries as ingestion_job_builder,
)
from jobs.transformation.marts.catalog.mart_countries_by_region import job as mart_job
from jobs.transformation.quality.check_completeness import job as quality_job
from jobs.transformation.staging.stg_restcountries import job as staging_job
from pipelines.shared.notifications import notify_pipeline

_logger = get_logger("pipelines.weekly.countries_to_dwh")


# ── Stage declarations ────────────────────────────────────────────────────────


@stage(
    job=ingestion_job_builder,
    # ingest_date propagé depuis le contexte initial de la pipeline
    context_mapping={"ingest_date": "ingest_date"},
)
def ingestion_stage() -> None:
    """Ingestion REST Countries API → Data Lake (raw JSON)."""


@stage(
    job=staging_job,
    # partition = ingest_date propagé depuis le stage d'ingestion
    context_mapping={"partition": "ingest_date"},
)
def staging_stage() -> None:
    """Staging : Data Lake → DWH staging (typage, normalisation)."""


@stage(job=mart_job)
def mart_stage() -> None:
    """Mart : Staging → Mart catalog agrégé par région."""


@stage(job=quality_job, continue_on_failure=True)
def quality_stage() -> None:
    """Quality : vérification post-pipeline (non-bloquante)."""


# ── Pipeline declaration ──────────────────────────────────────────────────────


@pipeline(
    name="weekly-countries-to-dwh",
    description=(
        "Pipeline hebdomadaire REST Countries → Data Lake → DWH Staging → "
        "Mart Catalog → Quality Check."
    ),
    schedule="0 1 * * 0",  # dimanche 01h00 UTC
    owner="data-team@company.com",
    tags=["weekly", "restcountries", "dwh", "connector"],
    version="2.0.0",
)
def countries_to_dwh() -> None:
    """Pipeline hebdomadaire REST Countries → DWH.

    Stages (en ordre d'exécution) :
        1. ingestion_stage  — API REST Countries → Data Lake
        2. staging_stage    — Data Lake → DWH Staging
        3. mart_stage       — Staging → Mart Catalog par région
        4. quality_stage    — Vérification de complétude (continue_on_failure)
    """
    ingestion_stage()
    staging_stage()
    mart_stage()
    quality_stage()


# ── Entrypoint ────────────────────────────────────────────────────────────────


def main(date: str | None = None) -> None:
    """Point d'entrée principal de la pipeline."""
    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415
    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415

    configure_platform_logging()

    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    target_date = date or settings.today()
    _logger.info(
        "Construction de la pipeline countries_to_dwh pour la date %s", target_date
    )

    pipeline_obj = countries_to_dwh.build()
    engine = WorkflowEngine()

    _logger.info("Démarrage de la pipeline '%s'", pipeline_obj.name)
    pipeline_run = engine.run_pipeline(
        pipeline_obj,
        initial_context={"ingest_date": target_date},
        triggered_by="manual",
    )

    print(pipeline_run.summary)  # noqa: T201

    try:
        notify_pipeline(pipeline_run)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Notification échouée (non-bloquant) : %s", exc)

    if not pipeline_run.success:
        _logger.error("Pipeline '%s' terminée en ÉCHEC", pipeline_obj.name)
        sys.exit(1)

    _logger.info("Pipeline '%s' terminée avec succès", pipeline_obj.name)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline REST Countries → DWH")
    parser.add_argument(
        "--date", default=None, help="Date YYYY-MM-DD (défaut: aujourd'hui)"
    )
    args = parser.parse_args()
    main(date=args.date)
