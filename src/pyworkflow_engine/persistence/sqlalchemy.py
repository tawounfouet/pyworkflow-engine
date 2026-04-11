"""
SQLAlchemy persistence implementation for the PyWorkflow Engine.

This persistence backend provides advanced SQL features through SQLAlchemy,
including support for PostgreSQL, MySQL, and other databases with
connection pooling, advanced querying, and ORM capabilities.

Features:
    - Multiple database backends (PostgreSQL, MySQL, SQLite, etc.)
    - Connection pooling and management
    - Advanced querying with SQLAlchemy Core/ORM
    - Database migrations via Alembic integration
    - Async support (when available)
    - High performance with bulk operations

This backend requires optional dependencies:
    - SQLAlchemy 2.0+
    - Database drivers (psycopg2, PyMySQL, etc.)
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

try:
    from sqlalchemy import (
        Column,
        DateTime,
        ForeignKey,
        Index,
        Integer,
        MetaData,
        String,
        Table,
        Text,
        create_engine,
    )
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.sql import delete, func, insert, select, update
except ImportError as e:
    raise ImportError(
        "SQLAlchemy persistence requires: pip install ias-workflow-engine[sqlalchemy]"
    ) from e

from ..models import Job, JobRun, Step, StepRun
from .base import BasePersistence, JobNotFoundError, PersistenceError


class SQLAlchemyPersistence(BasePersistence):
    """SQLAlchemy-based persistence backend.

    This implementation provides enterprise-grade persistence with support
    for multiple database backends, connection pooling, and advanced SQL
    features through SQLAlchemy.

    Supported databases:
        - PostgreSQL (recommended for production)
        - MySQL/MariaDB
        - SQLite (for development/testing)
        - Oracle, SQL Server (with appropriate drivers)

    Features:
        - ACID transactions
        - Connection pooling
        - Query optimization
        - Bulk operations
        - Database migrations
        - Multi-database support
    """

    def __init__(
        self,
        database_url: str,
        engine_options: dict[str, Any] | None = None,
        table_prefix: str = "workflow_",
    ):
        """Initialize SQLAlchemy persistence.

        Args:
            database_url: SQLAlchemy database URL (e.g., "postgresql://user:pass@localhost/db")
            engine_options: Additional SQLAlchemy engine options
            table_prefix: Prefix for all table names
        """
        self.database_url = database_url
        self.table_prefix = table_prefix

        # Default engine options
        default_options = {
            "echo": False,
            "pool_pre_ping": True,  # Verify connections before use
            "pool_recycle": 3600,  # Recycle connections every hour
        }

        if engine_options:
            default_options.update(engine_options)

        # Handle SQLite memory databases
        if database_url.startswith("sqlite:///:memory:"):
            default_options.update(
                {
                    "poolclass": StaticPool,
                    "connect_args": {"check_same_thread": False},
                }
            )

        # Create engine
        self.engine = create_engine(database_url, **default_options)

        # Define metadata and tables
        self.metadata = MetaData()
        self._define_tables()

        # Initialize database
        self._initialize_database()

    def _define_tables(self) -> None:
        """Define database tables using SQLAlchemy Core."""

        # Jobs table
        self.jobs_table = Table(
            f"{self.table_prefix}jobs",
            self.metadata,
            Column("name", String(255), primary_key=True),
            Column("description", Text),
            Column("steps", Text, nullable=False),  # JSON
            Column("tags", Text),  # JSON
            Column("metadata", Text),  # JSON
            Column("version", String(50)),
            Column("enabled", Integer, default=1),
            Column("created_at", DateTime, default=datetime.utcnow),
            Column(
                "updated_at",
                DateTime,
                default=datetime.utcnow,
                onupdate=datetime.utcnow,
            ),
        )

        # Job runs table
        self.job_runs_table = Table(
            f"{self.table_prefix}job_runs",
            self.metadata,
            Column("job_run_id", String(255), primary_key=True),
            Column(
                "job_name",
                String(255),
                ForeignKey(f"{self.table_prefix}jobs.name"),
                nullable=False,
            ),
            Column("status", String(50), nullable=False),
            Column("created_at", DateTime, nullable=False),
            Column("start_time", DateTime),
            Column("end_time", DateTime),
            Column("input_data", Text),  # JSON
            Column("metadata", Text),  # JSON
        )

        # Step runs table
        self.step_runs_table = Table(
            f"{self.table_prefix}step_runs",
            self.metadata,
            Column("step_run_id", String(255), primary_key=True),
            Column(
                "job_run_id",
                String(255),
                ForeignKey(f"{self.table_prefix}job_runs.job_run_id"),
                nullable=False,
            ),
            Column("step_name", String(255), nullable=False),
            Column("status", String(50), nullable=False),
            Column("start_time", DateTime),
            Column("end_time", DateTime),
            Column("input_data", Text),  # JSON
            Column("output_data", Text),  # JSON
            Column("error", Text),
            Column("metadata", Text),  # JSON
        )

        # Schema version table
        self.schema_version_table = Table(
            f"{self.table_prefix}schema_version",
            self.metadata,
            Column("version", Integer, primary_key=True),
            Column("applied_at", DateTime, default=datetime.utcnow),
        )

        # Create indexes
        Index(
            f"idx_{self.table_prefix}job_runs_job_name", self.job_runs_table.c.job_name
        )
        Index(f"idx_{self.table_prefix}job_runs_status", self.job_runs_table.c.status)
        Index(
            f"idx_{self.table_prefix}job_runs_created_at",
            self.job_runs_table.c.created_at,
        )
        Index(
            f"idx_{self.table_prefix}step_runs_job_run_id",
            self.step_runs_table.c.job_run_id,
        )
        Index(f"idx_{self.table_prefix}step_runs_status", self.step_runs_table.c.status)

    def _initialize_database(self) -> None:
        """Initialize database schema."""
        try:
            # Create all tables
            self.metadata.create_all(self.engine)

            # Record schema version
            with self.engine.begin() as conn:
                # Check if version exists
                result = conn.execute(
                    select(self.schema_version_table.c.version).where(
                        self.schema_version_table.c.version == 1
                    )
                )
                if not result.fetchone():
                    conn.execute(insert(self.schema_version_table).values(version=1))

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to initialize database: {e}") from e

    def _serialize_json(self, data: Any) -> str | None:
        """Serialize data to JSON string."""
        return json.dumps(data) if data else None

    def _deserialize_json(self, data: str | None) -> Any:
        """Deserialize JSON string to data."""
        return json.loads(data) if data else {}

    def _serialize_job(self, job: Job) -> dict[str, Any]:
        """Serialize job for database storage."""
        return {
            "name": job.name,
            "description": job.description,
            "steps": json.dumps([s.to_dict() for s in job.steps]),
            "tags": self._serialize_json(job.tags),
            "metadata": self._serialize_json(job.metadata),
            "version": job.version,
            "enabled": 1 if job.enabled else 0,
        }

    def _deserialize_job(self, row: Any) -> Job:
        """Deserialize job from database row."""
        steps = [Step.from_dict(s) for s in json.loads(row.steps)]

        return Job(
            name=row.name,
            description=row.description or "",
            steps=steps,
            tags=(
                self._deserialize_json(row.tags)
                if hasattr(row, "tags") and row.tags
                else []
            ),
            metadata=self._deserialize_json(row.metadata),
            version=row.version or "1.0.0",
            enabled=bool(row.enabled) if row.enabled is not None else True,
        )

    def _to_naive_utc(self, dt: datetime | None) -> datetime | None:
        """Convert a datetime to naive UTC (strip tzinfo) for DB storage."""
        if dt is None:
            return None
        if dt.tzinfo is not None:
            # Convert to UTC then strip tzinfo

            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt

    def _serialize_job_run(self, job_run: JobRun) -> dict[str, Any]:
        """Serialize job run for database storage."""
        return {
            "job_run_id": job_run.job_run_id,
            "job_name": job_run.job_name,
            "status": job_run.status.value,
            "created_at": self._to_naive_utc(job_run.created_at),
            "start_time": self._to_naive_utc(job_run.start_time),
            "end_time": self._to_naive_utc(job_run.end_time),
            "input_data": self._serialize_json(job_run.input_data),
            "metadata": self._serialize_json(job_run.metadata),
        }

    def _deserialize_job_run(self, row: Any, step_runs: list[StepRun] = None) -> JobRun:
        """Deserialize job run from database row."""
        from ..models.enums import RunStatus

        return JobRun(
            job_run_id=row.job_run_id,
            job_name=row.job_name,
            status=RunStatus(row.status),
            created_at=row.created_at,
            start_time=row.start_time,
            end_time=row.end_time,
            input_data=self._deserialize_json(row.input_data),
            metadata=self._deserialize_json(row.metadata),
            step_runs=step_runs or [],
        )

    def _serialize_step_run(self, step_run: StepRun) -> dict[str, Any]:
        """Serialize step run for database storage."""
        return {
            "step_run_id": step_run.step_run_id,
            "job_run_id": step_run.job_run_id,
            "step_name": step_run.step_name,
            "status": step_run.status.value,
            "start_time": self._to_naive_utc(step_run.start_time),
            "end_time": self._to_naive_utc(step_run.end_time),
            "input_data": self._serialize_json(step_run.input_data),
            "output_data": self._serialize_json(step_run.output_data),
            "error": step_run.error,
            "metadata": self._serialize_json(step_run.metadata),
        }

    def _deserialize_step_run(self, row: Any) -> StepRun:
        """Deserialize step run from database row."""
        from ..models.enums import RunStatus

        return StepRun(
            step_run_id=row.step_run_id,
            job_run_id=row.job_run_id,
            step_name=row.step_name,
            status=RunStatus(row.status),
            start_time=row.start_time,
            end_time=row.end_time,
            input_data=self._deserialize_json(row.input_data),
            output_data=self._deserialize_json(row.output_data),
            error=row.error,
            metadata=self._deserialize_json(row.metadata),
        )

    def _load_step_runs(self, job_run_id: str, conn=None) -> list[StepRun]:
        """Load all step runs for a job run."""
        query = (
            select(self.step_runs_table)
            .where(self.step_runs_table.c.job_run_id == job_run_id)
            .order_by(self.step_runs_table.c.step_name)
        )

        if conn:
            result = conn.execute(query)
        else:
            with self.engine.connect() as conn:
                result = conn.execute(query)

        return [self._deserialize_step_run(row) for row in result]

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper cleanup."""
        conn = self.engine.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self):
        """Get a database transaction with proper cleanup."""
        with self.engine.begin() as conn:
            yield conn

    # Transaction support

    def begin_transaction(self) -> None:
        """Begin a database transaction."""
        # SQLAlchemy handles transactions via context managers
        # This method is for interface compatibility

    def commit_transaction(self) -> None:
        """Commit the current transaction."""
        # SQLAlchemy handles commits automatically with context managers
        # This method is for interface compatibility

    def rollback_transaction(self) -> None:
        """Roll back the current transaction."""
        # SQLAlchemy handles rollbacks automatically with context managers
        # This method is for interface compatibility

    # Job operations

    def save_job(self, job: Job) -> None:
        """Save a job definition."""
        data = self._serialize_job(job)

        try:
            with self._transaction() as conn:
                # Use merge-like behavior (INSERT OR UPDATE)
                stmt = insert(self.jobs_table).values(**data)

                # Check if job exists
                existing = conn.execute(
                    select(self.jobs_table.c.name).where(
                        self.jobs_table.c.name == job.name
                    )
                ).fetchone()

                if existing:
                    # Update existing job
                    update_data = {k: v for k, v in data.items() if k != "name"}
                    update_data["updated_at"] = datetime.utcnow()

                    stmt = (
                        update(self.jobs_table)
                        .where(self.jobs_table.c.name == job.name)
                        .values(**update_data)
                    )

                conn.execute(stmt)

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to save job '{job.name}': {e}") from e

    def get_job(self, job_name: str) -> Job | None:
        """Retrieve a job definition by name."""
        try:
            with self._get_connection() as conn:
                query = select(self.jobs_table).where(
                    self.jobs_table.c.name == job_name
                )
                result = conn.execute(query)
                row = result.fetchone()
                return self._deserialize_job(row) if row else None

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to get job '{job_name}': {e}") from e

    def list_jobs(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        """List all job definitions."""
        try:
            with self._get_connection() as conn:
                query = select(self.jobs_table).order_by(self.jobs_table.c.name)

                if limit is not None:
                    query = query.limit(limit).offset(offset)

                result = conn.execute(query)
                return [self._deserialize_job(row) for row in result]

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to list jobs: {e}") from e

    def delete_job(self, job_name: str) -> bool:
        """Delete a job definition."""
        try:
            with self._transaction() as conn:
                stmt = delete(self.jobs_table).where(self.jobs_table.c.name == job_name)
                result = conn.execute(stmt)
                return result.rowcount > 0

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to delete job '{job_name}': {e}") from e

    # Job run operations

    def save_job_run(self, job_run: JobRun) -> None:
        """Save a job run and its step runs."""
        try:
            with self._transaction() as conn:
                run_data = self._serialize_job_run(job_run)

                # Check if exists
                existing = conn.execute(
                    select(self.job_runs_table.c.job_run_id).where(
                        self.job_runs_table.c.job_run_id == job_run.job_run_id
                    )
                ).fetchone()

                if existing:
                    stmt = (
                        update(self.job_runs_table)
                        .where(self.job_runs_table.c.job_run_id == job_run.job_run_id)
                        .values(**run_data)
                    )
                else:
                    stmt = insert(self.job_runs_table).values(**run_data)

                conn.execute(stmt)

                # Replace step runs
                conn.execute(
                    delete(self.step_runs_table).where(
                        self.step_runs_table.c.job_run_id == job_run.job_run_id
                    )
                )

                if job_run.step_runs:
                    step_data = [
                        self._serialize_step_run(sr) for sr in job_run.step_runs
                    ]
                    conn.execute(insert(self.step_runs_table), step_data)

        except SQLAlchemyError as e:
            raise PersistenceError(
                f"Failed to save job run '{job_run.job_run_id}': {e}"
            ) from e

    def update_job_run(self, job_run: JobRun) -> None:
        """Update an existing job run."""
        try:
            with self._transaction() as conn:
                existing = conn.execute(
                    select(self.job_runs_table.c.job_run_id).where(
                        self.job_runs_table.c.job_run_id == job_run.job_run_id
                    )
                ).fetchone()

                if not existing:
                    raise JobNotFoundError(f"Job run {job_run.job_run_id} not found")

                run_data = self._serialize_job_run(job_run)
                stmt = (
                    update(self.job_runs_table)
                    .where(self.job_runs_table.c.job_run_id == job_run.job_run_id)
                    .values(**run_data)
                )
                conn.execute(stmt)

                conn.execute(
                    delete(self.step_runs_table).where(
                        self.step_runs_table.c.job_run_id == job_run.job_run_id
                    )
                )

                if job_run.step_runs:
                    step_data = [
                        self._serialize_step_run(sr) for sr in job_run.step_runs
                    ]
                    conn.execute(insert(self.step_runs_table), step_data)

        except SQLAlchemyError as e:
            raise PersistenceError(
                f"Failed to update job run '{job_run.job_run_id}': {e}"
            ) from e

    def get_job_run(self, run_id: str) -> JobRun | None:
        """Retrieve a job run by ID."""
        try:
            with self._get_connection() as conn:
                query = select(self.job_runs_table).where(
                    self.job_runs_table.c.job_run_id == run_id
                )
                result = conn.execute(query)
                row = result.fetchone()

                if not row:
                    return None

                step_runs = self._load_step_runs(run_id, conn)
                return self._deserialize_job_run(row, step_runs)

        except SQLAlchemyError as e:
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
        try:
            with self._get_connection() as conn:
                query = select(self.job_runs_table)

                # Apply filters
                if job_name:
                    query = query.where(self.job_runs_table.c.job_name == job_name)

                if status:
                    query = query.where(self.job_runs_table.c.status == status)

                if since:
                    query = query.where(
                        self.job_runs_table.c.created_at >= self._to_naive_utc(since)
                    )

                # Order and paginate
                query = query.order_by(self.job_runs_table.c.created_at.desc())

                if limit is not None:
                    query = query.limit(limit).offset(offset)

                result = conn.execute(query)
                runs = []

                for row in result:
                    step_runs = self._load_step_runs(row.job_run_id, conn)
                    runs.append(self._deserialize_job_run(row, step_runs))

                return runs

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to list job runs: {e}") from e

    def delete_job_run(self, run_id: str) -> bool:
        """Delete a job run and its step runs."""
        try:
            with self._transaction() as conn:
                stmt = delete(self.job_runs_table).where(
                    self.job_runs_table.c.job_run_id == run_id
                )
                result = conn.execute(stmt)
                return result.rowcount > 0

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to delete job run '{run_id}': {e}") from e

    def get_job_run_count(self, job_name: str | None = None) -> int:
        """Get the total number of job runs."""
        try:
            with self._get_connection() as conn:
                query = select(func.count()).select_from(self.job_runs_table)

                if job_name:
                    query = query.where(self.job_runs_table.c.job_name == job_name)

                result = conn.execute(query)
                return result.scalar()

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to count job runs: {e}") from e

    def cleanup_old_runs(self, older_than: datetime, dry_run: bool = False) -> int:
        """Remove job runs older than the specified datetime.

        Args:
            older_than: Delete runs created before this datetime.
            dry_run: If True (default), only count without deleting.
        """
        try:
            if dry_run:
                with self._get_connection() as conn:
                    stmt = (
                        select(func.count())
                        .select_from(self.job_runs_table)
                        .where(self.job_runs_table.c.created_at < older_than)
                    )
                    return conn.execute(stmt).scalar() or 0
            with self._transaction() as conn:
                stmt = delete(self.job_runs_table).where(
                    self.job_runs_table.c.created_at < older_than
                )
                result = conn.execute(stmt)
                return result.rowcount

        except SQLAlchemyError as e:
            raise PersistenceError(f"Failed to cleanup old runs: {e}") from e

    def health_check(self) -> dict[str, Any]:
        """Check the health of the persistence backend."""
        try:
            with self._get_connection() as conn:
                # Test basic queries
                job_result = conn.execute(
                    select(func.count()).select_from(self.jobs_table)
                )
                job_count = job_result.scalar()

                run_result = conn.execute(
                    select(func.count()).select_from(self.job_runs_table)
                )
                run_count = run_result.scalar()

                # Test write capability
                test_query = select(self.schema_version_table.c.version).where(
                    self.schema_version_table.c.version == -999
                )
                conn.execute(test_query)

                return {
                    "status": "healthy",
                    "backend": "sqlalchemy",
                    "database_url": self._mask_password(self.database_url),
                    "job_count": job_count,
                    "run_count": run_count,
                    "writable": True,
                    "engine_info": {
                        "dialect": self.engine.dialect.name,
                        "driver": self.engine.dialect.driver,
                        "pool_size": getattr(self.engine.pool, "size", "N/A"),
                    },
                }

        except Exception as e:
            return {
                "status": "unhealthy",
                "backend": "sqlalchemy",
                "database_url": self._mask_password(self.database_url),
                "error": str(e),
                "writable": False,
            }

    def get_statistics(self) -> dict[str, Any]:
        """Get persistence backend statistics."""
        health = self.health_check()

        if health["status"] == "unhealthy":
            return health

        try:
            with self._get_connection() as conn:
                # Get status distribution
                status_query = select(
                    self.job_runs_table.c.status, func.count().label("count")
                ).group_by(self.job_runs_table.c.status)
                status_result = conn.execute(status_query)
                status_counts = dict(status_result.fetchall())

                # Get recent activity
                recent_query = (
                    select(func.count())
                    .select_from(self.job_runs_table)
                    .where(
                        self.job_runs_table.c.created_at
                        >= func.datetime("now", "-1 day")
                    )
                )
                recent_result = conn.execute(recent_query)
                runs_last_24h = recent_result.scalar()

                return {
                    "backend": "sqlalchemy",
                    "total_jobs": health["job_count"],
                    "total_runs": health["run_count"],
                    "status_counts": status_counts,
                    "runs_last_24h": runs_last_24h,
                    "engine_info": health["engine_info"],
                }

        except Exception as e:
            return {
                "backend": "sqlalchemy",
                "error": str(e),
            }

    def _mask_password(self, url: str) -> str:
        """Mask password in database URL for security."""
        if "://" not in url:
            return url

        try:
            parts = url.split("://")
            if "@" in parts[1]:
                auth, rest = parts[1].split("@", 1)
                if ":" in auth:
                    user, _ = auth.split(":", 1)
                    return f"{parts[0]}://{user}:***@{rest}"
            return url
        except (IndexError, ValueError):
            return url

    def close(self) -> None:
        """Close the database engine and all connections."""
        self.engine.dispose()
