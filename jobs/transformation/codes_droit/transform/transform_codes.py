"""
Transformation — XML bruts codes.droit.org → articles JSON structurés (Job 2).

Ce job utilise l'API décorateurs ``@step`` / ``@job`` (ADR-005).

Fréquence : hebdomadaire (dimanche 03h30 UTC — après ingestion-codes-droit à 03h00)
Source    : datalake://raw/codes_droit/{slug}/{date}/{slug}.xml
Cible     : datalake://curated/codes_droit/{slug}/{date}/{slug}_articles.json
Owner     : data-team@company.com

Pipeline :
    load_raw_xml
        ↓   {"files": [...], "file_count": N}
    parse_articles
        ↓   {"articles_by_slug": {...}, "total_articles": N}
    save_curated
        →   {"files_written": N, "paths": [...]}

Variables d'environnement :
    DATALAKE_PATH : Répertoire racine du Data Lake (défaut : ./data/datalake)

Usage CLI :
    python -m jobs.transformation.codes_droit.transform.transform_codes
    python -m jobs.transformation.codes_droit.transform.transform_codes --date 2026-04-15
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.transformation.codes_droit.transform")


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="load_raw_xml")
def load_raw_xml(ingest_date: str = "latest") -> dict[str, Any]:
    """Découvre les fichiers XML bruts dans le Data Lake.

    Si ``ingest_date`` est ``"latest"``, utilise la dernière date disponible
    par tri lexicographique (ADR-025 D4).

    Returns:
        ``{"files": [{"slug": str, "path": str, "size_kb": int, "date": str}], "file_count": N}``
    """
    from jobs.shared.datalake import DataLake  # noqa: PLC0415

    dl = DataLake.from_env()
    raw_base = dl.root / "raw/codes_droit"

    if not raw_base.exists():
        _logger.warning("Répertoire raw/codes_droit introuvable : %s", raw_base)
        return {"files": [], "file_count": 0}

    files: list[dict[str, Any]] = []

    for slug_dir in sorted(raw_base.iterdir()):
        if not slug_dir.is_dir():
            continue
        slug = slug_dir.name

        partitions = dl.list_partitions(f"raw/codes_droit/{slug}")
        if not partitions:
            _logger.debug("[%s] Aucune partition disponible", slug)
            continue

        date = ingest_date if ingest_date != "latest" else partitions[-1]
        xml_path = raw_base / slug / date / f"{slug}.xml"

        if not xml_path.exists():
            _logger.warning("[%s] Fichier XML introuvable : %s", slug, xml_path)
            continue

        size_kb = xml_path.stat().st_size // 1024
        files.append(
            {"slug": slug, "path": str(xml_path), "size_kb": size_kb, "date": date}
        )
        _logger.info("[%s] Trouvé : %s (%d KB)", slug, xml_path.name, size_kb)

    _logger.info("load_raw_xml — %d fichier(s) XML détecté(s)", len(files))
    return {"files": files, "file_count": len(files)}


@step(name="parse_articles", dependencies=["load_raw_xml"])
def parse_articles(
    files: list[dict[str, Any]] | None = None,
    file_count: int = 0,
) -> dict[str, Any]:
    """Parse chaque fichier XML et extrait les articles VIGUEUR.

    Args:
        files:      Injecté depuis ``load_raw_xml``.
        file_count: Injecté depuis ``load_raw_xml``.

    Returns:
        ``{"articles_by_slug": {slug: [article, ...]}, "total_articles": N}``
    """
    from jobs.transformation.codes_droit.transform.parser import (  # noqa: PLC0415
        _extract_articles,
        extract_metadata,
    )

    items = files or []
    if not items:
        _logger.warning("Aucun fichier XML à parser")
        return {"articles_by_slug": {}, "metadata_by_slug": {}, "total_articles": 0}

    articles_by_slug: dict[str, list[dict[str, Any]]] = {}
    metadata_by_slug: dict[str, dict[str, Any]] = {}
    total = 0

    for f in items:
        slug = f["slug"]
        xml_path = Path(f["path"])
        meta = extract_metadata(xml_path)
        articles = _extract_articles(xml_path, slug)
        meta["articles_count"] = len(articles)
        articles_by_slug[slug] = articles
        metadata_by_slug[slug] = meta
        total += len(articles)
        _logger.info("[%s] %d article(s) VIGUEUR extrait(s)", slug, len(articles))

    _logger.info(
        "parse_articles — %d articles extraits depuis %d fichier(s)",
        total,
        len(items),
    )
    return {
        "articles_by_slug": articles_by_slug,
        "metadata_by_slug": metadata_by_slug,
        "total_articles": total,
    }


@step(name="save_curated", dependencies=["parse_articles"])
def save_curated(
    articles_by_slug: dict[str, list[dict[str, Any]]] | None = None,
    metadata_by_slug: dict[str, dict[str, Any]] | None = None,
    total_articles: int = 0,
    ingest_date: str = "latest",
) -> dict[str, Any]:
    """Sauvegarde les articles parsés en JSON structuré dans ``curated/``.

    Format de sortie identique à ``_archives/pytaxes-engine/data/cgi_database.json`` :

    .. code-block:: json

        {
            "metadata": {
                "source": "cgi.xml",
                "source_type": "xml",
                "code_nom": "Code général des impôts",
                "code_id": "LEGITEXT000006069577",
                "lastup": "2026-03-31",
                "build": "Beta 0.95.6",
                "articles_count": 2428
            },
            "articles": [ ... ]
        }

    Chemin de sortie :
        ``curated/codes_droit/{slug}/{ingest_date}/{slug}_articles.json``

    Args:
        articles_by_slug: Injecté depuis ``parse_articles``.
        metadata_by_slug: Injecté depuis ``parse_articles``.
        total_articles:   Injecté depuis ``parse_articles``.
        ingest_date:      Date de partition (depuis ``initial_context``).

    Returns:
        ``{"files_written": N, "paths": [...], "curated_date": str}``
    """
    from jobs.shared.datalake import DataLake  # noqa: PLC0415

    by_slug = articles_by_slug or {}
    meta_by_slug = metadata_by_slug or {}

    if not by_slug:
        _logger.warning("Aucun article à sauvegarder dans curated/")
        return {"files_written": 0, "paths": [], "curated_date": ingest_date}

    dl = DataLake.from_env()
    paths: list[str] = []

    for slug, articles in by_slug.items():
        if not articles:
            _logger.debug("[%s] Aucun article — skip curated", slug)
            continue

        dest_dir = dl.root / f"curated/codes_droit/{slug}/{ingest_date}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{slug}_articles.json"

        # Enveloppe {"metadata": {...}, "articles": [...]}
        payload = {
            "metadata": meta_by_slug.get(
                slug, {"source": f"{slug}.xml", "articles_count": len(articles)}
            ),
            "articles": articles,
        }

        dest_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        paths.append(str(dest_file))
        _logger.info("[%s] ✅ %d articles → %s", slug, len(articles), dest_file)

    _logger.success(  # type: ignore[attr-defined]
        "✅ save_curated — %d fichier(s) JSON écrits (%d articles au total)",
        len(paths),
        total_articles,
    )
    return {"files_written": len(paths), "paths": paths, "curated_date": ingest_date}


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="transform-codes-droit",
    version="1.0.0",
    description=(
        "Transformation XML bruts codes.droit.org → articles JSON structurés. "
        "Pipeline : découverte XML (raw/) → parsing Légifrance (VIGUEUR) "
        "→ sauvegarde JSON (curated/)."
    ),
    steps=[load_raw_xml, parse_articles, save_curated],
)
def transform_codes_droit() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    load_raw_xml()
    parse_articles()
    save_curated()


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
        description="Transformation XML codes.droit.org → articles JSON (Job 2)"
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date de partition source (défaut : dernière date disponible).",
    )
    args = parser.parse_args()

    configure_platform_logging()
    ingest_date = args.date or "latest"

    engine = WorkflowEngine(
        storage=SQLiteStorage(database_path="workflow.db"),
    )
    result = engine.run_with_storage(
        transform_codes_droit.build(),
        initial_context={"ingest_date": ingest_date},
    )

    for step_run in result.step_runs:
        ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
        print(
            f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
        )  # noqa: T201

    print(f"\nStatut final : {result.status}")  # noqa: T201
