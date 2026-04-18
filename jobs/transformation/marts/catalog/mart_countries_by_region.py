"""
Mart Catalog — Pays agrégés par région.

Fréquence : hebdomadaire (dimanche 04h00 UTC, après staging restcountries)
Source    : DWH staging_stg_countries
Cible     : DWH marts_catalog_countries_by_region
Owner     : data-team@company.com

Métriques produites par région :
    - Nombre de pays
    - Population totale et moyenne
    - Surface totale et moyenne (km²)
    - Nombre de pays indépendants / membres ONU
    - Nombre de sous-régions distinctes
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.shared.warehouse import Warehouse

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext

_logger = get_logger("jobs.transformation.marts.catalog.mart_countries_by_region")

# ── Steps ────────────────────────────────────────────────────────────────


def aggregate_by_region(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Agrège les métriques pays par région depuis staging."""
    wh = Warehouse.from_env()

    _logger.info(
        "Création / vérification de la table marts_catalog_countries_by_region"
    )
    wh._get_connection().execute(
        """
        CREATE TABLE IF NOT EXISTS marts_catalog_countries_by_region (
            "region"              VARCHAR PRIMARY KEY,
            "country_count"       INTEGER,
            "independent_count"   INTEGER,
            "un_member_count"     INTEGER,
            "subregion_count"     INTEGER,
            "total_population"    BIGINT,
            "avg_population"      DOUBLE,
            "total_area_km2"      DOUBLE,
            "avg_area_km2"        DOUBLE
        )
        """
    )

    _logger.info("Agrégation depuis staging_stg_countries par région")
    rows = wh.query(
        """
        SELECT
            region,
            COUNT(*)                                            AS country_count,
            SUM(CASE WHEN independent THEN 1 ELSE 0 END)       AS independent_count,
            SUM(CASE WHEN un_member   THEN 1 ELSE 0 END)       AS un_member_count,
            COUNT(DISTINCT subregion)                           AS subregion_count,
            SUM(CAST(population AS BIGINT))                     AS total_population,
            ROUND(AVG(CAST(population AS DOUBLE)), 0)           AS avg_population,
            ROUND(SUM(CAST(area_km2 AS DOUBLE)), 2)             AS total_area_km2,
            ROUND(AVG(CAST(area_km2 AS DOUBLE)), 2)             AS avg_area_km2
        FROM staging_stg_countries
        WHERE region IS NOT NULL AND region != ''
        GROUP BY region
        ORDER BY country_count DESC
        """
    )

    _logger.info("%d région(s) agrégée(s)", len(rows))

    if rows:
        wh.upsert(
            table="marts_catalog_countries_by_region",
            data=rows,
            key="region",
        )
        _logger.info(
            "Upsert marts_catalog_countries_by_region : %d ligne(s)", len(rows)
        )

    return {
        "rows_aggregated": len(rows),
        "regions": [r["region"] for r in rows] if rows else [],
    }


def validate_mart(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Validation du mart catalog countries."""
    wh = Warehouse.from_env()
    count = wh.query_scalar("SELECT COUNT(*) FROM marts_catalog_countries_by_region")
    zero_countries = wh.query_scalar(
        "SELECT COUNT(*) FROM marts_catalog_countries_by_region WHERE country_count = 0"
    )
    negative_population = wh.query_scalar(
        "SELECT COUNT(*) FROM marts_catalog_countries_by_region "
        "WHERE total_population < 0"
    )
    quality_passed = (zero_countries or 0) == 0 and (negative_population or 0) == 0
    _logger.info(
        "Validation mart countries : %d régions, %d régions vides, "
        "%d populations négatives — %s",
        count or 0,
        zero_countries or 0,
        negative_population or 0,
        "✓ OK" if quality_passed else "✗ ÉCHEC",
    )
    return {
        "total_regions": count,
        "zero_country_regions": zero_countries,
        "negative_population_regions": negative_population,
        "quality_passed": quality_passed,
    }


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="transform-mart-catalog-countries",
    version="1.0.0",
    steps=[
        Step(
            name="aggregate_by_region",
            step_type=StepType.FUNCTION,
            handler=aggregate_by_region,
        ),
        Step(
            name="validate_mart",
            step_type=StepType.FUNCTION,
            handler=validate_mart,
            dependencies=["aggregate_by_region"],
        ),
    ],
)


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pyworkflow_engine import WorkflowEngine

    from jobs.shared.logging import configure_platform_logging

    configure_platform_logging()

    result = WorkflowEngine().run(job)
    print(f"Terminé : {result.status}")  # noqa: T201
