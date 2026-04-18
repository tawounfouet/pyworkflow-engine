"""
Transformation — Raw REST Countries → Staging (DWH).

Fréquence : hebdomadaire (dimanche 03h00 UTC, après ingestion restcountries)
Source    : datalake://raw/restcountries/countries/{date}/
Cible     : DWH staging_stg_countries (DuckDB / Postgres)
Owner     : data-team@company.com

Transformations appliquées :
    - Typage strict des champs numériques (``area``, ``population``)
    - Normalisation des listes (``languages``, ``currencies``, ``timezones``)
      → chaînes jointes par ``|`` pour stockage relationnel simple
    - Extraction du nom officiel EN et FR
    - Déduplication sur ``iso_alpha2``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models import Job, Step
from pyworkflow_engine.models.enums import StepType

from jobs.shared.datalake import DataLake
from jobs.shared.warehouse import Warehouse

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext

_logger = get_logger("jobs.transformation.staging.stg_restcountries")


# ── Helpers ──────────────────────────────────────────────────────────────


def _join_list(value: Any, sep: str = "|") -> str | None:
    """Normalise une liste ou une valeur scalaire en chaîne jointe.

    ``["fr", "en"]`` → ``"fr|en"``
    ``"fr"`` → ``"fr"``
    ``None`` / ``[]`` → ``None``
    """
    if not value:
        return None
    if isinstance(value, list):
        cleaned = [str(v).strip() for v in value if v]
        return sep.join(cleaned) if cleaned else None
    return str(value).strip() or None


def _safe_float(value: Any) -> float | None:
    """Convertit en float, retourne ``None`` si impossible."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    """Convertit en int, retourne ``None`` si impossible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ── Steps ────────────────────────────────────────────────────────────────


def read_from_datalake(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Lecture des pays normalisés depuis le Data Lake."""
    dl = DataLake.from_env()
    partition = context.get("partition", "latest")
    path = f"raw/restcountries/countries/{partition}/"
    _logger.info("Lecture Data Lake : %s", path)
    raw = dl.read_json(path)
    _logger.info("%d enregistrement(s) brut(s) lus", len(raw))
    return {"raw_records": raw, "source_count": len(raw)}


def _map_record(record: dict[str, Any], iso2: str) -> dict[str, Any]:
    """Mappe un enregistrement brut vers le schéma staging."""
    capital_raw = record.get("capital")
    if isinstance(capital_raw, list):
        capital = capital_raw[0] if capital_raw else None
    else:
        capital = capital_raw or None

    return {
        "iso_alpha2": iso2,
        "iso_alpha3": str(record.get("iso_alpha3", "")).strip().upper() or None,
        "name_common_en": str(record.get("name_common_en", "")).strip() or None,
        "name_official_en": str(record.get("name_official_en", "")).strip() or None,
        "name_common_fr": str(record.get("name_common_fr", "")).strip() or None,
        "name_official_fr": str(record.get("name_official_fr", "")).strip() or None,
        "region": str(record.get("region", "")).strip() or None,
        "subregion": str(record.get("subregion", "")).strip() or None,
        "capital": str(capital).strip() if capital else None,
        "area_km2": _safe_float(record.get("area")),
        "population": _safe_int(record.get("population")),
        "independent": bool(record.get("independent")),
        "un_member": bool(record.get("un_member")),
        "landlocked": bool(record.get("landlocked")),
        "currencies": _join_list(record.get("currencies")),
        "languages": _join_list(record.get("languages")),
        "timezones": _join_list(record.get("timezones")),
        "flag_emoji": record.get("flag_emoji"),
        "flag_png_url": record.get("flag_png_url"),
        "google_maps_url": record.get("google_maps_url"),
    }


def clean_and_type(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Typage, normalisation des listes, déduplication par ``iso_alpha2``.

    Transformations :
    - ``area`` et ``population`` castés en float/int
    - ``languages``, ``currencies``, ``timezones`` joints en chaîne ``|``
    - ``capital`` : premier élément si liste
    - Déduplication sur ``iso_alpha2``
    """
    raw: list[dict[str, Any]] = context.get_step_output("read_from_datalake")[
        "raw_records"
    ]

    if not raw:
        _logger.warning("Aucun enregistrement brut à transformer")
        return {"clean_records": [], "clean_count": 0, "duplicates_removed": 0}

    _logger.info("Transformation de %d enregistrement(s)", len(raw))

    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    duplicates = 0

    for record in raw:
        iso2 = str(record.get("iso_alpha2", "")).strip().upper()
        if not iso2:
            _logger.warning("Enregistrement sans iso_alpha2 ignoré : %s", record)
            continue
        if iso2 in seen:
            duplicates += 1
            _logger.debug("Doublon ignoré : %s", iso2)
            continue
        seen.add(iso2)
        cleaned.append(_map_record(record, iso2))

    _logger.info(
        "Transformation terminée : %d pays propres, %d doublon(s) supprimé(s)",
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
    _logger.info("Chargement de %d pays dans staging_stg_countries", len(clean))
    rows = wh.upsert(
        table="staging_stg_countries",
        data=clean,
        key="iso_alpha2",
    )
    _logger.info("Upsert terminé : %d ligne(s) écrite(s)", rows)
    return {"rows_upserted": rows, "skipped": False}


def quality_check(context: WorkflowContext) -> dict[str, Any]:  # type: ignore[type-arg]
    """Vérifications post-chargement sur staging_stg_countries."""
    load_result = context.get_step_output("load_to_warehouse")
    if load_result.get("skipped"):
        _logger.info("Quality check ignoré — aucune donnée chargée")
        return {
            "total_rows": 0,
            "null_names": 0,
            "null_regions": 0,
            "quality_passed": True,
            "skipped": True,
        }

    wh = Warehouse.from_env()
    count = wh.query_scalar("SELECT COUNT(*) FROM staging_stg_countries")
    null_names = wh.query_scalar(
        "SELECT COUNT(*) FROM staging_stg_countries "
        "WHERE name_common_en IS NULL OR name_common_en = ''"
    )
    null_regions = wh.query_scalar(
        "SELECT COUNT(*) FROM staging_stg_countries WHERE region IS NULL OR region = ''"
    )
    _logger.info(
        "Quality check staging_stg_countries : %d lignes, %d noms null, %d régions null",
        count or 0,
        null_names or 0,
        null_regions or 0,
    )
    quality_passed = (null_names or 0) == 0
    if not quality_passed:
        _logger.warning("Quality check échoué sur staging_stg_countries")
    return {
        "total_rows": count,
        "null_names": null_names,
        "null_regions": null_regions,
        "quality_passed": quality_passed,
    }


# ── Job definition ───────────────────────────────────────────────────────

job = Job(
    name="transform-stg-restcountries",
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

    from jobs.shared.logging import configure_platform_logging

    configure_platform_logging()

    result = WorkflowEngine().run(job, initial_context={"partition": "2026-04-12"})
    print(f"Terminé : {result.status}")  # noqa: T201
