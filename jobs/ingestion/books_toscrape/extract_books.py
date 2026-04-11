"""
Ingestion — Books.toscrape.com → Data Lake (raw).

Fréquence : quotidien (02h00 UTC)
Source    : HTTP scraping books.toscrape.com
Cible     : datalake://raw/books_toscrape/books/{date}/
Owner     : data-team@company.com

Variables d'environnement :
    BOOKS_BASE_URL       : URL de base (défaut : http://books.toscrape.com/)
    BOOKS_MAX_PAGES      : Nombre max de pages par catégorie (0 = illimité)
    BOOKS_CATEGORIES     : Catégories à scraper, séparées par virgule (vide = toutes)
    DATALAKE_PATH        : Répertoire racine du Data Lake
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.ingestion.books_toscrape.client import BooksToScrapeClient
from jobs.shared.datalake import DataLake

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext

_logger = get_logger("jobs.ingestion.books_toscrape.extract")

# ── Steps ────────────────────────────────────────────────────────────────


def scrape_catalogue(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Scraping du catalogue books.toscrape.com.

    Respecte les variables d'environnement ``BOOKS_*`` pour configurer
    le périmètre (catégories, pages max) et le délai poli.
    """
    _logger.info("Démarrage du scraping — books.toscrape.com")
    client = BooksToScrapeClient.from_env()
    books = client.fetch_catalogue()
    _logger.info("Scraping terminé : %d livres extraits", len(books))

    if not books:
        _logger.warning("Aucun livre extrait — pipeline ignorée")

    return {"raw_books": books, "count": len(books)}


def validate_raw(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Validation minimale avant écriture (schéma, non-vide)."""
    raw: list[dict[str, Any]] = context.get_step_output("scrape_catalogue")["raw_books"]
    count = len(raw)

    _logger.info("Validation des données brutes : %d enregistrement(s)", count)

    if not raw:
        _logger.warning("Validation : aucun enregistrement à valider — skip load")
        return {"status": "empty", "skip_load": True, "invalid_count": 0}

    required = {"upc", "title", "price_raw", "category", "rating_raw"}
    invalid = [r for r in raw if not required.issubset(r.keys())]

    if invalid:
        _logger.error(
            "Validation échouée : %d enregistrement(s) manquent les champs requis %s",
            len(invalid),
            required,
        )
        msg = f"{len(invalid)} records missing required fields {required}"
        raise ValueError(msg)

    _logger.info("Validation réussie : %d livres valides, 0 invalide", count)
    return {"status": "valid", "skip_load": False, "invalid_count": 0}


def load_to_datalake(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Écriture brute (JSON) dans le Data Lake.

    Partition par date d'ingestion : ``raw/books_toscrape/books/{date}/``.
    """
    validate = context.get_step_output("validate_raw")
    if validate.get("skip_load"):
        _logger.info("Chargement ignoré (skip_load=True)")
        return {"rows_written": 0, "skipped": True}

    dl = DataLake.from_env()
    partition = context.get("ingest_date", "latest")
    raw_books: list[dict[str, Any]] = context.get_step_output("scrape_catalogue")[
        "raw_books"
    ]
    path = f"raw/books_toscrape/books/{partition}/"

    _logger.info("Écriture dans le Data Lake : %d livres → %s", len(raw_books), path)
    rows = dl.write_json(path, raw_books)
    _logger.info("Data Lake : %d lignes écrites dans %s", rows, path)

    return {"rows_written": rows, "path": path}


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="ingestion-books-toscrape",
    version="1.0.0",
    steps=[
        Step(
            name="scrape_catalogue",
            step_type=StepType.FUNCTION,
            handler=scrape_catalogue,
        ),
        Step(
            name="validate_raw",
            step_type=StepType.FUNCTION,
            handler=validate_raw,
            dependencies=["scrape_catalogue"],
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
    from datetime import UTC, datetime

    from pyworkflow_engine import WorkflowEngine

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    result = WorkflowEngine().run(job, initial_context={"ingest_date": today})
    print(f"Terminé : {result.status}")  # noqa: T201
