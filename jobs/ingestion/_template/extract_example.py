"""
Ingestion — [SOURCE] [ENTITY] → Data Lake (raw).

Fréquence : TODO
Source    : TODO
Cible     : datalake://raw/[source]/[entity]/{date}/
Owner     : TODO

Ce fichier sert de template pour créer un nouveau job d'ingestion.
Copiez le dossier ``_template/`` et remplacez les TODO.

Checklist complète : docs/data-plateforme/03-patterns-conventions.md § 9.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.ingestion._template.client import TemplateClient
from jobs.shared.datalake import DataLake

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext


# ── Steps ────────────────────────────────────────────────────────────────


def extract(context: WorkflowContext) -> dict:  # type: ignore[type-arg]
    """Extraction depuis la source.

    TODO: Adapter l'appel au client réel.
    """
    client = TemplateClient.from_env()
    data = client.fetch_data(since=context.get("since_date"))
    return {"raw_data": data, "count": len(data)}


def validate_raw(context: WorkflowContext) -> dict:  # type: ignore[type-arg]
    """Validation minimale avant écriture (non-vide, champs critiques)."""
    raw = context.get_step_output("extract")["raw_data"]
    if not raw:
        return {"status": "empty", "skip_load": True}
    # TODO: ajouter la validation des champs requis
    return {"status": "valid", "skip_load": False}


def load_to_datalake(context: WorkflowContext) -> dict:  # type: ignore[type-arg]
    """Écriture brute (JSON) dans le Data Lake."""
    validate = context.get_step_output("validate_raw")
    if validate.get("skip_load"):
        return {"rows_written": 0, "skipped": True}
    dl = DataLake.from_env()
    partition = context.get("since_date", "latest")
    raw_data = context.get_step_output("extract")["raw_data"]
    # TODO: remplacer TODO_SOURCE et TODO_ENTITY
    path = f"raw/TODO_SOURCE/TODO_ENTITY/{partition}/"
    rows = dl.write_json(path, raw_data)
    return {"rows_written": rows, "path": path}


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="ingestion-TODO_SOURCE-TODO_ENTITY",
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

    result = WorkflowEngine().run(job)
    print(f"Terminé : {result.status}")
