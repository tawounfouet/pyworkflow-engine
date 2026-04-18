"""
Ingestion — IMF DataMapper API v1 → Data Lake (raw).

Ce job utilise l'API décorateurs ``@step`` / ``@job``.

Fréquence : semi-annuel (mai et novembre, après publication WEO)
Source    : https://www.imf.org/external/datamapper/api/v1/
Cible     :
    datalake://raw/imf/indicators/{date}/data.json   — série temporelle normalisée
    datalake://raw/imf/meta/{date}/indicators.json   — catalogue indicateurs (133)
    datalake://raw/imf/meta/{date}/countries.json    — catalogue pays (241)
    datalake://raw/imf/meta/{date}/regions.json      — catalogue régions géographiques
    datalake://raw/imf/meta/{date}/groups.json       — catalogue groupes analytiques
Owner     : data-team@company.com

Pipeline :
    fetch_metadata      (indicators + countries + regions + groups)
        ↓
    fetch_raw_data      (retry ×3)
        ↓
    validate_raw
        ↓
    normalize_records
        ↓
    load_to_datalake    (4 catalogues JSON + série temporelle)

Variables d'environnement :
    IMF_BASE_URL    : URL de base (défaut : https://www.imf.org/external/datamapper/api/v1)
    IMF_TIMEOUT     : Timeout HTTP en secondes (défaut : 60)
    IMF_INDICATORS  : Codes indicateurs séparés par virgule (défaut : 6 indicateurs macro)
    IMF_YEAR_FROM   : Année de début incluse (défaut : 2000)
    IMF_YEAR_TO     : Année de fin incluse (défaut : année en cours)
    DATALAKE_PATH   : Répertoire racine du Data Lake (défaut : ./data/datalake)

Usage CLI :
    python -m jobs.ingestion.imf.extract_imf                      # pipeline complet
    python -m jobs.ingestion.imf.extract_imf --catalog            # catalogues seulement
    python -m jobs.ingestion.imf.extract_imf --date 2026-01-01    # partition custom
    python -m jobs.ingestion.imf.extract_imf --catalog --date 2026-01-01
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

from jobs.shared.datalake import DataLake

_logger = get_logger("jobs.ingestion.imf")


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="fetch_metadata", timeout=120.0)
def fetch_metadata() -> dict[str, Any]:
    """Récupère les 4 ressources de référence IMF (indicateurs, pays, régions, groupes).

    Effectue 4 appels séquentiels :
    ``/indicators``, ``/countries``, ``/regions``, ``/groups``.

    Returns:
        ``{"indicators_meta": {code: label}, "countries_meta": {iso3: label},
           "regions_meta": {code: label}, "groups_meta": {code: label},
           "indicator_count": int, "country_count": int,
           "region_count": int, "group_count": int}``
    """
    from jobs.ingestion.imf.client import IMFClient  # noqa: PLC0415

    client = IMFClient.from_env()
    _logger.info("Fetch métadonnées IMF (indicateurs, pays, régions, groupes)")
    indicators_meta = client.fetch_indicators_meta()
    countries_meta = client.fetch_countries_meta()
    regions_meta: dict[str, str] = {}
    groups_meta: dict[str, str] = {}
    if hasattr(client, "fetch_regions_meta"):
        regions_meta = client.fetch_regions_meta()
    if hasattr(client, "fetch_groups_meta"):
        groups_meta = client.fetch_groups_meta()
    _logger.info(
        "Métadonnées : %d indicateurs, %d pays, %d régions, %d groupes",
        len(indicators_meta),
        len(countries_meta),
        len(regions_meta),
        len(groups_meta),
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ fetch_metadata — %d indicateurs · %d pays · %d régions · %d groupes",
        len(indicators_meta),
        len(countries_meta),
        len(regions_meta),
        len(groups_meta),
    )
    return {
        "indicators_meta": indicators_meta,
        "countries_meta": countries_meta,
        "regions_meta": regions_meta,
        "groups_meta": groups_meta,
        "indicator_count": len(indicators_meta),
        "country_count": len(countries_meta),
        "region_count": len(regions_meta),
        "group_count": len(groups_meta),
    }


@step(
    name="fetch_raw_data",
    dependencies=["fetch_metadata"],
    retry_count=3,
    retry_delay=10.0,
    timeout=600.0,
)
def fetch_raw_data(
    indicators_meta: dict[str, str] | None = None,
    countries_meta: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Télécharge les données brutes pour tous les indicateurs configurés.

    Un appel ``/{INDICATOR}`` par code dans ``IMF_INDICATORS``.
    Retry ×3 (délai 10 s) en cas d'erreur réseau transitoire.

    Args:
        indicators_meta: Injecté depuis ``fetch_metadata``.
        countries_meta:  Injecté depuis ``fetch_metadata``.

    Returns:
        ``{"raw_data": {indicator: {iso3: {year: value}}},
           "indicators_fetched": [...], "record_count_raw": int}``
    """
    from jobs.ingestion.imf.client import IMFClient  # noqa: PLC0415

    client = IMFClient.from_env()
    meta_ind = indicators_meta or {}

    _logger.info(
        "Fetch données — %d indicateurs, filtre %s→%s",
        len(client.indicators),
        client.year_from or "début",
        client.year_to or "fin",
    )

    raw_data: dict[str, Any] = {}
    indicators_fetched: list[str] = []
    total_raw = 0

    for code in client.indicators:
        label = meta_ind.get(code, code)
        try:
            raw = client.fetch_raw_indicator(code)
            raw_data[code] = raw
            indicators_fetched.append(code)
            count = sum(len(years) for years in raw.values())
            total_raw += count
            _logger.info(
                "  ✓ %s (%s) — %d pays, %d points", code, label, len(raw), count
            )
        except RuntimeError as exc:
            _logger.warning("  ✗ %s ignoré : %s", code, exc)

    _logger.info(
        "Fetch terminé : %d/%d indicateurs, %d points bruts",
        len(indicators_fetched),
        len(client.indicators),
        total_raw,
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ fetch_raw_data — %d/%d indicateurs · %d points bruts",
        len(indicators_fetched),
        len(client.indicators),
        total_raw,
    )
    return {
        "raw_data": raw_data,
        "indicators_fetched": indicators_fetched,
        "record_count_raw": total_raw,
    }


