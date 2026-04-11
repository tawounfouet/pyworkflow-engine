"""
Mart Finance — Revenue quotidien agrégé.

Fréquence : quotidien (04h00 UTC, après staging)
Source    : DWH staging_stg_payments
Cible     : DWH marts_finance_revenue
Owner     : data-team@company.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.shared.warehouse import Warehouse

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext


# ── Steps ────────────────────────────────────────────────────────────────


def aggregate_revenue(context: WorkflowContext) -> dict[str, Any]:
    """Agrège le revenue par jour et par devise depuis staging."""
    wh = Warehouse.from_env()

    # Créer la table marts si elle n'existe pas
    wh._get_connection().execute(
        """
        CREATE TABLE IF NOT EXISTS marts_finance_revenue (
            "date" VARCHAR,
            "currency" VARCHAR,
            "total_amount" DOUBLE,
            "transaction_count" INTEGER,
            "avg_amount" DOUBLE,
            PRIMARY KEY ("date", "currency")
        )
    """
    )

    # Agrégation depuis staging
    rows = wh.query(
        """
        SELECT
            CAST(created_at AS DATE) AS "date",
            currency,
            ROUND(SUM(CAST(amount AS DOUBLE)), 2) AS total_amount,
            COUNT(*) AS transaction_count,
            ROUND(AVG(CAST(amount AS DOUBLE)), 2) AS avg_amount
        FROM staging_stg_payments
        WHERE status = 'succeeded'
        GROUP BY CAST(created_at AS DATE), currency
        ORDER BY "date" DESC, currency
    """
    )

    if rows:
        wh.upsert(
            table="marts_finance_revenue",
            data=rows,
            key="date",
        )

    return {
        "rows_aggregated": len(rows),
        "currencies": list({r["currency"] for r in rows}) if rows else [],
    }


def validate_mart(context: WorkflowContext) -> dict[str, Any]:
    """Validation du mart revenue."""
    wh = Warehouse.from_env()
    count = wh.query_scalar("SELECT COUNT(*) FROM marts_finance_revenue")
    negative = wh.query_scalar(
        "SELECT COUNT(*) FROM marts_finance_revenue WHERE total_amount < 0"
    )
    return {
        "total_rows": count,
        "negative_amounts": negative,
        "quality_passed": (negative or 0) == 0,
    }


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="transform-mart-finance-revenue",
    version="1.0.0",
    steps=[
        Step(
            name="aggregate_revenue",
            step_type=StepType.FUNCTION,
            handler=aggregate_revenue,
        ),
        Step(
            name="validate_mart",
            step_type=StepType.FUNCTION,
            handler=validate_mart,
            dependencies=["aggregate_revenue"],
        ),
    ],
)


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pyworkflow_engine import WorkflowEngine

    result = WorkflowEngine().run(job)
    print(f"Terminé : {result.status}")
