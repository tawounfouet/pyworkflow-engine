"""
Ingestion — codes.droit.org (XML) → Data Lake (raw).

Ce job utilise l'API décorateurs ``@step`` / ``@job``.

Fréquence : hebdomadaire (dimanche 03h00 UTC) — les codes changent rarement
Source    : https://codes.droit.org/payloads/
Cible     : datalake://raw/codes_droit/{slug}/{date}/{slug}.xml
Owner     : data-team@company.com

Pipeline :
    fetch_codes        (téléchargement HTTP, retry ×2, fallback SSL)
        ↓
    validate_downloads (au moins un succès, log les échecs partiels)
        ↓
    load_to_datalake   (copie → Data Lake partitionné par slug + date)

Variables d'environnement :
    CODES_DROIT_BASE_URL : URL de base (défaut : https://codes.droit.org/payloads)
    CODES_DROIT_SLUGS    : Slugs séparés par virgule (défaut : tous)
    CODES_DROIT_TIMEOUT  : Timeout HTTP en secondes (défaut : 60)
    DATALAKE_PATH        : Répertoire racine du Data Lake (défaut : ./data/datalake)

Usage CLI :
    python -m jobs.ingestion.codes_droit.extract_codes
    python -m jobs.ingestion.codes_droit.extract_codes --slugs cgi,code_civil
    python -m jobs.ingestion.codes_droit.extract_codes --date 2026-04-15
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.ingestion.codes_droit")


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="fetch_codes", retry_count=2, retry_delay=10.0, timeout=600.0)
def fetch_codes() -> dict[str, Any]:
    """Télécharge tous les codes XML configurés dans un répertoire temporaire.

    Supporte un sous-ensemble via ``CODES_DROIT_SLUGS``.
    Retry automatique ×2 (délai 10 s) en cas d'erreur réseau.
    Fallback SSL intégré (identique à ``_archives/download_cgi_xml.py``).

    Returns:
        ``{"results": [...], "success_count": int, "error_count": int, "tmp_dir": str}``
    """
    from jobs.ingestion.codes_droit.client import DroitCodesClient  # noqa: PLC0415

    client = DroitCodesClient.from_env()
    tmp_dir = tempfile.mkdtemp(prefix="codes_droit_")

    _logger.info(
        "Téléchargement de %d code(s) → tmpdir %s",
        len(client.resolved_codes()),
        tmp_dir,
    )

    results = client.download_all(tmp_dir)
    success_count = sum(1 for r in results if r.success)
    error_count = len(results) - success_count

    _logger.success(  # type: ignore[attr-defined]
        "✅ fetch_codes — %d/%d codes téléchargés (%d échec(s))",
        success_count,
        len(results),
        error_count,
    )
    return {
        "results": [r.to_dict() for r in results],
        "success_count": success_count,
        "error_count": error_count,
        "tmp_dir": tmp_dir,
    }


@step(name="validate_downloads", dependencies=["fetch_codes"])
def validate_downloads(
    results: list[dict[str, Any]] | None = None,
    success_count: int = 0,
    error_count: int = 0,
) -> dict[str, Any]:
    """Vérifie qu'au moins un code a été téléchargé avec succès.

    Les échecs partiels sont loggés en warning mais ne bloquent pas le pipeline.
    Seul ``success_count == 0`` lève une exception.

    Args:
        results:       Injecté depuis ``fetch_codes``.
        success_count: Injecté depuis ``fetch_codes``.
        error_count:   Injecté depuis ``fetch_codes``.

    Returns:
        ``{"status": "valid"|"empty", "failed_slugs": [...]}``

    Raises:
        ValueError: Si aucun fichier n'a été téléchargé avec succès.
    """
    items = results or []
    failed_slugs = [r["slug"] for r in items if not r["success"]]

    if success_count == 0:
        raise ValueError(
            f"Aucun code téléchargé avec succès. "
            f"Échecs : {[r['slug'] for r in items]}"
        )

    if failed_slugs:
        _logger.warning("Codes en échec (non bloquant) : %s", failed_slugs)

    _logger.success(  # type: ignore[attr-defined]
        "✅ validate_downloads — %d succès · %d échec(s) : %s",
        success_count,
        error_count,
        failed_slugs or "aucun",
    )
    return {"status": "valid", "failed_slugs": failed_slugs}


@step(name="load_to_datalake", dependencies=["fetch_codes", "validate_downloads"])
def load_to_datalake(
    results: list[dict[str, Any]] | None = None,
    tmp_dir: str = "",
    status: str = "empty",
    ingest_date: str = "latest",
) -> dict[str, Any]:
    """Copie les fichiers XML vers le Data Lake, partitionnés par slug et date.

    Chemin de sortie : ``raw/codes_droit/{slug}/{ingest_date}/{slug}.xml``
    Le répertoire temporaire est supprimé après la copie.

    Args:
        results:     Injecté depuis ``fetch_codes``.
        tmp_dir:     Répertoire temporaire contenant les fichiers téléchargés.
        status:      Injecté depuis ``validate_downloads``. Si ``"empty"``, skip.
        ingest_date: Partition date — injecté depuis ``initial_context``
                     par le moteur (clé ``"ingest_date"``).

    Returns:
        ``{"files_written": int, "paths": [...], "skipped": bool}``
    """
    if status == "empty" or not results or not tmp_dir:
        _logger.info("Chargement ignoré — aucun fichier à écrire")
        return {"files_written": 0, "paths": [], "skipped": True}

    from jobs.shared.datalake import DataLake  # noqa: PLC0415

    dl = DataLake.from_env()
    paths: list[str] = []

    for r in results:
        if not r["success"]:
            continue
        slug = r["slug"]
        src = Path(r["output_path"])
        if not src.exists():
            _logger.warning("[%s] Fichier source introuvable : %s", slug, src)
            continue

        dest_dir = dl.root / f"raw/codes_droit/{slug}/{ingest_date}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{slug}.xml"

        shutil.copy2(src, dest_file)
        size_kb = dest_file.stat().st_size // 1024
        paths.append(str(dest_file))
        _logger.info("[%s] ✅ %d KB → %s", slug, size_kb, dest_file)

    # Nettoyage du répertoire temporaire
    shutil.rmtree(tmp_dir, ignore_errors=True)
    _logger.debug("Tmpdir supprimé : %s", tmp_dir)

    _logger.success(  # type: ignore[attr-defined]
        "✅ load_to_datalake — %d fichier(s) écrits dans le Data Lake",
        len(paths),
    )
    return {"files_written": len(paths), "paths": paths, "skipped": False}


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="ingestion-codes-droit",
    version="1.0.0",
    description=(
        "Ingestion codes.droit.org (XML) → Data Lake. "
        "Pipeline : téléchargement HTTP (retry ×2, fallback SSL) → validation "
        "→ écriture XML partitionné par code et date."
    ),
    steps=[fetch_codes, validate_downloads, load_to_datalake],
)
def ingest_codes_droit() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    fetch_codes()
    validate_downloads()
    load_to_datalake()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse  # noqa: PLC0415

    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.storage import SQLiteStorage  # noqa: PLC0415
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Ingestion codes.droit.org (XML) → Data Lake"
    )
    parser.add_argument(
        "--slugs",
        default=None,
        metavar="SLUG1,SLUG2",
        help=(
            "Codes à télécharger, séparés par virgule (défaut : tous). "
            "Ex: cgi,code_civil,code_penal"
        ),
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date de partition (défaut : date du jour).",
    )
    args = parser.parse_args()

    if args.slugs:
        os.environ["CODES_DROIT_SLUGS"] = args.slugs

    configure_platform_logging()
    today = args.date or settings.today()

    engine = WorkflowEngine(
        storage=SQLiteStorage(database_path="workflow.db"),
    )
    result = engine.run_with_storage(
        ingest_codes_droit.build(),
        initial_context={"ingest_date": today},
    )

    for step_run in result.step_runs:
        ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
        print(
            f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
        )  # noqa: T201

    print(f"\nStatut final : {result.status}")  # noqa: T201