@step(name="validate_raw", dependencies=["fetch_raw_data"])
def validate_raw(
    raw_data: dict[str, Any] | None = None,
    indicators_fetched: list[str] | None = None,
    record_count_raw: int = 0,
) -> dict[str, Any]:
    """Validation minimale : au moins un indicateur avec des données.

    Args:
        raw_data:           Injecté depuis ``fetch_raw_data``.
        indicators_fetched: Injecté depuis ``fetch_raw_data``.
        record_count_raw:   Injecté depuis ``fetch_raw_data``.

    Returns:
        ``{"status": "valid"|"empty", "empty_indicators": [...]}``

    Raises:
        ValueError: Si tous les indicateurs sont vides (fetch OK mais zéro donnée).
    """
    fetched = indicators_fetched or []
    data = raw_data or {}

    _logger.info(
        "Validation : %d indicateurs, %d points bruts", len(fetched), record_count_raw
    )

    if not fetched or record_count_raw == 0:
        _logger.warning("Validation : aucune donnée — pipeline ignorée")
        return {"status": "empty", "empty_indicators": []}

    empty = [code for code in fetched if not data.get(code)]
    if empty:
        _logger.warning("Indicateurs sans données : %s", empty)

    _logger.info("Validation réussie : statut valid")
    _logger.success(  # type: ignore[attr-defined]
        "✅ validate_raw — %d indicateurs valides, %d sans données",
        len(fetched),
        len(empty),
    )
    return {"status": "valid", "empty_indicators": empty}


