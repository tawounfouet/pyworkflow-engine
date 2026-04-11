"""
In-memory persistence backend for the PyWorkflow Engine.

Provides fast, thread-safe storage for development and testing.
Data is stored in memory and lost when the process exits.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job, JobRun

from pyworkflow_engine.persistence.base import BasePersistence, JobNotFoundError, PersistenceError


class InMemoryPersistence(BasePersistence):
    """In-memory persistence backend.

    Stores all data in memory using thread-safe data structures.
    Ideal for development, testing, and temporary workflows.

    Features:
    - Thread-safe operations
    - Fast access times
    - Full transaction support (rollback via snapshots)
    - No external dependencies
    - Data lost on process exit

    Usage:
        persistence = InMemoryPersistence()
        engine = WorkflowEngine(persistence=persistence)
    """

    def __init__(self):
        """Initialize the in-memory persistence backend."""
        self._jobs: dict[str, Job] = {}
        self._job_runs: dict[str, JobRun] = {}
        self._lock = threading.RLock()

        # Transaction support
        self._transaction_active = False
        self._transaction_snapshots: dict[str, Any] | None = None

    def save_job(self, job: Job) -> None:
        """Save a job definition."""
        with self._lock:
            # Deep copy to prevent external mutations
            self._jobs[job.name] = deepcopy(job)

    def get_job(self, job_name: str) -> Job | None:
        """Retrieve a job definition by name."""
        with self._lock:
            job = self._jobs.get(job_name)
            return deepcopy(job) if job else None

    def list_jobs(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        """List all job definitions."""
        with self._lock:
            jobs = list(self._jobs.values())
            jobs.sort(key=lambda j: j.name)  # Consistent ordering

            # Apply pagination
            if offset > 0:
                jobs = jobs[offset:]
            if limit is not None:
                jobs = jobs[:limit]

            return [deepcopy(job) for job in jobs]

    def delete_job(self, job_name: str) -> bool:
        """Delete a job definition."""
        with self._lock:
            if job_name in self._jobs:
                del self._jobs[job_name]
                return True
            return False

    def save_job_run(self, job_run: JobRun) -> None:
        """Save a job run (execution state)."""
        with self._lock:
            self._job_runs[job_run.job_run_id] = deepcopy(job_run)

    def get_job_run(self, run_id: str) -> JobRun | None:
        """Retrieve a job run by ID."""
        with self._lock:
            job_run = self._job_runs.get(run_id)
            return deepcopy(job_run) if job_run else None

    def list_job_runs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[JobRun]:
        """List job runs with optional filtering."""
        with self._lock:
            job_runs = list(self._job_runs.values())

            # Apply filters
            if job_name is not None:
                job_runs = [jr for jr in job_runs if jr.job_name == job_name]

            if status is not None:
                # Accept both string and RunStatus enum for the filter value
                from pyworkflow_engine.models.enums import RunStatus

                status_val = RunStatus(status) if isinstance(status, str) else status
                job_runs = [jr for jr in job_runs if jr.status == status_val]

            if since is not None:
                job_runs = [jr for jr in job_runs if jr.created_at >= since]

            # Sort by created_at descending (most recent first).
            # Use job_run_id as a stable secondary sort key.
            job_runs.sort(
                key=lambda jr: (jr.created_at, jr.job_run_id),
                reverse=True,
            )

            # Apply pagination
            if offset > 0:
                job_runs = job_runs[offset:]
            if limit is not None:
                job_runs = job_runs[:limit]

            return [deepcopy(job_run) for job_run in job_runs]

    def delete_job_run(self, run_id: str) -> bool:
        """Delete a job run."""
        with self._lock:
            if run_id in self._job_runs:
                del self._job_runs[run_id]
                return True
            return False

    def update_job_run(self, job_run: JobRun) -> None:
        """Update an existing job run."""
        with self._lock:
            if job_run.job_run_id not in self._job_runs:
                raise JobNotFoundError(f"Job run {job_run.job_run_id} not found")

            self._job_runs[job_run.job_run_id] = deepcopy(job_run)

    def get_job_run_count(self, job_name: str | None = None) -> int:
        """Get the total number of job runs."""
        with self._lock:
            if job_name is not None:
                return sum(
                    1 for jr in self._job_runs.values() if jr.job_name == job_name
                )
            return len(self._job_runs)

    def cleanup_old_runs(self, older_than: datetime, dry_run: bool = False) -> int:
        """Remove job runs older than the specified datetime."""
        with self._lock:
            to_delete = [
                run_id
                for run_id, jr in self._job_runs.items()
                if jr.created_at < older_than
            ]
            if not dry_run:
                for run_id in to_delete:
                    del self._job_runs[run_id]
            return len(to_delete)

    # Transaction support

    def begin_transaction(self) -> None:
        """Begin a transaction by creating snapshots."""
        with self._lock:
            if self._transaction_active:
                raise PersistenceError("Transaction already active")

            # Create deep copies for rollback
            self._transaction_snapshots = {
                "jobs": deepcopy(self._jobs),
                "job_runs": deepcopy(self._job_runs),
            }
            self._transaction_active = True

    def commit_transaction(self) -> None:
        """Commit the current transaction."""
        with self._lock:
            if not self._transaction_active:
                raise PersistenceError("No active transaction to commit")

            # Discard snapshots - current state becomes committed
            self._transaction_snapshots = None
            self._transaction_active = False

    def rollback_transaction(self) -> None:
        """Rollback to transaction snapshots."""
        with self._lock:
            if not self._transaction_active:
                raise PersistenceError("No active transaction to rollback")

            if self._transaction_snapshots:
                # Restore from snapshots
                self._jobs = self._transaction_snapshots["jobs"]
                self._job_runs = self._transaction_snapshots["job_runs"]

            self._transaction_snapshots = None
            self._transaction_active = False

    # Enhanced utility methods

    def get_statistics(self) -> dict[str, Any]:
        """Get detailed statistics about stored data."""
        with self._lock:
            jobs = list(self._jobs.values())
            job_runs = list(self._job_runs.values())

            # Calculate status distribution
            status_counts = {}
            for job_run in job_runs:
                status_counts[job_run.status] = status_counts.get(job_run.status, 0) + 1

            return {
                "backend": "InMemory",
                "total_jobs": len(jobs),
                "total_job_runs": len(job_runs),
                "status_distribution": status_counts,
                "memory_usage_mb": self._estimate_memory_usage(),
                "transaction_active": self._transaction_active,
            }

    def _estimate_memory_usage(self) -> float:
        """Estimate memory usage in MB (rough approximation)."""
        import sys

        total_size = (
            sys.getsizeof(self._jobs)
            + sys.getsizeof(self._job_runs)
            + sum(sys.getsizeof(obj) for obj in self._jobs.values())
            + sum(sys.getsizeof(obj) for obj in self._job_runs.values())
        )

        if self._transaction_snapshots:
            total_size += sys.getsizeof(self._transaction_snapshots) + sum(
                sys.getsizeof(obj) for obj in self._transaction_snapshots.values()
            )

        return total_size / (1024 * 1024)  # Convert to MB

    def clear_all_data(self) -> None:
        """Clear all stored data.

        WARNING: This permanently deletes all jobs and job runs.
        Should only be used for testing or cleanup operations.
        """
        with self._lock:
            if self._transaction_active:
                raise PersistenceError("Cannot clear data during active transaction")

            self._jobs.clear()
            self._job_runs.clear()

    def export_data(self) -> dict[str, Any]:
        """Export all data for backup or migration.

        Note: callables on Step objects cannot be serialized and will be lost.

        Returns:
            Dictionary containing job names and run IDs (shallow export).
        """
        with self._lock:
            return {
                "job_names": list(self._jobs.keys()),
                "job_run_ids": list(self._job_runs.keys()),
                "exported_at": datetime.utcnow().isoformat(),
            }

    def import_data(self, data: dict[str, Any]) -> None:
        """Import data from backup or migration.

        Args:
            data: Data dictionary from export_data().

        Raises:
            PersistenceError: If data format is invalid.
        """
        raise PersistenceError(
            "InMemoryPersistence does not support import_data. "
            "Use a file-based backend for data migration."
        )
