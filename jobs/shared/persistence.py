"""
jobs/shared/persistence.py — Persistance du catalogue de jobs dans workflow.db.

Synchronise les définitions de jobs (depuis ``jobs/manifest.yaml``)
dans la table ``jobs`` de SQLite, en utilisant le même pattern que
``agents/shared/persistence.py`` → ``ai_agents``.

Méthodes principales :
  - ``sync_catalog()`` : UPSERT de tous les jobs du manifest → table ``jobs``
  - ``list_catalog()`` : Lecture du catalogue persisté
  - ``available()``    : Vérifie que la DB et la table existent

Usage interne (appelé par la CLI ``pyworkflow job sync``) ::

    from jobs.shared.persistence import JobCatalogPersistence

    pers = JobCatalogPersistence()
    stats = pers.sync_catalog()
    # → {"inserted": 3, "updated": 5, "total": 8}

Architecture : ADR-018 — Phase catalogue jobs
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# ── Résolution du chemin DB ───────────────────────────────────────────────────

_DEFAULT_DB = "workflow.db"


def _resolve_db_path() -> Path:
    """Retourne le chemin absolu du fichier SQLite.

    Priorité :
      1. Variable d'environnement ``PYWORKFLOW_DB``
      2. ``./workflow.db`` relatif au répertoire de travail courant
    """
    raw = os.environ.get("PYWORKFLOW_DB", _DEFAULT_DB)
    return Path(raw).expanduser().resolve()


# ── JobCatalogPersistence ─────────────────────────────────────────────────────


class JobCatalogPersistence:
    """Persistance du catalogue de jobs dans ``workflow.db``.

    Utilise la table ``jobs`` existante (schéma v1+) pour y stocker
    les définitions de jobs chargées depuis le manifest.

    Thread-safe : connexion locale au thread courant.

    Args:
        database_path: Chemin du fichier SQLite. ``None`` → auto-résolution
                       via ``PYWORKFLOW_DB`` ou ``./workflow.db``.
    """

    def __init__(self, database_path: str | Path | None = None) -> None:
        if database_path is None:
            self._db_path = _resolve_db_path()
        else:
            self._db_path = Path(database_path).expanduser().resolve()

        self._local = threading.local()
        self._lock = threading.RLock()

    # ── Connexion ─────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Connexion thread-locale avec WAL + foreign keys."""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._local.conn = conn
        return self._local.conn

    # ── Synchronisation catalogue → table jobs ────────────────────────────────

    def sync_catalog(
        self,
        manifest_path: str | Path | None = None,
    ) -> dict[str, int]:
        """Synchronise le catalogue de jobs Python dans ``workflow.db``.

        Lit tous les jobs via ``load_all_jobs_with_metadata()`` et effectue
        un UPSERT dans la table ``jobs``.

        Les colonnes ``created_at`` et ``updated_at`` sont gérées
        automatiquement : ``created_at`` n'est écrit que lors d'une insertion
        initiale, ``updated_at`` est toujours mis à jour.

        Args:
            manifest_path: Chemin vers le manifest (optionnel, défaut :
                ``jobs/manifest.yaml``).

        Returns:
            Dictionnaire ``{"inserted": N, "updated": N, "total": N}``.
        """
        from jobs.shared.loader import load_all_jobs_with_metadata

        enriched = load_all_jobs_with_metadata(manifest_path)
        now = datetime.now(UTC).isoformat()
        stats = {"inserted": 0, "updated": 0, "total": len(enriched)}

        with self._lock:
            conn = self._get_conn()
            for item in enriched:
                row_data = self._prepare_row(item, now)
                self._upsert_job(conn, row_data, stats)
            conn.commit()

        return stats

    # ── Helpers internes ──────────────────────────────────────────────────────

    @staticmethod
    def _prepare_row(item: dict[str, Any], now: str) -> dict[str, Any]:
        """Prépare les colonnes SQL à partir d'un item manifest enrichi."""
        job = item["job"]
        schedule = item.get("schedule")
        owner = item.get("owner")
        manifest_tags = item.get("tags", [])
        depends_on = item.get("depends_on", [])
        manifest_desc = item.get("description", "")

        steps_json = json.dumps([s.to_dict() for s in job.steps] if job.steps else [])
        all_tags = list(set(list(job.tags) + manifest_tags))
        tags_json = json.dumps(all_tags) if all_tags else None

        meta: dict[str, Any] = dict(job.metadata) if job.metadata else {}
        if schedule:
            meta["schedule"] = schedule
        if owner:
            meta["owner"] = owner
        if depends_on:
            meta["depends_on"] = depends_on
        meta_json = json.dumps(meta) if meta else None

        return {
            "name": job.name,
            "description": job.description or manifest_desc,
            "steps": steps_json,
            "tags": tags_json,
            "metadata": meta_json,
            "version": job.version,
            "enabled": 1 if job.enabled else 0,
            "now": now,
        }

    @staticmethod
    def _upsert_job(
        conn: sqlite3.Connection,
        row: dict[str, Any],
        stats: dict[str, int],
    ) -> None:
        """INSERT ou UPDATE d'un job dans la table ``jobs``."""
        existing = conn.execute(
            "SELECT name FROM jobs WHERE name = ?", (row["name"],)
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO jobs
                    (name, description, steps, tags, metadata,
                     version, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["name"],
                    row["description"],
                    row["steps"],
                    row["tags"],
                    row["metadata"],
                    row["version"],
                    row["enabled"],
                    row["now"],
                    row["now"],
                ),
            )
            stats["inserted"] += 1
        else:
            conn.execute(
                """
                UPDATE jobs SET
                    description = ?,
                    steps       = ?,
                    tags        = ?,
                    metadata    = ?,
                    version     = ?,
                    enabled     = ?,
                    updated_at  = ?
                WHERE name = ?
                """,
                (
                    row["description"],
                    row["steps"],
                    row["tags"],
                    row["metadata"],
                    row["version"],
                    row["enabled"],
                    row["now"],
                    row["name"],
                ),
            )
            stats["updated"] += 1

    # ── Lecture du catalogue ───────────────────────────────────────────────────

    def list_catalog(self) -> list[dict[str, Any]]:
        """Retourne tous les jobs persistés dans la table ``jobs``.

        Returns:
            Liste de dicts ordonnés par nom.
        """
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM jobs ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def get_job(self, job_name: str) -> dict[str, Any] | None:
        """Retourne un job par son nom.

        Args:
            job_name: Nom du job.

        Returns:
            Dict ou ``None`` si introuvable.
        """
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM jobs WHERE name = ?", (job_name,)).fetchone()
        return dict(row) if row else None

    def get_job_stats(self) -> dict[str, Any]:
        """Retourne des statistiques sur le catalogue persisté.

        Returns:
            Dict avec ``total``, ``enabled``, ``disabled``.
        """
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        enabled = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE enabled = 1"
        ).fetchone()[0]
        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
        }

    # ── Disponibilité ─────────────────────────────────────────────────────────

    def available(self) -> bool:
        """Retourne ``True`` si le fichier DB existe et contient la table ``jobs``."""
        if not self._db_path.exists():
            return False
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
            ).fetchone()
            return row is not None
        except sqlite3.Error:
            return False

    def __repr__(self) -> str:
        return f"JobCatalogPersistence(db={self._db_path})"