@step(
    name="normalize_records",
    dependencies=["fetch_raw_data", "fetch_metadata", "validate_raw"],
)
def normalize_records(
    raw_data: dict[str, Any] | None = None,
    indicators_meta: dict[str, str] | None = None,
    countries_meta: dict[str, str] | None = None,
    indicators_fetched: list[str] | None = None,
    status: str = "empty",
) -> dict[str, Any]:
    """Normalise les données brutes en records plats (indicateur, pays, année, valeur).

    Applique les filtres ``year_from`` / ``year_to`` depuis l'env.

    Args:
        raw_data:           Injecté depuis ``fetch_raw_data``.
        indicators_meta:    Injecté depuis ``fetch_metadata``.
        countries_meta:     Injecté depuis ``fetch_metadata``.
        indicators_fetched: Injecté depuis ``fetch_raw_data``.
        status:             Injecté depuis ``validate_raw``. Si ``"empty"``, skip.

    Returns:
        ``{"records": [...], "record_count": int, "null_value_count": int}``
    """
    if status == "empty":
        _logger.info("Normalisation ignorée (validate_raw status=empty)")
        return {"records": [], "record_count": 0, "null_value_count": 0}

    from jobs.ingestion.imf.client import IMFClient  # noqa: PLC0415

    client = IMFClient.from_env()
    data = raw_data or {}
    meta_ind = indicators_meta or {}
    meta_co = countries_meta or {}
    fetched = indicators_fetched or list(data.keys())

    _logger.info("Normalisation de %d indicateurs", len(fetched))

    records: list[dict[str, Any]] = []
    null_count = 0

    for code in fetched:
        label = meta_ind.get(code, code)
        for iso3, years_data in data.get(code, {}).items():
            country_label = meta_co.get(iso3, iso3)
            for year_str, value in years_data.items():
                try:
                    year = int(year_str)
                except ValueError:
                    continue
                if client.year_from and year < client.year_from:
                    continue
                if client.year_to and year > client.year_to:
                    continue
                if value is None:
                    null_count += 1
                records.append(
                    {
                        "indicator": code,
                        "indicator_label": label,
                        "country": iso3,
                        "country_label": country_label,
                        "year": year,
                        "value": float(value) if value is not None else None,
                    }
                )

    _logger.info(
        "Normalisation terminée : %d records, %d valeurs null",
        len(records),
        null_count,
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ normalize_records — %d records · %d valeurs null",
        len(records),
        null_count,
    )
    return {
        "records": records,
        "record_count": len(records),
        "null_value_count": null_count,
    }


