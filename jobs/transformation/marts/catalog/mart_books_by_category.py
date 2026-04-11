"""
Mart Catalog — Livres agrégés par catégorie.

Fréquence : quotidien (05h00 UTC, après staging books)
Source    : DWH staging_stg_books
Cible     : DWH marts_catalog_books_by_category
Owner     : data-team@company.com

Métriques produites par catégorie :
    - Nombre de livres
    - Prix moyen, min, max (GBP)
    - Stock total
    - Note moyenne (1-5)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.shared.warehouse import Warehouse

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext

_logger = get_logger("jobs.transformation.marts.catalog.mart_books_by_category")

# ── Steps ────────────────────────────────────────────────────────────────


def aggregate_by_category(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Agrège les métriques livres par catégorie depuis staging."""
    wh = Warehouse.from_env()

    _logger.info("Création / vérification de la table marts_catalog_books_by_category")
    wh._get_connection().execute(
        """
        CREATE TABLE IF NOT EXISTS marts_catalog_books_by_category (
            "category"      VARCHAR PRIMARY KEY,
            "book_count"    INTEGER,
            "avg_price_gbp" DOUBLE,
            "min_price_gbp" DOUBLE,
            "max_price_gbp" DOUBLE,
            "total_stock"   INTEGER,
            "avg_rating"    DOUBLE
        )
        """
    )

    _logger.info("Agrégation depuis staging_stg_books par catégorie")
    rows = wh.query(
        """
        SELECT
            category,
            COUNT(*)                                    AS book_count,
            ROUND(AVG(CAST(price_gbp AS DOUBLE)), 2)   AS avg_price_gbp,
            ROUND(MIN(CAST(price_gbp AS DOUBLE)), 2)   AS min_price_gbp,
            ROUND(MAX(CAST(price_gbp AS DOUBLE)), 2)   AS max_price_gbp,
            SUM(CAST(stock AS INTEGER))                 AS total_stock,
            ROUND(AVG(CAST(rating AS DOUBLE)), 2)      AS avg_rating
        FROM staging_stg_books
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY book_count DESC
        """
    )

    _logger.info("%d catégorie(s) agrégée(s)", len(rows))

    if rows:
        wh.upsert(
            table="marts_catalog_books_by_category",
            data=rows,
            key="category",
        )
        _logger.info("Upsert marts_catalog_books_by_category : %d ligne(s)", len(rows))

    return {
        "rows_aggregated": len(rows),
        "categories": [r["category"] for r in rows] if rows else [],
    }


def validate_mart(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Validation du mart catalog."""
    wh = Warehouse.from_env()
    count = wh.query_scalar("SELECT COUNT(*) FROM marts_catalog_books_by_category")
    negative_prices = wh.query_scalar(
        "SELECT COUNT(*) FROM marts_catalog_books_by_category WHERE avg_price_gbp < 0"
    )
    zero_books = wh.query_scalar(
        "SELECT COUNT(*) FROM marts_catalog_books_by_category WHERE book_count = 0"
    )
    quality_passed = (negative_prices or 0) == 0 and (zero_books or 0) == 0
    _logger.info(
        "Validation mart catalog : %d catégories, %d prix négatifs, %d catégories vides — %s",
        count or 0,
        negative_prices or 0,
        zero_books or 0,
        "✓ OK" if quality_passed else "✗ ÉCHEC",
    )
    return {
        "total_categories": count,
        "negative_prices": negative_prices,
        "zero_book_categories": zero_books,
        "quality_passed": quality_passed,
    }


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="transform-mart-catalog-books",
    version="1.0.0",
    steps=[
        Step(
            name="aggregate_by_category",
            step_type=StepType.FUNCTION,
            handler=aggregate_by_category,
        ),
        Step(
            name="validate_mart",
            step_type=StepType.FUNCTION,
            handler=validate_mart,
            dependencies=["aggregate_by_category"],
        ),
    ],
)


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pyworkflow_engine import WorkflowEngine

    result = WorkflowEngine().run(job)
    print(f"Terminé : {result.status}")  # noqa: T201
