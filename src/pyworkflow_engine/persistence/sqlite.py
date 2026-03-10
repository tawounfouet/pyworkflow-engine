"""
SQLite persistence implementation for the IAS Workflow Engine.

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
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator

from .base import BasePersistence, PersistenceError, JobNotFoundError, TransactionError
from ..core.models import JobRun, StepRun, Job


# Database schema version
SCHEMA_VERSION = 1

# SQL Schema definitions
SCHEMA_SQL = """
-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    name TEXT PRIMARY KEY,
    description TEXT,
    parameters TEXT,  -- JSON
    steps TEXT,       -- JSON array of steps
    metadata TEXT,    -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Job runs table
CREATE TABLE IF NOT EXISTS job_runs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    parameters TEXT,  -- JSON
    metadata TEXT,    -- JSON
    FOREIGN KEY (job_name) REFERENCES jobs(name) ON DELETE CASCADE
);

-- Step runs table  
CREATE TABLE IF NOT EXISTS step_runs (
    id TEXT PRIMARY KEY,
    job_run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    input_data TEXT,    -- JSON
    output_data TEXT,   -- JSON
    error_message TEXT,
    metadata TEXT,      -- JSON
    FOREIGN KEY (job_run_id) REFERENCES job_runs(id) ON DELETE CASCADE
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

    def _serialize_job(self, job: Job) -> Dict[str, Any]:
        """Serialize a job for database storage."""
        return {
            "name": job.name,
            "description": job.description,
            "parameters": json.dumps(job.parameters) if job.parameters else None,
            "steps": json.dumps(
                [
                    {
                        "name": step.name,
                        "type": step.type,
                        "function": step.function,
                        "parameters": step.parameters,
                        "depends_on": list(step.depends_on),
                        "timeout": step.timeout,
                    }
                    for step in job.steps
                ]
            ),
            "metadata": json.dumps(job.metadata) if job.metadata else None,
        }

    def _deserialize_job(self, row: sqlite3.Row) -> Job:
        """Deserialize a job from database row."""
        from ..core.models import Step

        steps_data = json.loads(row["steps"])
        steps = []

        for step_data in steps_data:
            step = Step(
                name=step_data["name"],
                type=step_data["type"],
                function=step_data["function"],
                parameters=step_data.get("parameters", {}),
                depends_on=set(step_data.get("depends_on", [])),
                timeout=step_data.get("timeout"),
            )
            steps.append(step)

        return Job(
            name=row["name"],
            description=row["description"] or "",
            parameters=json.loads(row["parameters"]) if row["parameters"] else {},
            steps=steps,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _serialize_job_run(self, job_run: JobRun) -> Dict[str, Any]:
        """Serialize a job run for database storage."""
        return {
            "id": job_run.id,
            "job_name": job_run.job_name,
            "status": job_run.status.value,
            "created_at": job_run.created_at.isoformat(),
            "started_at": (
                job_run.started_at.isoformat() if job_run.started_at else None
            ),
            "completed_at": (
                job_run.completed_at.isoformat() if job_run.completed_at else None
            ),
            "parameters": (
                json.dumps(job_run.parameters) if job_run.parameters else None
            ),
            "metadata": json.dumps(job_run.metadata) if job_run.metadata else None,
        }

    def _deserialize_job_run(
        self, row: sqlite3.Row, step_runs: List[StepRun] = None
    ) -> JobRun:
        """Deserialize a job run from database row."""
        from ..core.models import JobRunStatus

        return JobRun(
            id=row["id"],
            job_name=row["job_name"],
            status=JobRunStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=(
                datetime.fromisoformat(row["started_at"]) if row["started_at"] else None
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            parameters=json.loads(row["parameters"]) if row["parameters"] else {},
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            step_runs=step_runs or [],
        )

    def _serialize_step_run(self, step_run: StepRun) -> Dict[str, Any]:
        """Serialize a step run for database storage."""
        return {
            "id": step_run.id,
            "job_run_id": step_run.job_run_id,
            "step_name": step_run.step_name,
            "status": step_run.status.value,
            "created_at": step_run.created_at.isoformat(),
            "started_at": (
                step_run.started_at.isoformat() if step_run.started_at else None
            ),
            "completed_at": (
                step_run.completed_at.isoformat() if step_run.completed_at else None
            ),
            "input_data": (
                json.dumps(step_run.input_data)
                if step_run.input_data is not None
                else None
            ),
            "output_data": (
                json.dumps(step_run.output_data)
                if step_run.output_data is not None
                else None
            ),
            "error_message": step_run.error_message,
            "metadata": json.dumps(step_run.metadata) if step_run.metadata else None,
        }

    def _deserialize_step_run(self, row: sqlite3.Row) -> StepRun:
        """Deserialize a step run from database row."""
        from ..core.models import StepRunStatus

        return StepRun(
            id=row["id"],
            job_run_id=row["job_run_id"],
            step_name=row["step_name"],
            status=StepRunStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=(
                datetime.fromisoformat(row["started_at"]) if row["started_at"] else None
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            input_data=json.loads(row["input_data"]) if row["input_data"] else None,
            output_data=json.loads(row["output_data"]) if row["output_data"] else None,
            error_message=row["error_message"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _load_step_runs(self, job_run_id: str) -> List[StepRun]:
        """Load all step runs for a job run."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM step_runs WHERE job_run_id = ? ORDER BY created_at",
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
                INSERT OR REPLACE INTO jobs (name, description, parameters, steps, metadata)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    data["name"],
                    data["description"],
                    data["parameters"],
                    data["steps"],
                    data["metadata"],
                ),
            )
            conn.commit()
        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to save job '{job.name}': {e}") from e

    def get_job(self, job_name: str) -> Optional[Job]:
        """Retrieve a job definition by name."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM jobs WHERE name = ?", (job_name,))
            row = cursor.fetchone()
            return self._deserialize_job(row) if row else None
        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to get job '{job_name}': {e}") from e

    def list_jobs(self, limit: Optional[int] = None, offset: int = 0) -> List[Job]:
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
                (id, job_name, status, created_at, started_at, completed_at, parameters, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run_data["id"],
                    run_data["job_name"],
                    run_data["status"],
                    run_data["created_at"],
                    run_data["started_at"],
                    run_data["completed_at"],
                    run_data["parameters"],
                    run_data["metadata"],
                ),
            )

            # Save step runs
            for step_run in job_run.step_runs:
                step_data = self._serialize_step_run(step_run)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO step_runs 
                    (id, job_run_id, step_name, status, created_at, started_at, 
                     completed_at, input_data, output_data, error_message, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        step_data["id"],
                        step_data["job_run_id"],
                        step_data["step_name"],
                        step_data["status"],
                        step_data["created_at"],
                        step_data["started_at"],
                        step_data["completed_at"],
                        step_data["input_data"],
                        step_data["output_data"],
                        step_data["error_message"],
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
                "SELECT id FROM job_runs WHERE id = ?", (job_run.job_run_id,)
            )
            if not cursor.fetchone():
                raise JobNotFoundError(f"Job run {job_run.job_run_id} not found")

            # Update job run (same as save_job_run but with explicit update)
            run_data = self._serialize_job_run(job_run)
            conn.execute(
                """
                UPDATE job_runs 
                SET job_name=?, status=?, created_at=?, started_at=?, completed_at=?, 
                    parameters=?, metadata=?
                WHERE id=?
                """,
                (
                    run_data["job_name"],
                    run_data["status"],
                    run_data["created_at"],
                    run_data["started_at"],
                    run_data["completed_at"],
                    run_data["parameters"],
                    run_data["metadata"],
                    run_data["id"],
                ),
            )

            # Delete existing step runs and insert new ones
            conn.execute(
                "DELETE FROM step_runs WHERE job_run_id = ?", (job_run.job_run_id,)
            )

            # Save step runs
            for step_run in job_run.step_runs:
                step_data = self._serialize_step_run(step_run)
                conn.execute(
                    """
                    INSERT INTO step_runs 
                    (id, job_run_id, step_name, status, created_at, started_at, 
                     completed_at, input_data, output_data, error_message, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        step_data["id"],
                        step_data["job_run_id"],
                        step_data["step_name"],
                        step_data["status"],
                        step_data["created_at"],
                        step_data["started_at"],
                        step_data["completed_at"],
                        step_data["input_data"],
                        step_data["output_data"],
                        step_data["error_message"],
                        step_data["metadata"],
                    ),
                )

            conn.commit()

        except sqlite3.Error as e:
            raise PersistenceError(
                f"Failed to update job run '{job_run.job_run_id}': {e}"
            ) from e

    def get_job_run(self, run_id: str) -> Optional[JobRun]:
        """Retrieve a job run by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM job_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None

            # Load step runs
            step_runs = self._load_step_runs(run_id)
            return self._deserialize_job_run(row, step_runs)

        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to get job run '{run_id}': {e}") from e

    def list_job_runs(
        self,
        job_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        since: Optional[datetime] = None,
    ) -> List[JobRun]:
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
                step_runs = self._load_step_runs(row["id"])
                runs.append(self._deserialize_job_run(row, step_runs))

            return runs

        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to list job runs: {e}") from e

    def delete_job_run(self, run_id: str) -> bool:
        """Delete a job run and its step runs."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM job_runs WHERE id = ?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to delete job run '{run_id}': {e}") from e

    def get_job_run_count(self, job_name: Optional[str] = None) -> int:
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

    def cleanup_old_runs(self, older_than: datetime) -> int:
        """Remove job runs older than the specified datetime."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM job_runs WHERE created_at < ?", (older_than.isoformat(),)
            )
            conn.commit()
            return cursor.rowcount
        except sqlite3.Error as e:
            raise PersistenceError(f"Failed to cleanup old runs: {e}") from e

    def health_check(self) -> Dict[str, Any]:
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

    def get_statistics(self) -> Dict[str, Any]:
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
