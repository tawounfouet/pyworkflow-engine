"""
Adapter persistence — backend SQLite via stdlib (SQLiteStorage).

Stockage fiable avec transactions ACID.  Utilise uniquement le module
``sqlite3`` de la stdlib — zéro dépendance externe.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from pyworkflow_engine.models import Job, JobRun, StepRun
from pyworkflow_engine.models.pipeline.pipeline_run import PipelineRun, StageRun
from pyworkflow_engine.ports.storage import (
    BaseStorage,
    JobNotFoundError,
    StorageError,
    TransactionError,
)

# Database schema version
SCHEMA_VERSION = 5

# SQL Schema definitions
SCHEMA_SQL = """
-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    name TEXT PRIMARY KEY,
    description TEXT,
    steps TEXT NOT NULL,  -- JSON array of steps
    tags TEXT,            -- JSON array
    metadata TEXT,        -- JSON
    version TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Job runs table (v2: added job_version, updated_at, output_data, context, error, duration_ms, triggered_by, priority)
CREATE TABLE IF NOT EXISTS job_runs (
    job_run_id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    job_version TEXT DEFAULT '1.0.0',
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms INTEGER,
    triggered_by TEXT DEFAULT 'manual',
    priority INTEGER DEFAULT 5,
    input_data TEXT,   -- JSON
    output_data TEXT,  -- JSON
    context TEXT,      -- JSON
    error TEXT,
    metadata TEXT,     -- JSON
    FOREIGN KEY (job_name) REFERENCES jobs(name) ON DELETE CASCADE
);

-- Step runs table (v2: added executor_type, duration_ms, retry_count)
CREATE TABLE IF NOT EXISTS step_runs (
    step_run_id TEXT PRIMARY KEY,
    job_run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL,
    executor_type TEXT DEFAULT 'local',
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms INTEGER,
    retry_count INTEGER DEFAULT 0,
    input_data TEXT,   -- JSON
    output_data TEXT,  -- JSON
    error TEXT,
    metadata TEXT,     -- JSON
    FOREIGN KEY (job_run_id) REFERENCES job_runs(job_run_id) ON DELETE CASCADE
);

