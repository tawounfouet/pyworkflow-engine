"""
Indexation RAG — embeddings codes.droit.org → KnowledgeSource / Document / Chunk (Job 4).

Ce job utilise l'API décorateurs ``@step`` / ``@job`` (ADR-005).
Il alimente le sous-système RAG (ADR-023) via ``UnifiedStorage``.

Idempotent : si ``codes_droit_{date}`` est déjà indexée (statut INDEXED),
le job retourne immédiatement sans recréer les documents et chunks.

Fréquence : hebdomadaire (dimanche 04h30 UTC — après embed-codes-droit à 04h00)
Source    : datalake://curated/codes_droit/{slug}/{date}/{slug}_articles.json
            datalake://curated/codes_droit/{slug}/{date}/{slug}_embeddings.npy
                                                         {slug}_embeddings_metadata.json
Cible     : workflow.db → ai_knowledge_sources / ai_documents / ai_chunks
Owner     : data-team@company.com

Pipeline :
    create_knowledge_source
        ↓   {"source_id": str, "source_name": str, "skipped": bool}
    index_articles
        →   {"documents_count": N, "chunks_count": N, "source_id": str, "skipped": bool}

Variables d'environnement :
    DATALAKE_PATH : Répertoire racine du Data Lake (défaut : ./data/datalake)
    PYWORKFLOW_DB : Chemin SQLite (défaut : workflow.db)

Usage CLI :
    python -m jobs.transformation.codes_droit.index.index_codes
    python -m jobs.transformation.codes_droit.index.index_codes --date 2026-04-13
    python -m jobs.transformation.codes_droit.index.index_codes --date 2026-04-13 --force
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.transformation.codes_droit.index")


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="create_knowledge_source")
def create_knowledge_source(
    ingest_date: str = "latest",
    force_reindex: bool = False,
) -> dict[str, Any]:
    """Crée ou récupère la KnowledgeSource pour cette session d'ingestion.

    Idempotence (ADR-025 recommandation) :
    - Si ``codes_droit_{date}`` existe déjà avec statut ``INDEXED``
      et que ``force_reindex`` est ``False`` → retourne la source existante
      avec ``skipped=True``, sans rien recréer.
    - Sinon (PENDING / INDEXING / FAILED ou force) → crée / met à jour
      la source avec statut ``INDEXING``.

    Args:
        ingest_date:    Date de la session (depuis ``initial_context``).
        force_reindex:  Si ``True``, re-indexe même si déjà INDEXED.

    Returns:
        ``{"source_id": str, "source_name": str, "embedding_date": str, "skipped": bool}``
    """
    import os  # noqa: PLC0415

    from pyworkflow_engine.adapters.storage.unified import (
        UnifiedStorage,
    )  # noqa: PLC0415
    from pyworkflow_engine.models.ai.knowledge import KnowledgeSource  # noqa: PLC0415
    from pyworkflow_engine.models.ai.types import (
        IndexStatus,
        SourceType,
    )  # noqa: PLC0415

    from jobs.shared.datalake import DataLake  # noqa: PLC0415

    dl = DataLake.from_env()
    embedding_date = ingest_date

    if ingest_date == "latest":
        curated_base = dl.root / "curated/codes_droit"
        if curated_base.exists():
            for slug_dir in sorted(curated_base.iterdir()):
                if not slug_dir.is_dir() or slug_dir.name.startswith("_"):
                    continue
                for part_dir in sorted(slug_dir.iterdir(), reverse=True):
                    if part_dir.is_dir() and list(part_dir.glob("*_embeddings.npy")):
                        embedding_date = part_dir.name
                        break
                if embedding_date != ingest_date:
                    break

    source_name = f"codes_droit_{embedding_date}"
    db_path = os.environ.get("PYWORKFLOW_DB", "workflow.db")
    storage = UnifiedStorage(database_path=db_path)
    storage.migrate()

    # ── Idempotence : vérifier si déjà indexé ────────────────────────
    existing = storage.knowledge_sources.filter(name=source_name)
    if existing:
        source = existing[0]
        if source.index_status == IndexStatus.INDEXED and not force_reindex:
            _logger.info(
                "KnowledgeSource '%s' déjà indexée (id=%s) — skip (force_reindex=%s)",
                source_name,
                source.id,
                force_reindex,
            )
            return {
                "source_id": source.id,
                "source_name": source_name,
                "embedding_date": embedding_date,
                "skipped": True,
            }
        _logger.info(
            "KnowledgeSource '%s' trouvée (statut=%s) — réindexation",
            source_name,
            source.index_status,
        )
        source.index_status = IndexStatus.INDEXING
        storage.knowledge_sources.create_or_update(source)
        return {
            "source_id": source.id,
            "source_name": source_name,
            "embedding_date": embedding_date,
            "skipped": False,
        }

    # ── Première indexation ───────────────────────────────────────────
    source = KnowledgeSource(
        name=source_name,
        description=(
            f"Codes juridiques français (codes.droit.org) — "
            f"session {embedding_date}. "
            f"Articles VIGUEUR vectorisés via OpenAI text-embedding-3-large."
        ),
        source_type=SourceType.DOCUMENT,
        index_status=IndexStatus.INDEXING,
        metadata={"date": embedding_date, "origin": "codes.droit.org"},
    )
    storage.knowledge_sources.create_or_update(source)

    _logger.info("KnowledgeSource créée : %s (id=%s)", source_name, source.id)
    return {
        "source_id": source.id,
        "source_name": source_name,
        "embedding_date": embedding_date,
        "skipped": False,
    }


@step(name="index_articles", dependencies=["create_knowledge_source"])
def index_articles(
    source_id: str = "",
    source_name: str = "",
    embedding_date: str = "latest",
    skipped: bool = False,
) -> dict[str, Any]:
    """Crée un Document + un Chunk (avec embedding) par article juridique.

    Si ``skipped=True`` (injecté depuis ``create_knowledge_source`` quand la
    source est déjà INDEXED), retourne immédiatement sans rien écrire.

    Relation (ADR-025 D5 — 1 chunk par article) :
        KnowledgeSource → Document (1 par article) → Chunk (embedding float32)

    Args:
        source_id:      Injecté depuis ``create_knowledge_source``.
        source_name:    Injecté depuis ``create_knowledge_source``.
        embedding_date: Injecté depuis ``create_knowledge_source``.
        skipped:        Injecté depuis ``create_knowledge_source`` — skip si True.

    Returns:
        ``{"documents_count": N, "chunks_count": N, "source_id": str, "skipped": bool}``
    """
    if skipped:
        _logger.info("index_articles — skip (source '%s' déjà INDEXED)", source_name)
        return {
            "documents_count": 0,
            "chunks_count": 0,
            "source_id": source_id,
            "source_name": source_name,
            "skipped": True,
        }

    import os  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    from pyworkflow_engine.adapters.storage.unified import (
        UnifiedStorage,
    )  # noqa: PLC0415
    from pyworkflow_engine.models.ai.knowledge import Chunk, Document  # noqa: PLC0415
    from pyworkflow_engine.models.ai.types import IndexStatus  # noqa: PLC0415

    from jobs.shared.datalake import DataLake  # noqa: PLC0415

    dl = DataLake.from_env()
    db_path = os.environ.get("PYWORKFLOW_DB", "workflow.db")
    storage = UnifiedStorage(database_path=db_path)

    curated_base = dl.root / "curated/codes_droit"
    docs_count = 0
    chunks_count = 0

    with storage.transaction():
        for slug_dir in sorted(curated_base.iterdir()):
            if not slug_dir.is_dir() or slug_dir.name.startswith("_"):
                continue
            slug = slug_dir.name

            # Résoudre la date
            date_dir = slug_dir / embedding_date
            if not date_dir.exists():
                partitions = sorted(d.name for d in slug_dir.iterdir() if d.is_dir())
                if not partitions:
                    continue
                date_dir = slug_dir / partitions[-1]

            npy_path = date_dir / f"{slug}_embeddings.npy"
            meta_path = date_dir / f"{slug}_embeddings_metadata.json"
            articles_file = date_dir / f"{slug}_articles.json"

            if not npy_path.exists() or not meta_path.exists():
                _logger.warning(
                    "[%s] Embeddings introuvables dans %s — skip", slug, date_dir
                )
                continue

            matrix = np.load(str(npy_path))
            meta_list: list[dict[str, Any]] = json.loads(
                meta_path.read_text(encoding="utf-8")
            )

            # Charger le contenu complet des articles
            content_index: dict[str, str] = {}
            if articles_file.exists():
                payload = json.loads(articles_file.read_text(encoding="utf-8"))
                articles = (
                    payload.get("articles", payload)
                    if isinstance(payload, dict)
                    else payload
                )
                for a in articles:
                    content_index[a.get("legiarti_id", "")] = a.get("content", "")

            if len(matrix) != len(meta_list):
                _logger.warning(
                    "[%s] Incohérence matrice/métadonnées : %d vs %d — skip",
                    slug,
                    len(matrix),
                    len(meta_list),
                )
                continue

            _logger.info("[%s] Indexation de %d articles", slug, len(meta_list))

            for i, meta in enumerate(meta_list):
                legiarti_id = meta.get("legiarti_id", "")
                number = meta.get("number", "")
                title = meta.get("title", f"Article {number}")
                content = content_index.get(legiarti_id, "")

                doc = Document(
                    source_id=source_id,
                    title=title,
                    content=content,
                    metadata={"slug": slug, "legiarti_id": legiarti_id},
                    chunk_count=1,
                )
                storage.documents.create_or_update(doc)
                docs_count += 1

                chunk = Chunk(
                    document_id=doc.id,
                    content=content,
                    embedding=matrix[i].tolist(),
                    chunk_index=0,
                    metadata={
                        "slug": slug,
                        "legiarti_id": legiarti_id,
                        "number": number,
                    },
                )
                storage.chunks.create_or_update(chunk)
                chunks_count += 1

            _logger.info("[%s] ✅ %d documents + chunks", slug, len(meta_list))

        # Mise à jour du statut KnowledgeSource → INDEXED
        source = storage.knowledge_sources.get(source_id)
        if source:
            source.index_status = IndexStatus.INDEXED
            source.chunks_count = chunks_count
            storage.knowledge_sources.create_or_update(source)

    _logger.success(  # type: ignore[attr-defined]
        "✅ index_articles — %d documents + %d chunks indexés (source=%s)",
        docs_count,
        chunks_count,
        source_name,
    )
    return {
        "documents_count": docs_count,
        "chunks_count": chunks_count,
        "source_id": source_id,
        "source_name": source_name,
        "skipped": False,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="index-codes-droit",
    version="1.1.0",
    description=(
        "Indexation RAG codes.droit.org → KnowledgeSource / Document / Chunk (SQLite). "
        "Idempotent : skip si codes_droit_{date} déjà INDEXED. "
        "Pipeline : création KnowledgeSource → insertion documents+chunks → statut INDEXED."
    ),
    steps=[create_knowledge_source, index_articles],
)
def index_codes_droit() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    create_knowledge_source()
    index_articles()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse  # noqa: PLC0415

    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.storage import SQLiteStorage  # noqa: PLC0415

    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Indexation RAG articles juridiques → SQLite (Job 4)"
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date des embeddings à indexer (défaut : dernière date disponible).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force la réindexation même si la source est déjà INDEXED.",
    )
    args = parser.parse_args()

    configure_platform_logging()
    ingest_date = args.date or "latest"

    engine = WorkflowEngine(
        storage=SQLiteStorage(database_path="workflow.db"),
    )
    result = engine.run_with_storage(
        index_codes_droit.build(),
        initial_context={"ingest_date": ingest_date, "force_reindex": args.force},
    )

    for step_run in result.step_runs:
        ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
        print(
            f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
        )  # noqa: T201

    print(f"\nStatut final : {result.status}")  # noqa: T201
