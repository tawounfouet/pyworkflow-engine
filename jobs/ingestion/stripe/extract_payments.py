"""
Ingestion — Stripe Payments → Data Lake (raw).

Fréquence : quotidien (01h00 UTC)
Source    : API Stripe /v1/charges
Cible     : datalake://raw/stripe/payments/{date}/
Owner     : data-team@company.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.ingestion.stripe.client import StripeClient
from jobs.shared.datalake import DataLake

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext


# ── Steps ────────────────────────────────────────────────────────────────


def extract(context: WorkflowContext) -> dict:  # type: ignore[type-arg]
    """Appel API Stripe — récupération des paiements du jour."""
    client = StripeClient.from_env()
    since = context.get("since_date")
    charges = client.list_charges(created_gte=since, limit=1000)
    return {"raw_charges": charges, "count": len(charges)}


def validate_raw(context: WorkflowContext) -> dict:  # type: ignore[type-arg]
    """Validation minimale avant écriture (schéma, non-vide)."""
    raw = context.get_step_output("extract")["raw_charges"]
    if not raw:
        return {"status": "empty", "skip_load": True}
    required = {"id", "amount", "currency", "created"}
    invalid = [r for r in raw if not required.issubset(r.keys())]
    if invalid:
        msg = f"{len(invalid)} records missing required fields {required}"
        raise ValueError(msg)
    return {"status": "valid", "skip_load": False}


def load_to_datalake(context: WorkflowContext) -> dict:  # type: ignore[type-arg]
    """Écriture brute (JSON) dans le Data Lake."""
    validate = context.get_step_output("validate_raw")
    if validate.get("skip_load"):
        return {"rows_written": 0, "skipped": True}
    dl = DataLake.from_env()
    partition = context.get("since_date", "latest")
    raw_charges = context.get_step_output("extract")["raw_charges"]
    path = f"raw/stripe/payments/{partition}/"
    rows = dl.write_json(path, raw_charges)
    return {"rows_written": rows, "path": path}


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="ingestion-stripe-payments",
    version="1.0.0",
    steps=[
        Step(name="extract", step_type=StepType.FUNCTION, handler=extract),
        Step(
            name="validate_raw",
            step_type=StepType.FUNCTION,
            handler=validate_raw,
            dependencies=["extract"],
        ),
        Step(
            name="load_to_datalake",
            step_type=StepType.FUNCTION,
            handler=load_to_datalake,
            dependencies=["validate_raw"],
        ),
    ],
)


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pyworkflow_engine import WorkflowEngine

    result = WorkflowEngine().run(job, initial_context={"since_date": "2026-04-10"})
    print(f"Terminé : {result.status}")
