"""
adapters/storage/checkpoint_sqlite — Backend SQLite pour les checkpoints pipeline.

Implémentation de ``BaseCheckpointStore`` sur SQLite via stdlib ``sqlite3``.
Thread-safe (connexion thread-locale, WAL mode).

Stocke les snapshots de contexte dans la table ``pipeline_checkpoints``
de la base de données workflow (partagée avec les autres tables).

Architecture : ADR-021 (Phase 2)
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pyworkflow_engine.ports.checkpoint import (
    BaseCheckpointStore,
    CheckpointNotFoundError,
    CheckpointRecord,
)

# ── DDL ──────────────────────────────────────────────────────────────────────

_CHECKPOINT_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    stage_name TEXT DEFAULT '',
    context TEXT NOT NULL,    -- JSON snapshot of pipeline context
    metadata TEXT,            -- JSON
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_checkpoints_run_id
    ON pipeline_checkpoints(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_checkpoints_stage
    ON pipeline_checkpoints(pipeline_run_id, stage_index);
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── SQLiteCheckpointStore ────────────────────────────────────────────────────


class SQLiteCheckpointStore(BaseCheckpointStore):
    """Backend SQLite pour la persistence des checkpoints pipeline.

    Thread-safe : connexion thread-locale (même pattern que SQLiteStorage).

    Args:
        database_path: Chemin vers le fichier SQLite (partagé avec workflow.db).
            Peut être ``:memory:`` pour les tests.

    Usage::

        store = SQLiteCheckpointStore("workflow.db")
        cid = store.save("run-uuid", stage_index=2, context={"key": "val"})
        record = store.load(cid)
        latest = store.get_latest("run-uuid")
    """

    def __init__(self, database_path: str | Path = "workflow.db") -> None:
        self._db_path = str(Path(database_path).expanduser().resolve())
        self._local = threading.local()
        self._lock = threading.RLock()
        self._init_schema()

    # ── Connexion ────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.executescript(_CHECKPOINT_SCHEMA)
            conn.commit()

    def close(self) -> None:
        if hasattr(self._local, "conn"):
            try:
                self._local.conn.close()
            except Exception:  # noqa: BLE001
                pass
            del self._local.conn

    # ── BaseCheckpointStore interface ────────────────────────────────

    def save(
        self,
        pipeline_run_id: str,
        stage_index: int,
        context: dict[str, Any],
        *,
        stage_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Sauvegarde un snapshot du contexte et retourne le checkpoint_id."""
        checkpoint_id = str(uuid4())
        now = _now_iso()
        context_json = json.dumps(context, default=str)
        metadata_json = json.dumps(metadata) if metadata else None

        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO pipeline_checkpoints
                    (checkpoint_id, pipeline_run_id, stage_index, stage_name,
                     context, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    pipeline_run_id,
                    stage_index,
                    stage_name,
                    context_json,
                    metadata_json,
                    now,
                ),
            )
            conn.commit()

        return checkpoint_id

    def load(self, checkpoint_id: str) -> CheckpointRecord:
        """Charge un checkpoint par son ID.

        Raises:
            CheckpointNotFoundError: Si le checkpoint n'existe pas.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM pipeline_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()

        if not row:
            raise CheckpointNotFoundError(checkpoint_id)

        return self._row_to_record(row)

    def list_for_run(self, pipeline_run_id: str) -> list[CheckpointRecord]:
        """Liste les checkpoints d'un run, triés par stage_index ASC."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM pipeline_checkpoints WHERE pipeline_run_id = ? "
            "ORDER BY stage_index ASC",
            (pipeline_run_id,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_latest(self, pipeline_run_id: str) -> CheckpointRecord | None:
        """Retourne le checkpoint au stage_index le plus élevé pour un run."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM pipeline_checkpoints WHERE pipeline_run_id = ? "
            "ORDER BY stage_index DESC LIMIT 1",
            (pipeline_run_id,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def delete(self, checkpoint_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM pipeline_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            )
            conn.commit()
        return cursor.rowcount > 0

    def delete_for_run(self, pipeline_run_id: str) -> int:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM pipeline_checkpoints WHERE pipeline_run_id = ?",
                (pipeline_run_id,),
            )
            conn.commit()
        return cursor.rowcount

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> CheckpointRecord:
        context = json.loads(row["context"])
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        return CheckpointRecord(
            checkpoint_id=row["checkpoint_id"],
            pipeline_run_id=row["pipeline_run_id"],
            stage_index=row["stage_index"],
            stage_name=row["stage_name"] or "",
            context=context,
            created_at=row["created_at"] or "",
            metadata=metadata,
        )
