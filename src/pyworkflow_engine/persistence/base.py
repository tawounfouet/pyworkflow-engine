"""
Base persistence interface for the PyWorkflow Engine.

Defines the abstract interface that all persistence backends must implement.
This provides a consistent API for storing and retrieving workflows regardless
of the underlying storage mechanism.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import Job, JobRun

from ..exceptions import WorkflowError


class PersistenceError(WorkflowError):
    """Base exception for persistence-related errors."""


class JobNotFoundError(PersistenceError):
    """Raised when a requested job/job run is not found."""


class TransactionError(PersistenceError):
    """Raised when a transaction operation fails."""


class BasePersistence(ABC):
    """Abstract base class for all persistence backends.

    This interface defines the contract that all persistence implementations
    must follow. It provides methods for storing, retrieving, and querying
    workflow data while maintaining consistency across different backends.

    Key principles:
    - Thread-safe operations
    - Atomic transactions where supported
    - Efficient querying capabilities
    - Proper error handling
    """

    @abstractmethod
    def save_job(self, job: Job) -> None:
        """Save a job definition.

        Args:
            job: The job to save.

        Raises:
            PersistenceError: If the save operation fails.
        """

    @abstractmethod
    def get_job(self, job_name: str) -> Job | None:
        """Retrieve a job definition by name.

        Args:
            job_name: Name of the job to retrieve.

        Returns:
            The job if found, None otherwise.

        Raises:
            PersistenceError: If the retrieval operation fails.
        """

    @abstractmethod
    def list_jobs(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        """List all job definitions.

        Args:
            limit: Maximum number of jobs to return.
            offset: Number of jobs to skip.

        Returns:
            List of jobs.

        Raises:
            PersistenceError: If the list operation fails.
        """

    @abstractmethod
    def delete_job(self, job_name: str) -> bool:
        """Delete a job definition.

        Args:
            job_name: Name of the job to delete.

        Returns:
            True if the job was deleted, False if it didn't exist.

        Raises:
            PersistenceError: If the delete operation fails.
        """

    @abstractmethod
    def save_job_run(self, job_run: JobRun) -> None:
        """Save a job run (execution state).

        Args:
            job_run: The job run to save.

        Raises:
            PersistenceError: If the save operation fails.
        """

    @abstractmethod
    def get_job_run(self, run_id: str) -> JobRun | None:
        """Retrieve a job run by ID.

        Args:
            run_id: ID of the job run to retrieve.

        Returns:
            The job run if found, None otherwise.

        Raises:
            PersistenceError: If the retrieval operation fails.
        """

    @abstractmethod
    def list_job_runs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[JobRun]:
        """List job runs with optional filtering.

        Args:
            job_name: Filter by job name.
            status: Filter by status.
            limit: Maximum number of runs to return.
            offset: Number of runs to skip.
            since: Only return runs created after this datetime.

        Returns:
            List of job runs matching the criteria.

        Raises:
            PersistenceError: If the list operation fails.
        """

    @abstractmethod
    def delete_job_run(self, run_id: str) -> bool:
        """Delete a job run.

        Args:
            run_id: ID of the job run to delete.

        Returns:
            True if the run was deleted, False if it didn't exist.

        Raises:
            PersistenceError: If the delete operation fails.
        """

    @abstractmethod
    def update_job_run(self, job_run: JobRun) -> None:
        """Update an existing job run.

        Args:
            job_run: The job run with updated data.

        Raises:
            JobNotFoundError: If the job run doesn't exist.
            PersistenceError: If the update operation fails.
        """

    def get_job_run_count(self, job_name: str | None = None) -> int:
        """Get count of job runs.

        Args:
            job_name: Filter by job name. If None, count all job runs.

        Returns:
            Number of job runs matching the criteria.
        """
        runs = self.list_job_runs(job_name=job_name)
        return len(runs)

    # Transaction support methods

    def begin_transaction(self) -> None:  # noqa: B027
        """Begin a transaction.

        Not all backends support transactions. For backends that don't,
        this method should be a no-op.
        """

    def commit_transaction(self) -> None:  # noqa: B027
        """Commit the current transaction.

        Raises:
            TransactionError: If there's no active transaction or commit fails.
        """

    def rollback_transaction(self) -> None:  # noqa: B027
        """Rollback the current transaction.

        Raises:
            TransactionError: If there's no active transaction or rollback fails.
        """

    # Context manager support for transactions

    def transaction(self) -> TransactionContext:
        """Get a transaction context manager.

        Returns:
            A context manager for handling transactions.

        Usage:
            with persistence.transaction():
                persistence.save_job_run(job_run)
                persistence.save_job(job)
                # Automatically commits on success, rolls back on exception
        """
        return TransactionContext(self)

    # Utility methods

    def health_check(self) -> dict[str, Any]:
        """Check the health of the persistence backend.

        Returns:
            Dictionary containing health status and metrics.
        """
        return {
            "status": "healthy",
            "backend": self.__class__.__name__,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the stored data.

        Returns:
            Dictionary containing data statistics.
        """
        try:
            jobs = self.list_jobs()
            job_runs = self.list_job_runs()

            return {
                "total_jobs": len(jobs),
                "total_job_runs": len(job_runs),
                "backend": self.__class__.__name__,
            }
        except Exception:
            return {
                "total_jobs": 0,
                "total_job_runs": 0,
                "backend": self.__class__.__name__,
                "error": "Unable to collect statistics",
            }

    def cleanup_old_runs(self, older_than: datetime, dry_run: bool = False) -> int:
        """Clean up old job runs.

        Args:
            older_than: Delete runs older than this datetime.
            dry_run: If True, only count runs that would be deleted.

        Returns:
            Number of runs deleted (or that would be deleted if dry_run=True).
        """
        old_runs = []
        for run in self.list_job_runs():
            if run.start_time and run.start_time < older_than:
                old_runs.append(run)

        if not dry_run:
            for run in old_runs:
                self.delete_job_run(run.job_run_id)

        return len(old_runs)


class TransactionContext:
    """Context manager for handling persistence transactions."""

    def __init__(self, persistence: BasePersistence):
        """Initialize transaction context.

        Args:
            persistence: The persistence backend to manage transactions for.
        """
        self.persistence = persistence
        self._in_transaction = False

    def __enter__(self) -> BasePersistence:
        """Enter transaction context."""
        self.persistence.begin_transaction()
        self._in_transaction = True
        return self.persistence

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit transaction context."""
        if self._in_transaction:
            if exc_type is None:
                # No exception, commit the transaction
                try:
                    self.persistence.commit_transaction()
                except Exception:
                    # If commit fails, try to rollback
                    import contextlib

                    with contextlib.suppress(Exception):
                        self.persistence.rollback_transaction()
                    raise
            else:
                # Exception occurred, rollback the transaction
                import contextlib

                with contextlib.suppress(Exception):
                    self.persistence.rollback_transaction()

            self._in_transaction = False
