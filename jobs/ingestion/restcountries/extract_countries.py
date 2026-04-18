"""
Ingestion — REST Countries API v3.1 → Data Lake (raw).

Adapté depuis ``_archives/import_countries.py`` (commande de gestion Django).
Ce job utilise l'**API décorateurs** ``@step`` / ``@job`` au lieu de l'API
impérative ``Job(steps=[Step(...)])`` utilisée dans ``books_toscrape``.

Fréquence : hebdomadaire (dimanche 01h00 UTC) — les données changent rarement
Source    : https://restcountries.com/v3.1
Cible     : datalake://raw/restcountries/countries/{date}/
Owner     : data-team@company.com

Pipeline :
    fetch_raw
        ↓
    validate_raw
        ↓
    normalize_countries
        ↓
    load_to_datalake

Variables d'environnement :
    RESTCOUNTRIES_BASE_URL        : URL de base (défaut : https://restcountries.com/v3.1)
    RESTCOUNTRIES_INDEPENDENT_ONLY: "true" = pays indépendants seulement (défaut : false)
    RESTCOUNTRIES_TIMEOUT         : Timeout HTTP en secondes (défaut : 30)
    DATALAKE_PATH                 : Répertoire racine du Data Lake (défaut : ./data/datalake)

Usage CLI :
    python -m jobs.ingestion.restcountries.extract_countries
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

from jobs.ingestion.restcountries.client import RestCountriesClient
from jobs.shared.datalake import DataLake

_logger = get_logger("jobs.ingestion.restcountries.extract")


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="fetch_raw", retry_count=3, retry_delay=5.0, timeout=120.0)
def fetch_raw() -> dict[str, Any]:
    """Appelle l'API REST Countries et retourne les données brutes.

    Effectue 1 ou 2 requêtes HTTP selon ``RESTCOUNTRIES_INDEPENDENT_ONLY`` :
    - ``/independent?status=true``  — pays indépendants
    - ``/independent?status=false`` — territoires non-indépendants

    Retry automatique (×3, délai 5 s) en cas d'erreur réseau transitoire.

    Returns:
        ``{"raw_countries": [...], "count_raw": int}``
    """
    _logger.info("Démarrage du fetch — REST Countries API v3.1")
    client = RestCountriesClient.from_env()
    raw = client.fetch_raw()
    _logger.success("✅ fetch_raw — %d enregistrements bruts récupérés", len(raw))
    return {"raw_countries": raw, "count_raw": len(raw)}


@step(name="validate_raw", dependencies=["fetch_raw"])
def validate_raw(raw_countries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Validation minimale des données brutes avant normalisation.

    Vérifie que la liste n'est pas vide et que chaque enregistrement
    contient le champ obligatoire ``cca2`` (code ISO Alpha-2).

    Args:
        raw_countries: Injecté depuis l'output de ``fetch_raw``.

    Returns:
        ``{"status": "valid"|"empty", "invalid_count": int, "total": int}``

    Raises:
        ValueError: Si des enregistrements sont invalides (``cca2`` absent).
    """
    countries = raw_countries or []
    total = len(countries)
    _logger.info("Validation de %d enregistrements bruts", total)

    if not countries:
        _logger.warning("Validation : aucun enregistrement — pipeline ignorée")
        return {"status": "empty", "invalid_count": 0, "total": 0}

    invalid = [r for r in countries if not r.get("cca2")]
    if invalid:
        msg = f"{len(invalid)} enregistrements sans code ISO Alpha-2 (cca2)"
        _logger.error("Validation échouée : %s", msg)
        raise ValueError(msg)

    _logger.success("✅ validate_raw — %d enregistrements valides", total)
    return {"status": "valid", "invalid_count": 0, "total": total}


