"""
SQLite persistence implementation for the PyWorkflow Engine.

This persistence backend uses SQLite database for reliable storage with
ACID transactions and SQL querying capabilities. It uses only Python's
standard library sqlite3 module, making it suitable for production
deployments where SQLite is sufficient.

Features:
    - ACID transactions
    - Efficient indexing and querying
    - WAL mode for better concurrency
    - Schema versioning and migrations
    - No external dependencies (stdlib only)
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import Job, JobRun, StepRun
from .base import BasePersistence, JobNotFoundError, PersistenceError, TransactionError

# Database schema version
SCHEMA_VERSION = 2

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

-- Triggers to update timestamps
CREATE TRIGGER IF NOT EXISTS update_jobs_timestamp
    AFTER UPDATE ON jobs
    FOR EACH ROW
BEGIN
    UPDATE jobs SET updated_at = CURRENT_TIMESTAMP WHERE name = NEW.name;
END;
"""


class SQLitePersistence(BasePersistence):
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

        # Initialize database
        self._initialize_database()

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
                    conn.executescript(SCHEMA_SQL)
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                    conn.commit()

            except sqlite3.Error as e:
                raise PersistenceError(f"Failed to initialize database: {e}") from e

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
        from ..models import Job, Step

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
        from ..models.enums import RunStatus

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
        from ..models.enums import ExecutorType, RunStatus

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
            raise PersistenceError(f"Failed to load step runs: {e}") from e

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
            raise PersistenceError(f"Failed to save job '{job.name}': {e}") from e

    def get_job(self, job_name: str) -> Job | None:
        """Retrieve a job definition by name."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM jobs WHERE name = ?", (job_name,))
            row = cursor.fetchone()
            return self._deserialize_job(row) if row else None
        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to get job '{job_name}': {e}") from e

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
            raise PersistenceError(f"Failed to list jobs: {e}") from e

    def delete_job(self, job_name: str) -> bool:
        """Delete a job definition."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM jobs WHERE name = ?", (job_name,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to delete job '{job_name}': {e}") from e

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
            raise PersistenceError(
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
            raise PersistenceError(
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
            raise PersistenceError(f"Failed to get job run '{run_id}': {e}") from e

    def list_job_runs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[JobRun]:
        """List job runs with optional filtering."""
        conn = self._get_connection()
        try:
            sql = "SELECT * FROM job_runs WHERE 1=1"
            params = []

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

            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])

            cursor = conn.execute(sql, params)
            runs = []

            for row in cursor.fetchall():
                step_runs = self._load_step_runs(row["job_run_id"])
                runs.append(self._deserialize_job_run(row, step_runs))

            return runs

        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to list job runs: {e}") from e

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
            raise PersistenceError(f"Failed to delete job run '{run_id}': {e}") from e

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
            raise PersistenceError(f"Failed to count job runs: {e}") from e

    def cleanup_old_runs(self, older_than: datetime, dry_run: bool = False) -> int:
        """Remove job runs older than the specified datetime.

        Args:
            older_than: Delete runs created before this datetime.
            dry_run: If True (default), only count without deleting.
        """
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
            raise PersistenceError(f"Failed to cleanup old runs: {e}") from e

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