-- Pipeline runs table (v3)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    pipeline_run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    pipeline_version TEXT DEFAULT '1.0.0',
    status TEXT NOT NULL,
    triggered_by TEXT DEFAULT 'manual',
    context TEXT,      -- JSON
    error TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms INTEGER,
    trigger_data TEXT, -- JSON
    metadata TEXT,     -- JSON
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Stage runs table (v3)
CREATE TABLE IF NOT EXISTS stage_runs (
    stage_run_id TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL,
    job_name TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    status TEXT NOT NULL,
    skipped INTEGER DEFAULT 0,
    skip_reason TEXT,
    error TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms INTEGER,
    metadata TEXT,     -- JSON
    job_run_id TEXT,   -- FK → job_runs (nullable, added v5)
    FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs(pipeline_run_id) ON DELETE CASCADE
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_job_runs_job_name ON job_runs(job_name);
CREATE INDEX IF NOT EXISTS idx_job_runs_status ON job_runs(status);
CREATE INDEX IF NOT EXISTS idx_job_runs_created_at ON job_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_step_runs_job_run_id ON step_runs(job_run_id);
CREATE INDEX IF NOT EXISTS idx_step_runs_status ON step_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline_name ON pipeline_runs(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created_at ON pipeline_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_stage_runs_pipeline_run_id ON stage_runs(pipeline_run_id);

-- Triggers to update timestamps
CREATE TRIGGER IF NOT EXISTS update_jobs_timestamp
    AFTER UPDATE ON jobs
    FOR EACH ROW
BEGIN
    UPDATE jobs SET updated_at = CURRENT_TIMESTAMP WHERE name = NEW.name;
END;
"""

# Migration: v2 → v3 (add pipeline_runs + stage_runs to existing DBs)
MIGRATION_V2_TO_V3 = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    pipeline_run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    pipeline_version TEXT DEFAULT '1.0.0',
    status TEXT NOT NULL,
    triggered_by TEXT DEFAULT 'manual',
    context TEXT,
    error TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms INTEGER,
    trigger_data TEXT,
    metadata TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS stage_runs (
    stage_run_id TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL,
    job_name TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    status TEXT NOT NULL,
    skipped INTEGER DEFAULT 0,
    skip_reason TEXT,
    error TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms INTEGER,
    metadata TEXT,
    job_run_id TEXT,
    FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs(pipeline_run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline_name ON pipeline_runs(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created_at ON pipeline_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_stage_runs_pipeline_run_id ON stage_runs(pipeline_run_id);
"""

# Migration: v3 → v4 (ensure all indexes and triggers exist on upgraded DBs)
# All statements use IF NOT EXISTS — safe to re-run on any v3 database.
MIGRATION_V3_TO_V4 = """
CREATE INDEX IF NOT EXISTS idx_job_runs_job_name ON job_runs(job_name);
CREATE INDEX IF NOT EXISTS idx_job_runs_status ON job_runs(status);
CREATE INDEX IF NOT EXISTS idx_job_runs_created_at ON job_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_step_runs_job_run_id ON step_runs(job_run_id);
CREATE INDEX IF NOT EXISTS idx_step_runs_status ON step_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline_name ON pipeline_runs(pipeline_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created_at ON pipeline_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_stage_runs_pipeline_run_id ON stage_runs(pipeline_run_id);
"""

# Migration: v4 → v5 (add job_run_id to stage_runs / pl_stage_runs for step drill-down in GUI)
# ALTER TABLE … ADD COLUMN is safe — the column is nullable and defaults to NULL.
MIGRATION_V4_TO_V5_STEPS = [
    "ALTER TABLE stage_runs    ADD COLUMN job_run_id TEXT",
    "ALTER TABLE pl_stage_runs ADD COLUMN job_run_id TEXT",
]


class SQLiteStorage(BaseStorage):
    """SQLite-based persistence backend.

    This implementation provides reliable, ACID-compliant storage using
    SQLite database. It supports concurrent access through SQLite's WAL
    mode and provides efficient querying with proper indexing.

    Features:
        - ACID transactions
        - Concurrent read access (WAL mode)
        - Automatic schema migrations
        - Efficient indexing
        - Foreign key constraints
        - Automatic timestamp management
    """

    def __init__(self, database_path: str = "./workflow.db", **sqlite_options):
        """Initialize SQLite persistence.

        Args:
            database_path: Path to the SQLite database file.
            **sqlite_options: Additional SQLite connection options.
        """
        self.database_path = Path(database_path)
        self.sqlite_options = sqlite_options

        # Thread safety - SQLite is thread-safe but we use connection per thread
        self._local = threading.local()
        self._lock = threading.RLock()

        # Registry of all thread-local connections (for close())
        self._all_connections: list[sqlite3.Connection] = []

        # Initialize database
        self._initialize_database()

    def close(self) -> None:
        """Ferme la connexion thread-local courante et la libère.

        À appeler en fin de vie du thread (worker ASGI, thread de test…).
        Sans cet appel les connexions thread-local restent ouvertes jusqu'à
        la fin du processus.
        """
        if hasattr(self._local, "connection"):
            try:
                self._local.connection.close()
            except Exception:  # noqa: BLE001
                pass
            del self._local.connection

    def close_all(self) -> None:
        """Ferme toutes les connexions ouvertes (à appeler au shutdown du processus)."""
        with self._lock:
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
            self._all_connections.clear()

    def __enter__(self) -> "SQLiteStorage":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection"):
            conn = sqlite3.connect(
                self.database_path, check_same_thread=False, **self.sqlite_options
            )

            # Configure connection
            conn.row_factory = sqlite3.Row  # Enable dict-like access
            conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign keys
            conn.execute(
                "PRAGMA journal_mode = WAL"
            )  # Enable WAL mode for better concurrency
            conn.execute("PRAGMA synchronous = NORMAL")  # Balanced performance/safety
            conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
            conn.execute("PRAGMA temp_store = MEMORY")  # Use memory for temp tables

            self._local.connection = conn
            # Track so close_all() can reach every thread's connection
            with self._lock:
                self._all_connections.append(conn)

        return self._local.connection

    def _initialize_database(self) -> None:
        """Initialize the database schema."""
        with self._lock:
            conn = self._get_connection()

            try:
                # Check current schema version
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
                )
                has_version_table = cursor.fetchone() is not None

                if has_version_table:
                    cursor = conn.execute("SELECT MAX(version) FROM schema_version")
                    current_version = cursor.fetchone()[0] or 0
                else:
                    current_version = 0

                # Apply schema if needed
                if current_version < SCHEMA_VERSION:
                    if current_version == 0:
                        # Fresh install — apply full schema
                        conn.executescript(SCHEMA_SQL)
                    else:
                        # Incremental migrations — each step is idempotent
                        # (all DDL statements use IF NOT EXISTS).
                        # Add a new `if current_version < N` block for each
                        # future schema version bump.
                        if current_version < 3:
                            conn.executescript(MIGRATION_V2_TO_V3)
                        if current_version < 4:
                            conn.executescript(MIGRATION_V3_TO_V4)
                        if current_version < 5:
                            # ADD COLUMN is not idempotent — guard with a
                            # column-existence check before executing.
                            existing = {
                                row[1]
                                for row in conn.execute(
                                    "PRAGMA table_info(stage_runs)"
                                ).fetchall()
                            }
                            for stmt in MIGRATION_V4_TO_V5_STEPS:
                                col = stmt.split()[-1]  # last token = column name
                                if col not in existing:
                                    try:
                                        conn.execute(stmt)
                                    except sqlite3.OperationalError:
                                        pass  # column already exists in pl_* table
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                    conn.commit()

            except sqlite3.Error as e:
                raise StorageError(f"Failed to initialize database: {e}") from e

    def _serialize_job(self, job: Job) -> dict[str, Any]:
        """Serialize a job for database storage (compact SQL row format)."""
        return {
            "name": job.name,
            "description": job.description,
            "steps": json.dumps([s.to_dict() for s in job.steps]),
            "tags": json.dumps(job.tags) if job.tags else None,
            "metadata": json.dumps(job.metadata) if job.metadata else None,
            "version": job.version,
            "enabled": 1 if job.enabled else 0,
        }

    def _deserialize_job(self, row: sqlite3.Row) -> Job:
        """Deserialize a job from a database row."""
        from pyworkflow_engine.models import Job, Step

        steps = [Step.from_dict(s) for s in json.loads(row["steps"])]

        return Job(
            name=row["name"],
            description=row["description"] or "",
            steps=steps,
            tags=json.loads(row["tags"]) if row["tags"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            version=row["version"] or "1.0.0",
            enabled=bool(row["enabled"]) if row["enabled"] is not None else True,
        )

    def _serialize_job_run(self, job_run: JobRun) -> dict[str, Any]:
        """Serialize a job run for database storage (compact SQL row format)."""
        return {
            "job_run_id": job_run.job_run_id,
            "job_name": job_run.job_name,
            "job_version": job_run.job_version,
            "status": job_run.status.value,
            "created_at": job_run.created_at.isoformat(),
            "updated_at": job_run.updated_at.isoformat(),
            "start_time": (
                job_run.start_time.isoformat() if job_run.start_time else None
            ),
            "end_time": job_run.end_time.isoformat() if job_run.end_time else None,
            "duration_ms": job_run.duration_ms,
            "triggered_by": job_run.triggered_by,
            "priority": job_run.priority,
            "input_data": (
                json.dumps(job_run.input_data) if job_run.input_data else None
            ),
            "output_data": (
                json.dumps(job_run.output_data) if job_run.output_data else None
            ),
            "context": json.dumps(job_run.context) if job_run.context else None,
            "error": job_run.error,
            "metadata": json.dumps(job_run.metadata) if job_run.metadata else None,
        }

    def _deserialize_job_run(
        self, row: sqlite3.Row, step_runs: list[StepRun] = None
    ) -> JobRun:
        """Deserialize a job run from a database row."""
        from pyworkflow_engine.models.enums import RunStatus

        _keys = (
            row.keys()
        )  # sqlite3.Row: use .keys() for membership tests (SIM118/SIM401)
        return JobRun(
            job_run_id=row["job_run_id"],
            job_name=row["job_name"],
            job_version=(
                row["job_version"] if "job_version" in _keys else "1.0.0"
            ),  # noqa: SIM401
            status=RunStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=(
                datetime.fromisoformat(row["updated_at"])
                if "updated_at" in _keys and row["updated_at"]
                else datetime.fromisoformat(row["created_at"])
            ),
            start_time=(
                datetime.fromisoformat(row["start_time"]) if row["start_time"] else None
            ),
            end_time=(
                datetime.fromisoformat(row["end_time"]) if row["end_time"] else None
            ),
            duration_ms=(
                row["duration_ms"] if "duration_ms" in _keys else None
            ),  # noqa: SIM401
            triggered_by=(
                row["triggered_by"] if "triggered_by" in _keys else "manual"
            ),  # noqa: SIM401
            priority=row["priority"] if "priority" in _keys else 5,  # noqa: SIM401
            input_data=json.loads(row["input_data"]) if row["input_data"] else {},
            output_data=(
                json.loads(row["output_data"])
                if "output_data" in _keys and row["output_data"]
                else {}
            ),
            context=(
                json.loads(row["context"])
                if "context" in _keys and row["context"]
                else {}
            ),
            error=row["error"] if "error" in _keys else None,  # noqa: SIM401
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            step_runs=step_runs or [],
        )

    def _serialize_step_run(self, step_run: StepRun) -> dict[str, Any]:
        """Serialize a step run for database storage (compact SQL row format)."""
        return {
            "step_run_id": step_run.step_run_id,
            "job_run_id": step_run.job_run_id,
            "step_name": step_run.step_name,
            "status": step_run.status.value,
            "executor_type": step_run.executor_type.value,
            "start_time": (
                step_run.start_time.isoformat() if step_run.start_time else None
            ),
            "end_time": step_run.end_time.isoformat() if step_run.end_time else None,
            "duration_ms": step_run.duration_ms,
            "retry_count": step_run.retry_count,
            "input_data": (
                json.dumps(step_run.input_data) if step_run.input_data else None
            ),
            "output_data": (
                json.dumps(step_run.output_data) if step_run.output_data else None
            ),
            "error": step_run.error,
            "metadata": json.dumps(step_run.metadata) if step_run.metadata else None,
        }

    def _deserialize_step_run(self, row: sqlite3.Row) -> StepRun:
        """Deserialize a step run from a database row."""
        from pyworkflow_engine.models.enums import ExecutorType, RunStatus

        _keys = (
            row.keys()
        )  # sqlite3.Row: use .keys() for membership tests (SIM118/SIM401)
        return StepRun(
            step_run_id=row["step_run_id"],
            job_run_id=row["job_run_id"],
            step_name=row["step_name"],
            status=RunStatus(row["status"]),
            executor_type=(
                ExecutorType(row["executor_type"])
                if "executor_type" in _keys and row["executor_type"]
                else ExecutorType.LOCAL
            ),
            start_time=(
                datetime.fromisoformat(row["start_time"]) if row["start_time"] else None
            ),
            end_time=(
                datetime.fromisoformat(row["end_time"]) if row["end_time"] else None
            ),
            duration_ms=(
                row["duration_ms"] if "duration_ms" in _keys else None
            ),  # noqa: SIM401
            retry_count=(
                row["retry_count"] if "retry_count" in _keys else 0
            ),  # noqa: SIM401
            input_data=json.loads(row["input_data"]) if row["input_data"] else {},
            output_data=json.loads(row["output_data"]) if row["output_data"] else {},
            error=row["error"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _load_step_runs(self, job_run_id: str) -> list[StepRun]:
        """Load all step runs for a job run."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM step_runs WHERE job_run_id = ? ORDER BY step_name",
                (job_run_id,),
            )
            return [self._deserialize_step_run(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to load step runs: {e}") from e

    # Transaction support

    def begin_transaction(self) -> None:
        """Begin a database transaction."""
        conn = self._get_connection()
        try:
            conn.execute("BEGIN")
        except sqlite3.Error as e:
            raise TransactionError(f"Failed to begin transaction: {e}") from e

    def commit_transaction(self) -> None:
        """Commit the current transaction."""
        conn = self._get_connection()
        try:
            conn.commit()
        except sqlite3.Error as e:
            raise TransactionError(f"Failed to commit transaction: {e}") from e

    def rollback_transaction(self) -> None:
        """Roll back the current transaction."""
        conn = self._get_connection()
        try:
            conn.rollback()
        except sqlite3.Error as e:
            raise TransactionError(f"Failed to rollback transaction: {e}") from e

    # Job operations

    def save_job(self, job: Job) -> None:
        """Save a job definition."""
        conn = self._get_connection()
        data = self._serialize_job(job)

        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs
                    (name, description, steps, tags, metadata, version, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["name"],
                    data["description"],
                    data["steps"],
                    data["tags"],
                    data["metadata"],
                    data["version"],
                    data["enabled"],
                ),
            )
            conn.commit()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save job '{job.name}': {e}") from e

    def get_job(self, job_name: str) -> Job | None:
        """Retrieve a job definition by name."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM jobs WHERE name = ?", (job_name,))
            row = cursor.fetchone()
            return self._deserialize_job(row) if row else None
        except sqlite3.Error as e:
            raise StorageError(f"Failed to get job '{job_name}': {e}") from e

    def list_jobs(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        """List all job definitions."""
        conn = self._get_connection()
        try:
            sql = "SELECT * FROM jobs ORDER BY name"
            params = []

            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])

            cursor = conn.execute(sql, params)
            return [self._deserialize_job(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to list jobs: {e}") from e

    def delete_job(self, job_name: str) -> bool:
        """Delete a job definition."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM jobs WHERE name = ?", (job_name,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            raise StorageError(f"Failed to delete job '{job_name}': {e}") from e

    # Job run operations

    def save_job_run(self, job_run: JobRun) -> None:
        """Save a job run and its step runs."""
        conn = self._get_connection()

        try:
            # Save job run
            run_data = self._serialize_job_run(job_run)
            conn.execute(
                """
                INSERT OR REPLACE INTO job_runs
                    (job_run_id, job_name, job_version, status,
                     created_at, updated_at, start_time, end_time,
                     duration_ms, triggered_by, priority,
                     input_data, output_data, context, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_data["job_run_id"],
                    run_data["job_name"],
                    run_data["job_version"],
                    run_data["status"],
                    run_data["created_at"],
                    run_data["updated_at"],
                    run_data["start_time"],
                    run_data["end_time"],
                    run_data["duration_ms"],
                    run_data["triggered_by"],
                    run_data["priority"],
                    run_data["input_data"],
                    run_data["output_data"],
                    run_data["context"],
                    run_data["error"],
                    run_data["metadata"],
                ),
            )

            # Delete existing step runs, then insert fresh
            conn.execute(
                "DELETE FROM step_runs WHERE job_run_id = ?", (job_run.job_run_id,)
            )

            for step_run in job_run.step_runs:
                step_data = self._serialize_step_run(step_run)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO step_runs
                        (step_run_id, job_run_id, step_name, status,
                         executor_type, start_time, end_time, duration_ms,
                         retry_count, input_data, output_data, error, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        step_data["step_run_id"],
                        step_data["job_run_id"],
                        step_data["step_name"],
                        step_data["status"],
                        step_data["executor_type"],
                        step_data["start_time"],
                        step_data["end_time"],
                        step_data["duration_ms"],
                        step_data["retry_count"],
                        step_data["input_data"],
                        step_data["output_data"],
                        step_data["error"],
                        step_data["metadata"],
                    ),
                )

            conn.commit()

        except sqlite3.Error as e:
            raise StorageError(
                f"Failed to save job run '{job_run.job_run_id}': {e}"
            ) from e

    def update_job_run(self, job_run: JobRun) -> None:
        """Update an existing job run."""
        conn = self._get_connection()

        try:
            # Check if job run exists
            cursor = conn.execute(
                "SELECT job_run_id FROM job_runs WHERE job_run_id = ?",
                (job_run.job_run_id,),
            )
            if not cursor.fetchone():
                raise JobNotFoundError(f"Job run {job_run.job_run_id} not found")

            run_data = self._serialize_job_run(job_run)
            conn.execute(
                """
                UPDATE job_runs
                SET job_name=?, job_version=?, status=?,
                    updated_at=?, start_time=?, end_time=?,
                    duration_ms=?, triggered_by=?, priority=?,
                    input_data=?, output_data=?, context=?,
                    error=?, metadata=?
                WHERE job_run_id=?
                """,
                (
                    run_data["job_name"],
                    run_data["job_version"],
                    run_data["status"],
                    run_data["updated_at"],
                    run_data["start_time"],
                    run_data["end_time"],
                    run_data["duration_ms"],
                    run_data["triggered_by"],
                    run_data["priority"],
                    run_data["input_data"],
                    run_data["output_data"],
                    run_data["context"],
                    run_data["error"],
                    run_data["metadata"],
                    run_data["job_run_id"],
                ),
            )

            # Replace step runs
            conn.execute(
                "DELETE FROM step_runs WHERE job_run_id = ?", (job_run.job_run_id,)
            )

            for step_run in job_run.step_runs:
                step_data = self._serialize_step_run(step_run)
                conn.execute(
                    """
                    INSERT INTO step_runs
                        (step_run_id, job_run_id, step_name, status,
                         executor_type, start_time, end_time, duration_ms,
                         retry_count, input_data, output_data, error, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        step_data["step_run_id"],
                        step_data["job_run_id"],
                        step_data["step_name"],
                        step_data["status"],
                        step_data["executor_type"],
                        step_data["start_time"],
                        step_data["end_time"],
                        step_data["duration_ms"],
                        step_data["retry_count"],
                        step_data["input_data"],
                        step_data["output_data"],
                        step_data["error"],
                        step_data["metadata"],
                    ),
                )

            conn.commit()

        except sqlite3.Error as e:
            raise StorageError(
                f"Failed to update job run '{job_run.job_run_id}': {e}"
            ) from e

    def get_job_run(self, run_id: str) -> JobRun | None:
        """Retrieve a job run by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM job_runs WHERE job_run_id = ?", (run_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            step_runs = self._load_step_runs(run_id)
            return self._deserialize_job_run(row, step_runs)

        except sqlite3.Error as e:
            raise StorageError(f"Failed to get job run '{run_id}': {e}") from e

    def list_job_runs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[JobRun]:
        """List job runs with optional filtering.

        Applique ``DEFAULT_PAGE_SIZE`` (500) si ``limit`` n'est pas fourni,
        afin d'éviter des lectures OOM sur des bases volumineuses.
        Passer ``limit=None`` explicitement n'a **pas** d'effet ici — utiliser
        un grand entier ou paginer via ``offset`` si vous avez besoin de plus
        de 500 résultats.
        """
        # Appliquer la limite par défaut si l'appelant ne précise rien.
        effective_limit = limit if limit is not None else self.DEFAULT_PAGE_SIZE

        conn = self._get_connection()
        try:
            sql = "SELECT * FROM job_runs WHERE 1=1"
            params: list = []

            if job_name:
                sql += " AND job_name = ?"
                params.append(job_name)

            if status:
                sql += " AND status = ?"
                params.append(status)

            if since:
                sql += " AND created_at >= ?"
                params.append(since.isoformat())

            sql += " ORDER BY created_at DESC"
            sql += " LIMIT ? OFFSET ?"
            params.extend([effective_limit, offset])

            cursor = conn.execute(sql, params)
            runs = []

            for row in cursor.fetchall():
                step_runs = self._load_step_runs(row["job_run_id"])
                runs.append(self._deserialize_job_run(row, step_runs))

            return runs

        except sqlite3.Error as e:
            raise StorageError(f"Failed to list job runs: {e}") from e

    def delete_job_run(self, run_id: str) -> bool:
        """Delete a job run and its step runs."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM job_runs WHERE job_run_id = ?", (run_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            raise StorageError(f"Failed to delete job run '{run_id}': {e}") from e

    def get_job_run_count(self, job_name: str | None = None) -> int:
        """Get the total number of job runs."""
        conn = self._get_connection()
        try:
            if job_name:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM job_runs WHERE job_name = ?", (job_name,)
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM job_runs")
            return cursor.fetchone()[0]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to count job runs: {e}") from e

    def cleanup_old_runs(self, older_than: datetime, dry_run: bool = False) -> int:
        """Remove job runs older than the specified datetime."""
        conn = self._get_connection()
        try:
            if dry_run:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM job_runs WHERE created_at < ?",
                    (older_than.isoformat(),),
                )
                return cursor.fetchone()[0]
            cursor = conn.execute(
                "DELETE FROM job_runs WHERE created_at < ?", (older_than.isoformat(),)
            )
            conn.commit()
            return cursor.rowcount
        except sqlite3.Error as e:
            raise StorageError(f"Failed to cleanup old runs: {e}") from e

    # ── Pipeline run persistence (schema v3 + ADR-018 pl_* tables) ───────────

    # DDL for the ADR-018 namespaced pipeline tables (created on first use
    # if the UnifiedStorage migration has not yet run on this connection).
    _PL_PIPELINE_RUNS_DDL = """
        CREATE TABLE IF NOT EXISTS pl_pipeline_runs (
            pipeline_run_id TEXT PRIMARY KEY,
            pipeline_name   TEXT NOT NULL,
            pipeline_version TEXT,
            status          TEXT NOT NULL,
            context         TEXT,
            error           TEXT,
            start_time      TIMESTAMP,
            end_time        TIMESTAMP,
            duration_ms     INTEGER,
            triggered_by    TEXT,
            trigger_data    TEXT,
            metadata        TEXT,
            created_at      TIMESTAMP NOT NULL,
            updated_at      TIMESTAMP NOT NULL
        )
    """
    _PL_STAGE_RUNS_DDL = """
        CREATE TABLE IF NOT EXISTS pl_stage_runs (
            stage_run_id    TEXT PRIMARY KEY,
            pipeline_run_id TEXT NOT NULL,
            job_name        TEXT NOT NULL,
            stage_index     INTEGER NOT NULL,
            status          TEXT NOT NULL,
            skipped         INTEGER DEFAULT 0,
            skip_reason     TEXT,
            error           TEXT,
            start_time      TIMESTAMP,
            end_time        TIMESTAMP,
            duration_ms     INTEGER,
            metadata        TEXT,
            job_run_id      TEXT,
            FOREIGN KEY (pipeline_run_id)
                REFERENCES pl_pipeline_runs(pipeline_run_id) ON DELETE CASCADE
        )
    """
    _PL_IDX_DDL = [
        "CREATE INDEX IF NOT EXISTS idx_pl_pipeline_runs_name   ON pl_pipeline_runs(pipeline_name)",
        "CREATE INDEX IF NOT EXISTS idx_pl_pipeline_runs_status ON pl_pipeline_runs(status)",
        "CREATE INDEX IF NOT EXISTS idx_pl_pipeline_runs_ts     ON pl_pipeline_runs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_pl_stage_runs_run_id    ON pl_stage_runs(pipeline_run_id)",
    ]

    def _ensure_pl_tables(self, conn: sqlite3.Connection) -> None:
        """Crée les tables ADR-018 ``pl_*`` si elles n'existent pas encore."""
        conn.execute(self._PL_PIPELINE_RUNS_DDL)
        conn.execute(self._PL_STAGE_RUNS_DDL)
        for idx_sql in self._PL_IDX_DDL:
            conn.execute(idx_sql)

    # ── Pipeline definitions (pl_pipelines) ──────────────────────────────

    def save_pipeline(self, pipeline: "Pipeline") -> None:  # type: ignore[name-defined]
        """Persiste la définition d'une Pipeline dans ``pl_pipelines`` (upsert)."""
        from pyworkflow_engine.models.pipeline.pipeline import (
            Pipeline as _Pipeline,
        )  # noqa: PLC0415

        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pl_pipelines (
                        name, description, stages, triggers, schedule,
                        priority, tags, metadata, version, enabled, owner
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pipeline.name,
                        pipeline.description,
                        json.dumps([s.model_dump() for s in pipeline.stages]),
                        json.dumps(
                            [
                                t.value if hasattr(t, "value") else str(t)
                                for t in pipeline.triggers
                            ]
                        ),
                        pipeline.schedule,
                        (
                            pipeline.priority.value
                            if hasattr(pipeline.priority, "value")
                            else str(pipeline.priority)
                        ),
                        json.dumps(pipeline.tags),
                        json.dumps(pipeline.metadata),
                        pipeline.version,
                        1 if pipeline.enabled else 0,
                        pipeline.owner,
                    ),
                )
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save pipeline '{pipeline.name}': {e}") from e

    def get_pipeline(self, name: str) -> "Pipeline | None":  # type: ignore[name-defined]
        """Récupère une Pipeline par son nom depuis ``pl_pipelines``."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM pl_pipelines WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            return self._deserialize_pipeline(row)
        except sqlite3.Error as e:
            raise StorageError(f"Failed to get pipeline '{name}': {e}") from e

    def list_pipelines(
        self,
        enabled_only: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list:
        """Liste toutes les pipelines depuis ``pl_pipelines``."""
        conn = self._get_connection()
        where = "WHERE enabled = 1" if enabled_only else ""
        limit_clause = (
            f"LIMIT {limit} OFFSET {offset}"
            if limit is not None
            else f"LIMIT -1 OFFSET {offset}"
        )
        try:
            rows = conn.execute(
                f"SELECT * FROM pl_pipelines {where} ORDER BY name {limit_clause}"
            ).fetchall()
            return [self._deserialize_pipeline(r) for r in rows]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to list pipelines: {e}") from e

    def _deserialize_pipeline(self, row: sqlite3.Row):  # type: ignore[return]
        """Reconstruit un objet ``Pipeline`` depuis une ligne SQLite."""
        from pyworkflow_engine.models.enums import (
            Priority,
            TriggerType,
        )  # noqa: PLC0415
        from pyworkflow_engine.models.pipeline.pipeline import (
            Pipeline,
            PipelineStage,
        )  # noqa: PLC0415

        stages_raw = json.loads(row["stages"] or "[]")
        stages = [PipelineStage(**s) for s in stages_raw]

        triggers_raw = json.loads(row["triggers"] or '["manual"]')
        triggers = []
        for t in triggers_raw:
            try:
                triggers.append(TriggerType(t))
            except ValueError:
                triggers.append(TriggerType.MANUAL)

        try:
            priority = Priority(row["priority"])
        except (ValueError, KeyError):
            priority = Priority.NORMAL

        return Pipeline(
            name=row["name"],
            description=row["description"] or "",
            stages=stages,
            triggers=triggers,
            schedule=row["schedule"],
            priority=priority,
            tags=json.loads(row["tags"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
            version=row["version"] or "1.0.0",
            enabled=bool(row["enabled"]),
            owner=row["owner"] or "",
        )

    def save_pipeline_run(self, pipeline_run: PipelineRun) -> None:
        """Persiste un PipelineRun et ses StageRuns (upsert).

        Écrit dans **deux** jeux de tables :
        - ``pipeline_runs`` / ``stage_runs``    — tables historiques (v3)
        - ``pl_pipeline_runs`` / ``pl_stage_runs`` — tables ADR-018 (namespaced)

        Les tables ADR-018 sont créées automatiquement si elles sont absentes
        (elles existent déjà si ``UnifiedStorage.migrate()`` a été appelé).
        """
        conn = self._get_connection()

        # Valeurs partagées entre les deux INSERT
        pr = pipeline_run
        run_values = (
            pr.pipeline_run_id,
            pr.pipeline_name,
            pr.pipeline_version,
            pr.status.value,
            pr.triggered_by,
            json.dumps(pr.context),
            pr.error,
            pr.start_time.isoformat() if pr.start_time else None,
            pr.end_time.isoformat() if pr.end_time else None,
            pr.duration_ms,
            json.dumps(pr.trigger_data),
            json.dumps(pr.metadata),
            pr.created_at.isoformat(),
            pr.updated_at.isoformat(),
        )

        try:
            with conn:
                self._ensure_pl_tables(conn)

                # ── tables historiques (rétrocompatibilité) ───────────────
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pipeline_runs (
                        pipeline_run_id, pipeline_name, pipeline_version,
                        status, triggered_by, context, error,
                        start_time, end_time, duration_ms,
                        trigger_data, metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    run_values,
                )

                # ── tables ADR-018 pl_* (namespaced, lues par l'UI/stats) ─
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pl_pipeline_runs (
                        pipeline_run_id, pipeline_name, pipeline_version,
                        status, triggered_by, context, error,
                        start_time, end_time, duration_ms,
                        trigger_data, metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    run_values,
                )

                # ── stage runs ────────────────────────────────────────────
                for sr in pr.stage_runs:
                    job_run_id = sr.job_run.job_run_id if sr.job_run else None
                    stage_values = (
                        sr.stage_run_id,
                        pr.pipeline_run_id,
                        sr.job_name,
                        sr.stage_index,
                        sr.status.value,
                        1 if sr.skipped else 0,
                        sr.skip_reason or "",
                        sr.error,
                        sr.start_time.isoformat() if sr.start_time else None,
                        sr.end_time.isoformat() if sr.end_time else None,
                        sr.duration_ms,
                        json.dumps(sr.metadata),
                        job_run_id,
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO stage_runs (
                            stage_run_id, pipeline_run_id, job_name, stage_index,
                            status, skipped, skip_reason, error,
                            start_time, end_time, duration_ms, metadata, job_run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        stage_values,
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO pl_stage_runs (
                            stage_run_id, pipeline_run_id, job_name, stage_index,
                            status, skipped, skip_reason, error,
                            start_time, end_time, duration_ms, metadata, job_run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        stage_values,
                    )
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save pipeline run: {e}") from e

    def get_pipeline_run(self, pipeline_run_id: str) -> PipelineRun | None:
        """Récupère un PipelineRun complet (avec StageRuns) par son identifiant."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE pipeline_run_id = ?",
                (pipeline_run_id,),
            ).fetchone()
            if row is None:
                return None
            stage_rows = conn.execute(
                "SELECT * FROM stage_runs WHERE pipeline_run_id = ? ORDER BY stage_index",
                (pipeline_run_id,),
            ).fetchall()
            return self._deserialize_pipeline_run(row, stage_rows)
        except sqlite3.Error as e:
            raise StorageError(f"Failed to get pipeline run: {e}") from e

    def list_pipeline_runs(
        self,
        pipeline_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[PipelineRun]:
        """Liste les PipelineRuns avec filtrage optionnel."""
        conn = self._get_connection()
        try:
            conditions: list[str] = []
            params: list[Any] = []
            if pipeline_name is not None:
                conditions.append("pipeline_name = ?")
                params.append(pipeline_name)
            if status is not None:
                conditions.append("status = ?")
                params.append(status)
            if since is not None:
                conditions.append("created_at >= ?")
                params.append(since.isoformat())
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT * FROM pipeline_runs {where} ORDER BY created_at DESC"
            if limit is not None:
                query += f" LIMIT {limit} OFFSET {offset}"
            elif offset > 0:
                query += f" LIMIT -1 OFFSET {offset}"
            rows = conn.execute(query, params).fetchall()
            result = []
            for row in rows:
                stage_rows = conn.execute(
                    "SELECT * FROM stage_runs WHERE pipeline_run_id = ? ORDER BY stage_index",
                    (row["pipeline_run_id"],),
                ).fetchall()
                result.append(self._deserialize_pipeline_run(row, stage_rows))
            return result
        except sqlite3.Error as e:
            raise StorageError(f"Failed to list pipeline runs: {e}") from e

    def _deserialize_pipeline_run(
        self,
        row: sqlite3.Row,
        stage_rows: list[sqlite3.Row],
    ) -> PipelineRun:
        """Désérialise un PipelineRun depuis des lignes SQLite."""
        from pyworkflow_engine.models.enums import RunStatus

        def _ts(val: str | None) -> datetime | None:
            return datetime.fromisoformat(val) if val else None

        return PipelineRun(
            pipeline_run_id=row["pipeline_run_id"],
            pipeline_name=row["pipeline_name"],
            pipeline_version=row["pipeline_version"] or "1.0.0",
            status=RunStatus(row["status"]),
            triggered_by=row["triggered_by"] or "manual",
            context=json.loads(row["context"]) if row["context"] else {},
            error=row["error"],
            start_time=_ts(row["start_time"]),
            end_time=_ts(row["end_time"]),
            duration_ms=row["duration_ms"],
            trigger_data=json.loads(row["trigger_data"]) if row["trigger_data"] else {},
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            stage_runs=[self._deserialize_stage_run(sr) for sr in stage_rows],
        )

    def _deserialize_stage_run(self, row: sqlite3.Row) -> StageRun:
        """Désérialise un StageRun depuis une ligne SQLite.

        Si ``job_run_id`` est présent dans la ligne (v5+), charge également
        le ``JobRun`` correspondant (avec ses ``step_runs``) afin que la vue
        GUI puisse afficher le détail des steps par stage.
        """
        from pyworkflow_engine.models.enums import RunStatus

        def _ts(val: str | None) -> datetime | None:
            return datetime.fromisoformat(val) if val else None

        stage_run = StageRun(
            stage_run_id=row["stage_run_id"],
            pipeline_run_id=row["pipeline_run_id"],
            job_name=row["job_name"],
            stage_index=row["stage_index"],
            status=RunStatus(row["status"]),
            skipped=bool(row["skipped"]),
            skip_reason=row["skip_reason"] or "",
            error=row["error"],
            start_time=_ts(row["start_time"]),
            end_time=_ts(row["end_time"]),
            duration_ms=row["duration_ms"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

        # Charger le JobRun sous-jacent si job_run_id est stocké (schema v5+)
        job_run_id = row["job_run_id"] if "job_run_id" in row.keys() else None
        if job_run_id:
            try:
                stage_run.job_run = self.get_job_run(job_run_id)
            except Exception:  # noqa: BLE001
                pass  # Ne pas casser la désérialisation si le job_run est absent

        return stage_run

    def health_check(self) -> dict[str, Any]:
        """Check the health of the persistence backend."""
        try:
            conn = self._get_connection()

            # Test basic query
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            job_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM job_runs")
            run_count = cursor.fetchone()[0]

            # Check database file size
            db_size = (
                self.database_path.stat().st_size if self.database_path.exists() else 0
            )

            # Test write capability
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (-1,)
            )
            conn.execute("DELETE FROM schema_version WHERE version = ?", (-1,))
            conn.commit()

            return {
                "status": "healthy",
                "backend": "sqlite",
                "database_path": str(self.database_path),
                "job_count": job_count,
                "run_count": run_count,
                "database_size_bytes": db_size,
                "writable": True,
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "backend": "sqlite",
                "database_path": str(self.database_path),
                "error": str(e),
                "writable": False,
            }

    def get_statistics(self) -> dict[str, Any]:
        """Get persistence backend statistics."""
        health = self.health_check()

        if health["status"] == "unhealthy":
            return health

        try:
            conn = self._get_connection()

            # Get additional statistics
            cursor = conn.execute(
                """
                SELECT
                    status,
                    COUNT(*) as count
                FROM job_runs
                GROUP BY status
            """
            )
            status_counts = dict(cursor.fetchall())

            # Get recent activity
            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM job_runs
                WHERE created_at >= datetime('now', '-1 day')
            """
            )
            runs_last_24h = cursor.fetchone()[0]

            return {
                "backend": "sqlite",
                "total_jobs": health["job_count"],
                "total_runs": health["run_count"],
                "status_counts": status_counts,
                "runs_last_24h": runs_last_24h,
                "database_size_bytes": health["database_size_bytes"],
                "database_path": health["database_path"],
            }

        except Exception as e:
            return {
                "backend": "sqlite",
                "error": str(e),
            }

    def close(self) -> None:
        """Close database connections."""
        if hasattr(self._local, "connection"):
            self._local.connection.close()
            delattr(self._local, "connection")
