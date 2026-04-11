"""
Transformation — Raw Payments → Staging (DWH).

Fréquence : quotidien (03h00 UTC, après ingestion)
Source    : datalake://raw/stripe/payments/
Cible     : DWH staging.stg_payments (DuckDB / Postgres)
Owner     : data-team@company.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.shared.datalake import DataLake
from jobs.shared.warehouse import Warehouse

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext


# ── Steps ────────────────────────────────────────────────────────────────


def read_from_datalake(context: WorkflowContext) -> dict[str, Any]:
    """Lecture des données brutes depuis le Data Lake."""
    dl = DataLake.from_env()
    partition = context.get("partition", "latest")
    raw = dl.read_json(f"raw/stripe/payments/{partition}/")
    return {"raw_records": raw, "source_count": len(raw)}


def clean_and_type(context: WorkflowContext) -> dict[str, Any]:
    """Nettoyage, typage, déduplication.

    Transformations appliquées :
    - ``amount`` : conversion centimes → euros (÷ 100)
    - ``created`` : timestamp Unix → ISO 8601 UTC
    - ``currency`` : normalisation majuscules
    - Déduplication sur ``id``
    - Renommage ``id`` → ``payment_id``
    """
    raw: list[dict[str, Any]] = context.get_step_output("read_from_datalake")[
        "raw_records"
    ]
    if not raw:
        return {"clean_records": [], "clean_count": 0, "duplicates_removed": 0}

    from datetime import UTC, datetime  # noqa: PLC0415

    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    duplicates = 0

    for record in raw:
        record_id = str(record.get("id", ""))
        if record_id in seen:
            duplicates += 1
            continue
        seen.add(record_id)

        amount_cents = int(record.get("amount", 0))
        created_ts = record.get("created")
        created_at = (
            datetime.fromtimestamp(int(created_ts), tz=UTC).isoformat()
            if created_ts
            else None
        )

        cleaned.append(
            {
                "payment_id": record_id,
                "amount": round(amount_cents / 100, 2),
                "amount_cents": amount_cents,
                "currency": str(record.get("currency", "")).upper(),
                "status": record.get("status"),
                "created_at": created_at,
                "description": record.get("description"),
            }
        )

    return {
        "clean_records": cleaned,
        "clean_count": len(cleaned),
        "duplicates_removed": duplicates,
    }


def load_to_warehouse(context: WorkflowContext) -> dict[str, Any]:
    """Écriture dans le DWH (staging schema)."""
    clean: list[dict[str, Any]] = context.get_step_output("clean_and_type")[
        "clean_records"
    ]
    if not clean:
        return {"rows_upserted": 0, "skipped": True}

    wh = Warehouse.from_env()
    rows = wh.upsert(
        table="staging_stg_payments",
        data=clean,
        key="payment_id",
    )
    return {"rows_upserted": rows}


def quality_check(context: WorkflowContext) -> dict[str, Any]:
    """Vérifications post-chargement."""
    wh = Warehouse.from_env()
    count = wh.query_scalar("SELECT COUNT(*) FROM staging_stg_payments")
    nulls = wh.query_scalar(
        "SELECT COUNT(*) FROM staging_stg_payments WHERE amount IS NULL"
    )
    return {
        "total_rows": count,
        "null_amounts": nulls,
        "quality_passed": (nulls or 0) == 0,
    }


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="transform-stg-payments",
    version="1.0.0",
    steps=[
        Step(
            name="read_from_datalake",
            step_type=StepType.FUNCTION,
            handler=read_from_datalake,
        ),
        Step(
            name="clean_and_type",
            step_type=StepType.FUNCTION,
            handler=clean_and_type,
            dependencies=["read_from_datalake"],
        ),
        Step(
            name="load_to_warehouse",
            step_type=StepType.FUNCTION,
            handler=load_to_warehouse,
            dependencies=["clean_and_type"],
        ),
        Step(
            name="quality_check",
            step_type=StepType.FUNCTION,
            handler=quality_check,
            dependencies=["load_to_warehouse"],
        ),
    ],
)


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pyworkflow_engine import WorkflowEngine

    result = WorkflowEngine().run(job, initial_context={"partition": "2026-04-10"})
    print(f"Terminé : {result.status}")