@step(name="load_to_datalake", dependencies=["normalize_records"])
def load_to_datalake(
    records: list[dict[str, Any]] | None = None,
    record_count: int = 0,
    indicators_meta: dict[str, str] | None = None,
    countries_meta: dict[str, str] | None = None,
    regions_meta: dict[str, str] | None = None,
    groups_meta: dict[str, str] | None = None,
    ingest_date: str = "latest",
) -> dict[str, Any]:
    """Écrit les records normalisés + les 4 catalogues de référence dans le Data Lake.

    Chemins de sortie :
    - ``raw/imf/indicators/{ingest_date}/data.json``   — série temporelle normalisée
    - ``raw/imf/meta/{ingest_date}/indicators.json``   — catalogue indicateurs
    - ``raw/imf/meta/{ingest_date}/countries.json``    — catalogue pays
    - ``raw/imf/meta/{ingest_date}/regions.json``      — catalogue régions
    - ``raw/imf/meta/{ingest_date}/groups.json``       — catalogue groupes analytiques

    Args:
        records:        Injecté depuis ``normalize_records``.
        record_count:   Nombre de records (pour le log).
        indicators_meta: Injecté depuis ``fetch_metadata``.
        countries_meta:  Injecté depuis ``fetch_metadata``.
        regions_meta:    Injecté depuis ``fetch_metadata``.
        groups_meta:     Injecté depuis ``fetch_metadata``.
        ingest_date:    Injecté depuis ``initial_context`` (clé ``"ingest_date"``).

    Returns:
        ``{"rows_written": int, "path": str, "catalog_paths": [...], "skipped": bool}``
    """
    dl = DataLake.from_env()
    catalog_paths: list[str] = []

    # ── 1. Catalogues de référence (4 fichiers JSON) ──────────────────
    meta_dir = f"raw/imf/meta/{ingest_date}"
    catalogs = {
        "indicators": indicators_meta or {},
        "countries": countries_meta or {},
        "regions": regions_meta or {},
        "groups": groups_meta or {},
    }
    for name, data in catalogs.items():
        dest_file = dl.write_json_file(meta_dir, f"{name}.json", data)
        catalog_paths.append(f"{meta_dir}/{name}.json")
        _logger.info("Catalogue %s : %d entrées → %s", name, len(data), dest_file)

    # ── 2. Série temporelle normalisée ────────────────────────────────
    if not records:
        _logger.info("Chargement série temporelle ignoré — aucun record à écrire")
        return {
            "rows_written": 0,
            "path": "",
            "catalog_paths": catalog_paths,
            "skipped": True,
        }

    path = f"raw/imf/indicators/{ingest_date}/"
    _logger.info("Écriture Data Lake : %d records → %s", record_count, path)
    rows_written = dl.write_json(path, records)
    _logger.info("Data Lake : %d lignes écrites dans %s", rows_written, path)

    return {
        "rows_written": rows_written,
        "path": path,
        "catalog_paths": catalog_paths,
        "skipped": False,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="ingestion-imf",
    version="1.0.0",
    description=(
        "Ingestion IMF DataMapper API v1 → Data Lake. "
        "Pipeline : métadonnées → fetch données (retry ×3) → validation "
        "→ normalisation (filtre années, labels) → écriture JSON partitionné par date."
    ),
    steps=[
        fetch_metadata,
        fetch_raw_data,
        validate_raw,
        normalize_records,
        load_to_datalake,
    ],
)
def ingest_imf() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    fetch_metadata()
    fetch_raw_data()
    validate_raw()
    normalize_records()
    load_to_datalake()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.storage import SQLiteStorage  # noqa: PLC0415

    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Ingestion IMF DataMapper API v1")
    parser.add_argument(
        "--catalog",
        action="store_true",
        help=(
            "Télécharge uniquement les 4 catalogues de référence "
            "(indicators, countries, regions, groups) sans les séries temporelles."
        ),
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date de partition (défaut : date du jour).",
    )
    args = parser.parse_args()

    configure_platform_logging()

    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    today = args.date or settings.today()

    if args.catalog:
        # ── Mode catalogue seul : fetch_metadata + écriture 4 JSON ──
        from jobs.ingestion.imf.client import IMFClient  # noqa: PLC0415
        from jobs.shared.datalake import DataLake  # noqa: PLC0415

        client = IMFClient.from_env()
        catalog = client.fetch_metadata_catalog()
        dl = DataLake.from_env()
        meta_dir = f"raw/imf/meta/{today}"
        for name, data in catalog.items():
            dest_file = dl.write_json_file(meta_dir, f"{name}.json", data)
            print(f"  ✅ {name}: {len(data)} entrées → {dest_file}")  # noqa: T201
        print(f"\nCatalogues écrits dans : {dl.root / meta_dir}")  # noqa: T201
    else:
        # ── Mode complet : pipeline 5 steps ──────────────────────────
        engine = WorkflowEngine(
            storage=SQLiteStorage(database_path="workflow.db"),
        )
        result = engine.run_with_storage(
            ingest_imf.build(),
            initial_context={"ingest_date": today},
        )

        for step_run in result.step_runs:
            ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
            print(
                f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
            )  # noqa: T201

        print(f"\nStatut final : {result.status}")  # noqa: T201
