"""
Transformation — Raw Books → Staging (DWH).

Fréquence : quotidien (04h00 UTC, après ingestion books)
Source    : datalake://raw/books_toscrape/books/{date}/
Cible     : DWH staging_stg_books (DuckDB / Postgres)
Owner     : data-team@company.com

Transformations appliquées :
    - ``price_raw``         : nettoyage HTML → float (GBP)
    - ``price_excl_tax_raw``: idem
    - ``tax_raw``           : idem
    - ``availability_raw``  : extraction du stock entier
    - ``rating_raw``        : mot anglais → entier 1-5
    - Déduplication sur ``upc``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.ingestion.books_toscrape.client import (
    _RATING_MAP,
    _clean_availability,
    _clean_price,
)
from jobs.shared.datalake import DataLake
from jobs.shared.warehouse import Warehouse

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext

_logger = get_logger("jobs.transformation.staging.stg_books")

# ── Steps ────────────────────────────────────────────────────────────────


def read_from_datalake(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Lecture des données brutes depuis le Data Lake."""
    dl = DataLake.from_env()
    partition = context.get("partition", "latest")
    path = f"raw/books_toscrape/books/{partition}/"
    _logger.info("Lecture Data Lake : %s", path)
    raw = dl.read_json(path)
    _logger.info("%d enregistrement(s) brut(s) lus", len(raw))
    return {"raw_records": raw, "source_count": len(raw)}


def clean_and_type(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Nettoyage, typage, déduplication.

    Transformations :
    - Prix bruts nettoyés → float (GBP)
    - Stock extrait → int
    - Rating mot → int (1-5)
    - Déduplication sur ``upc``
    """
    raw: list[dict[str, Any]] = context.get_step_output("read_from_datalake")[
        "raw_records"
    ]

    if not raw:
        _logger.warning("Aucun enregistrement brut à transformer")
        return {"clean_records": [], "clean_count": 0, "duplicates_removed": 0}

    _logger.info("Transformation de %d enregistrement(s) brut(s)", len(raw))

    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    duplicates = 0

    for record in raw:
        upc = str(record.get("upc", "")).strip()
        if upc in seen:
            duplicates += 1
            continue
        seen.add(upc)

        rating_word = str(record.get("rating_raw", "")).strip()
        rating = _RATING_MAP.get(rating_word, 0)

        cleaned.append(
            {
                "upc": upc,
                "title": str(record.get("title", "")).strip(),
                "price_gbp": _clean_price(record.get("price_raw", "")),
                "price_excl_tax_gbp": _clean_price(
                    record.get("price_excl_tax_raw", "")
                ),
                "tax_gbp": _clean_price(record.get("tax_raw", "")),
                "stock": _clean_availability(record.get("availability_raw", "")),
                "rating": rating,
                "category": str(record.get("category", "")).strip(),
                "description": str(record.get("description", "")).strip() or None,
                "img_url": record.get("img_url"),
                "source_url": record.get("source_url"),
            }
        )

    _logger.info(
        "Transformation terminée : %d livres propres, %d doublon(s) supprimé(s)",
        len(cleaned),
        duplicates,
    )
    return {
        "clean_records": cleaned,
        "clean_count": len(cleaned),
        "duplicates_removed": duplicates,
    }


def load_to_warehouse(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Écriture dans le DWH (staging schema)."""
    clean: list[dict[str, Any]] = context.get_step_output("clean_and_type")[
        "clean_records"
    ]
    if not clean:
        _logger.warning("Aucun enregistrement propre à charger — skip")
        return {"rows_upserted": 0, "skipped": True}

    wh = Warehouse.from_env()
    _logger.info("Chargement de %d livre(s) dans staging_stg_books", len(clean))
    rows = wh.upsert(
        table="staging_stg_books",
        data=clean,
        key="upc",
    )
    _logger.info("Upsert terminé : %d ligne(s) écrite(s)", rows)
    return {"rows_upserted": rows, "skipped": False}


def quality_check(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Vérifications post-chargement."""
    wh = Warehouse.from_env()
    count = wh.query_scalar("SELECT COUNT(*) FROM staging_stg_books")
    null_prices = wh.query_scalar(
        "SELECT COUNT(*) FROM staging_stg_books WHERE price_gbp IS NULL"
    )
    null_titles = wh.query_scalar(
        "SELECT COUNT(*) FROM staging_stg_books WHERE title IS NULL OR title = ''"
    )
    _logger.info(
        "Quality check staging_stg_books : %d lignes, %d prix null, %d titres null/vides",
        count or 0,
        null_prices or 0,
        null_titles or 0,
    )
    quality_passed = (null_prices or 0) == 0 and (null_titles or 0) == 0
    if not quality_passed:
        _logger.warning("Quality check échoué sur staging_stg_books")
    return {
        "total_rows": count,
        "null_prices": null_prices,
        "null_titles": null_titles,
        "quality_passed": quality_passed,
    }


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="transform-stg-books",
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

    result = WorkflowEngine().run(job, initial_context={"partition": "2026-04-12"})
    print(f"Terminé : {result.status}")  # noqa: T201
