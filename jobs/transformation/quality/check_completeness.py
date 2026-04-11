"""
Quality — Vérification de complétude des données dans le DWH.

Fréquence : quotidien (après les transformations)
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


def check_staging_tables(context: WorkflowContext) -> dict[str, Any]:
    """Vérifie que les tables staging contiennent des données."""
    wh = Warehouse.from_env()
    tables = ["staging_stg_payments"]
    results: dict[str, Any] = {}
    issues: list[str] = []

    for table in tables:
        try:
            count = wh.query_scalar(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            results[table] = count
            if not count:
                issues.append(f"{table} is empty")
        except Exception as e:
            results[table] = f"ERROR: {e}"
            issues.append(f"{table} not accessible: {e}")

    return {
        "table_counts": results,
        "issues": issues,
        "passed": len(issues) == 0,
    }


def check_null_rates(context: WorkflowContext) -> dict[str, Any]:
    """Vérifie les taux de NULL sur les colonnes critiques."""
    wh = Warehouse.from_env()
    checks = [
        ("staging_stg_payments", "payment_id"),
        ("staging_stg_payments", "amount"),
        ("staging_stg_payments", "currency"),
    ]
    issues: list[str] = []
    results: dict[str, Any] = {}

    for table, column in checks:
        try:
            total = wh.query_scalar(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            nulls = wh.query_scalar(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL"  # noqa: S608
            )
            rate = (nulls / total * 100) if total else 0
            key = f"{table}.{column}"
            results[key] = {
                "total": total,
                "nulls": nulls,
                "null_rate_pct": round(rate, 2),
            }
            if rate > 5:
                issues.append(f"{key} has {rate:.1f}% nulls (threshold: 5%)")
        except Exception as e:
            issues.append(f"Check failed for {table}.{column}: {e}")

    return {
        "null_checks": results,
        "issues": issues,
        "passed": len(issues) == 0,
    }


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="quality-check-completeness",
    version="1.0.0",
    steps=[
        Step(
            name="check_staging_tables",
            step_type=StepType.FUNCTION,
            handler=check_staging_tables,
        ),
        Step(
            name="check_null_rates",
            step_type=StepType.FUNCTION,
            handler=check_null_rates,
        ),
    ],
)


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pyworkflow_engine import WorkflowEngine

    result = WorkflowEngine().run(job)
    print(f"Terminé : {result.status}")
