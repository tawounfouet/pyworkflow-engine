"""
Embedding — articles JSON curated → vecteurs OpenAI (Job 3).

Ce job utilise l'API décorateurs ``@step`` / ``@job`` (ADR-005).

Fréquence : hebdomadaire (dimanche 04h00 UTC — après transform-codes-droit à 03h30)
Source    : datalake://curated/codes_droit/{slug}/{date}/{slug}_articles.json
Cible     : datalake://curated/codes_droit/{slug}/{date}/{slug}_embeddings.npy
                                                         {slug}_embeddings_metadata.json
Owner     : data-team@company.com

Partitionnement par code (ADR-025 amendement) :
    Chaque slug produit son propre fichier .npy + metadata, colocalisé
    avec le JSON d'articles. Permet la ré-exécution par code individuel.

Pipeline :
    load_articles_by_slug
        ↓   {"slugs": {"cgi": {"texts": [...], "metadata": [...]}, ...}}
    generate_embeddings_by_slug   (timeout=1800s)
        ↓   {"slugs": {"cgi": {"embeddings": [...], "shape": [N, dim]}, ...}}
    save_embeddings_by_slug
        →   {"files": [{"slug": str, "npy_path": str, "meta_path": str}, ...]}

Variables d'environnement :
    OPENAI_API_KEY          : Obligatoire
    EMBEDDING_MODEL         : Défaut text-embedding-3-large
    EMBEDDING_BATCH_SIZE    : Défaut 100
    EMBEDDING_CONTENT_TRUNC : Défaut 1500 (chars)
    DATALAKE_PATH           : Répertoire racine du Data Lake (défaut : ./data/datalake)

Usage CLI :
    python -m jobs.transformation.codes_droit.embed.embed_codes
    python -m jobs.transformation.codes_droit.embed.embed_codes --date 2026-04-15
    python -m jobs.transformation.codes_droit.embed.embed_codes --slugs cgi
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # Chargement .env avant tout import OpenAI / config

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.transformation.codes_droit.embed")


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="load_articles_by_slug")
def load_articles_by_slug(ingest_date: str = "latest") -> dict[str, Any]:
    """Charge les articles JSON depuis ``curated/``, groupés par slug.

    Returns:
        ``{"slugs": {slug: {"texts": [...], "metadata": [...], "date": str, "count": int}}}``
    """
    from jobs.shared.datalake import DataLake  # noqa: PLC0415
    from jobs.transformation.codes_droit.embed.config import (
        CONTENT_TRUNC,
    )  # noqa: PLC0415

    dl = DataLake.from_env()
    curated_base = dl.root / "curated/codes_droit"

    if not curated_base.exists():
        _logger.warning("Répertoire curated/codes_droit introuvable : %s", curated_base)
        return {"slugs": {}, "total_count": 0}

    slugs_data: dict[str, dict[str, Any]] = {}
    total = 0

    for slug_dir in sorted(curated_base.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name.startswith("_"):
            continue
        slug = slug_dir.name

        partitions = sorted(d.name for d in slug_dir.iterdir() if d.is_dir())
        if not partitions:
            continue

        date = ingest_date if ingest_date != "latest" else partitions[-1]
        articles_file = slug_dir / date / f"{slug}_articles.json"
        if not articles_file.exists():
            _logger.warning(
                "[%s] Fichier curated introuvable : %s", slug, articles_file
            )
            continue

        payload = json.loads(articles_file.read_text(encoding="utf-8"))
        articles: list[dict[str, Any]] = (
            payload.get("articles", payload) if isinstance(payload, dict) else payload
        )

        texts: list[str] = []
        metadata: list[dict[str, Any]] = []
        for article in articles:
            title = article.get("title", "")
            content = article.get("content", "")[:CONTENT_TRUNC]
            texts.append(f"{title}. {content}")
            metadata.append(
                {
                    "legiarti_id": article.get("legiarti_id", ""),
                    "slug": slug,
                    "number": article.get("number", ""),
                    "title": title,
                    "effective_date": article.get("effective_date", ""),
                }
            )

        slugs_data[slug] = {
            "texts": texts,
            "metadata": metadata,
            "date": date,
            "count": len(texts),
        }
        total += len(texts)
        _logger.info("[%s] %d articles chargés depuis %s", slug, len(texts), date)

    _logger.info(
        "load_articles_by_slug — %d textes dans %d code(s)", total, len(slugs_data)
    )
    return {"slugs": slugs_data, "total_count": total}


@step(
    name="generate_embeddings_by_slug",
    dependencies=["load_articles_by_slug"],
    timeout=1800.0,
)
def generate_embeddings_by_slug(
    slugs: dict[str, dict[str, Any]] | None = None,
    total_count: int = 0,
) -> dict[str, Any]:
    """Génère les embeddings OpenAI par slug, avec batches et normalisation L2."""
    import math  # noqa: PLC0415
    from openai import OpenAI  # noqa: PLC0415
    from jobs.transformation.codes_droit.embed.config import (
        BATCH_SIZE,
        DEFAULT_MODEL,
    )  # noqa: PLC0415

    slug_map = slugs or {}
    if not slug_map:
        _logger.warning("Aucun texte à embedder")
        return {"slugs": {}, "model": DEFAULT_MODEL, "total_count": 0}

    client = OpenAI()
    result_slugs: dict[str, dict[str, Any]] = {}
    global_total = 0

    for slug, data in slug_map.items():
        texts = data.get("texts", [])
        meta = data.get("metadata", [])
        date = data.get("date", "latest")

        if not texts:
            _logger.info("[%s] Aucun texte — skip", slug)
            continue

        n_batches = math.ceil(len(texts) / BATCH_SIZE)
        _logger.info(
            "[%s] Embedding de %d textes (%d batch(es))", slug, len(texts), n_batches
        )

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            _logger.info(
                "[%s] Batch %d/%d (%d textes)", slug, batch_num, n_batches, len(batch)
            )

            response = client.embeddings.create(model=DEFAULT_MODEL, input=batch)
            raw = [r.embedding for r in response.data]

            for vec in raw:
                norm = math.sqrt(sum(x * x for x in vec))
                all_embeddings.append([x / norm for x in vec] if norm > 0 else vec)

        dim = len(all_embeddings[0]) if all_embeddings else 0
        result_slugs[slug] = {
            "embeddings": all_embeddings,
            "shape": [len(all_embeddings), dim],
            "metadata": meta,
            "date": date,
        }
        global_total += len(all_embeddings)
        _logger.info("[%s] ✅ %d × %d", slug, len(all_embeddings), dim)

    _logger.success(  # type: ignore[attr-defined]
        "✅ generate_embeddings — %d vecteurs pour %d code(s) (modèle : %s)",
        global_total,
        len(result_slugs),
        DEFAULT_MODEL,
    )
    return {"slugs": result_slugs, "model": DEFAULT_MODEL, "total_count": global_total}


@step(name="save_embeddings_by_slug", dependencies=["generate_embeddings_by_slug"])
def save_embeddings_by_slug(
    slugs: dict[str, dict[str, Any]] | None = None,
    model: str = "",
    total_count: int = 0,
) -> dict[str, Any]:
    """Sauvegarde un .npy + metadata JSON par slug, colocalisé avec les articles.

    Chemin de sortie :
        ``curated/codes_droit/{slug}/{date}/{slug}_embeddings.npy``
        ``curated/codes_droit/{slug}/{date}/{slug}_embeddings_metadata.json``
    """
    import numpy as np  # noqa: PLC0415
    from jobs.shared.datalake import DataLake  # noqa: PLC0415

    slug_map = slugs or {}
    if not slug_map:
        _logger.warning("Aucun embedding à sauvegarder")
        return {"files": [], "total_count": 0}

    dl = DataLake.from_env()
    files: list[dict[str, str]] = []

    for slug, data in slug_map.items():
        vecs = data.get("embeddings", [])
        meta = data.get("metadata", [])
        date = data.get("date", "latest")
        shape = data.get("shape", [0, 0])

        if not vecs:
            continue

        dest_dir = dl.root / f"curated/codes_droit/{slug}/{date}"
        dest_dir.mkdir(parents=True, exist_ok=True)

        matrix = np.array(vecs, dtype=np.float32)
        npy_path = dest_dir / f"{slug}_embeddings.npy"
        np.save(str(npy_path), matrix)

        meta_path = dest_dir / f"{slug}_embeddings_metadata.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        size_mb = npy_path.stat().st_size / 1e6
        files.append(
            {"slug": slug, "npy_path": str(npy_path), "meta_path": str(meta_path)}
        )
        _logger.info("[%s] ✅ %s (%.1f Mo) + metadata", slug, shape, size_mb)

    _logger.success(  # type: ignore[attr-defined]
        "✅ save_embeddings — %d fichier(s) .npy écrits (%d vecteurs au total)",
        len(files),
        total_count,
    )
    return {"files": files, "total_count": total_count, "model": model}


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="embed-codes-droit",
    version="2.0.0",
    description=(
        "Embedding articles juridiques curated → vecteurs OpenAI normalisés (L2). "
        "Partitionnement par code : un .npy + metadata par slug, colocalisé "
        "avec les articles JSON."
    ),
    steps=[load_articles_by_slug, generate_embeddings_by_slug, save_embeddings_by_slug],
)
def embed_codes_droit() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    load_articles_by_slug()
    generate_embeddings_by_slug()
    save_embeddings_by_slug()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse  # noqa: PLC0415

    from dotenv import load_dotenv as _load_dotenv  # noqa: PLC0415

    _load_dotenv()

    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.storage import SQLiteStorage  # noqa: PLC0415
    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Embedding articles juridiques → .npy par code (Job 3)"
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date de partition curated (défaut : dernière date disponible).",
    )
    parser.add_argument(
        "--slugs",
        default=None,
        metavar="SLUG1,SLUG2",
        help="Codes à embedder (défaut : tous). Ex: cgi,code_civil",
    )
    args = parser.parse_args()

    if args.slugs:
        os.environ["CODES_DROIT_SLUGS"] = args.slugs

    configure_platform_logging()

    engine = WorkflowEngine(storage=SQLiteStorage(database_path="workflow.db"))
    result = engine.run_with_storage(
        embed_codes_droit.build(),
        initial_context={"ingest_date": args.date or "latest"},
    )

    for step_run in result.step_runs:
        ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
        print(f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}")

    print(f"\nStatut final : {result.status}")