@step(name="normalize_countries", dependencies=["fetch_raw", "validate_raw"])
def normalize_countries(
    raw_countries: list[dict[str, Any]] | None = None,
    status: str = "empty",
) -> dict[str, Any]:
    """Normalise et dédoublonne les pays bruts.

    Utilise ``RestCountriesClient.fetch_normalized()`` pour parser chaque
    enregistrement (codes ISO, noms EN/FR, géographie, devises, langues,
    drapeaux, fuseaux horaires…) et dédoublonner par ``cca2``.

    Args:
        raw_countries: Injecté depuis l'output de ``fetch_raw``.
        status: Injecté depuis l'output de ``validate_raw``. Si ``"empty"``,
            le step retourne immédiatement sans traitement.

    Returns:
        ``{"countries": [...], "count": int, "error_count": int}``
    """
    if status == "empty":
        _logger.info("Normalisation ignorée (validate_raw status=empty)")
        return {"countries": [], "count": 0, "error_count": 0}

    countries = raw_countries or []
    _logger.info("Normalisation de %d enregistrements", len(countries))

    from jobs.ingestion.restcountries.client import parse_country  # noqa: PLC0415

    normalized: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []

    for i, raw in enumerate(countries):
        try:
            record = parse_country(raw)
            cca2: str = record["iso_alpha2"]
            if cca2 not in normalized:
                normalized[cca2] = record
            else:
                _logger.debug("Doublon ignoré : %s (index %d)", cca2, i)
        except (ValueError, KeyError) as exc:
            errors.append({"index": i, "cca2": raw.get("cca2", "?"), "error": str(exc)})
            _logger.warning("Erreur parsing index %d : %s", i, exc)

    result = list(normalized.values())
    _logger.success(
        "✅ normalize_countries — %d pays normalisés, %d erreurs",
        len(result),
        len(errors),
    )

    if errors:
        _logger.warning(
            "Détail des erreurs de parsing (%d) : %s",
            len(errors),
            errors[:5],  # log les 5 premières
        )

    return {"countries": result, "count": len(result), "error_count": len(errors)}


@step(name="load_to_datalake", dependencies=["normalize_countries"])
def load_to_datalake(
    countries: list[dict[str, Any]] | None = None,
    count: int = 0,
    ingest_date: str = "latest",
) -> dict[str, Any]:
    """Écrit les pays normalisés dans le Data Lake (partition par date).

    Chemin de sortie : ``raw/restcountries/countries/{ingest_date}/data.json``

    Args:
        countries: Injecté depuis l'output de ``normalize_countries``.
        count: Nombre de pays normalisés (pour le log).
        ingest_date: Partition date — injecté depuis ``initial_context``
            par le moteur (clé ``"ingest_date"``).

    Returns:
        ``{"rows_written": int, "path": str, "skipped": bool}``
    """
    if not countries:
        _logger.info("Chargement ignoré — aucun pays à écrire")
        return {"rows_written": 0, "path": "", "skipped": True}

    dl = DataLake.from_env()
    path = f"raw/restcountries/countries/{ingest_date}/"

    _logger.info(
        "Écriture dans le Data Lake : %d pays → %s",
        count,
        path,
    )
    rows_written = dl.write_json(path, countries)
    _logger.success(
        "✅ load_to_datalake — %d lignes écrites → %s",
        rows_written,
        path,
    )

    return {"rows_written": rows_written, "path": path, "skipped": False}


# ═══════════════════════════════════════════════════════════════════════════
# Job — composition des steps
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="ingestion-restcountries",
    version="1.0.0",
    description=(
        "Ingestion REST Countries API v3.1 → Data Lake. "
        "Pipeline : fetch (retry ×3) → validation → normalisation "
        "(dédoublonnage ISO Alpha-2, conversion types, noms EN/FR) → "
        "écriture JSON partitionné par date."
    ),
    steps=[fetch_raw, validate_raw, normalize_countries, load_to_datalake],
)
def ingest_restcountries() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    fetch_raw()
    validate_raw()
    normalize_countries()
    load_to_datalake()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from datetime import UTC, datetime

    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.adapters.storage import SQLiteStorage

    from jobs.shared.logging import configure_platform_logging

    configure_platform_logging()

    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    today = settings.today()

    engine = WorkflowEngine(
        storage=SQLiteStorage(database_path="workflow.db"),
    )

    result = engine.run_with_storage(
        ingest_restcountries.build(),
        initial_context={"ingest_date": today},
    )

    for step_run in result.step_runs:
        ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
        status_icon = "✅" if ok else "❌"
        print(f"  {status_icon} {step_run.step_name}: {step_run.status}")  # noqa: T201
        # if step_run.output_data:
        #     # Afficher une sélection de clés pertinentes sans le raw_data
        #     summary = {
        #         k: v for k, v in step_run.output_data.items() if k != "raw_countries"
        #     }
        #     print(f"     → {summary}")  # noqa: T201

    print(f"\nStatut final : {result.status}")  # noqa: T201
