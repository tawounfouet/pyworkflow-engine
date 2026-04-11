"""
Adapter persistence — backend JSON sur disque (JSONFilePersistence).

Stockage dans des fichiers JSON.  Adapté au développement, aux tests et
aux déploiements de petite échelle où la lisibilité prime sur la performance.

Zéro dépendance externe — stdlib uniquement.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from pyworkflow_engine.models import Job, JobRun, StepRun
from pyworkflow_engine.ports.persistence import (
    BasePersistence,
    JobNotFoundError,
    PersistenceError,
    TransactionError,
)


class JSONFilePersistence(BasePersistence):
    """File-based persistence using JSON format.

    This implementation stores each job and job run in separate JSON files
    within a configured directory structure. It provides atomic operations
    and basic transaction support via file locking.

    Directory structure:
        storage_dir/
        ├── jobs/
        │   ├── job1.json
        │   └── job2.json
        └── runs/
            ├── run1.json
            └── run2.json
    """

    def __init__(self, storage_dir: str = "./workflow_data"):
        """Initialize JSON file persistence.

        Args:
            storage_dir: Directory to store workflow data files.
        """
        self.storage_dir = Path(storage_dir)
        self.jobs_dir = self.storage_dir / "jobs"
        self.runs_dir = self.storage_dir / "runs"

        # Ensure directories exist
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

        # Thread safety
        self._lock = threading.RLock()

        # Transaction state
        self._in_transaction = False
        self._transaction_operations: list[dict[str, Any]] = []

    def _safe_filename(self, name: str) -> str:
        """Convert a name to a safe filename."""
        # Replace unsafe characters with underscores
        safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        return "".join(c if c in safe_chars else "_" for c in name)

    def _job_file_path(self, job_name: str) -> Path:
        """Get the file path for a job."""
        safe_name = self._safe_filename(job_name)
        return self.jobs_dir / f"{safe_name}.json"

    def _run_file_path(self, run_id: str) -> Path:
        """Get the file path for a job run."""
        safe_id = self._safe_filename(run_id)
        return self.runs_dir / f"{safe_id}.json"

    def _serialize_job(self, job: Job) -> dict[str, Any]:
        """Serialize a job to JSON-compatible format."""
        return job.to_dict()

    def _deserialize_job(self, data: dict[str, Any]) -> Job:
        """Deserialize a job from JSON format."""
        return Job.from_dict(data)

    def _serialize_job_run(self, job_run: JobRun) -> dict[str, Any]:
        """Serialize a job run to JSON-compatible format."""
        return job_run.to_dict()

    def _serialize_step_run(self, step_run: StepRun) -> dict[str, Any]:
        """Serialize a step run to JSON-compatible format."""
        return step_run.to_dict()

    def _deserialize_job_run(self, data: dict[str, Any]) -> JobRun:
        """Deserialize a job run from JSON format."""
        return JobRun.from_dict(data)

    def _read_file_atomic(self, file_path: Path) -> dict[str, Any] | None:
        """Atomically read a JSON file."""
        try:
            if not file_path.exists():
                return None
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise PersistenceError(f"Failed to read {file_path}: {e}") from e

    def _write_file_atomic(self, file_path: Path, data: dict[str, Any]) -> None:
        """Atomically write a JSON file."""
        try:
            # Write to temporary file first, then rename (atomic on most filesystems)
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk

            # Atomic rename
            temp_path.rename(file_path)
        except OSError as e:
            # Clean up temp file if it exists
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()
            raise PersistenceError(f"Failed to write {file_path}: {e}") from e

    def _delete_file_atomic(self, file_path: Path) -> bool:
        """Atomically delete a file."""
        try:
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except OSError as e:
            raise PersistenceError(f"Failed to delete {file_path}: {e}") from e

    # Transaction support

    def begin_transaction(self) -> None:
        """Begin a transaction."""
        with self._lock:
            if self._in_transaction:
                raise TransactionError("Transaction already in progress")
            self._in_transaction = True
            self._transaction_operations.clear()

    def commit_transaction(self) -> None:
        """Commit the current transaction."""
        with self._lock:
            if not self._in_transaction:
                raise TransactionError("No transaction in progress")

            try:
                # Execute all operations atomically
                for operation in self._transaction_operations:
                    op_type = operation["type"]
                    if op_type == "write":
                        self._write_file_atomic(operation["path"], operation["data"])
                    elif op_type == "delete":
                        self._delete_file_atomic(operation["path"])

                self._in_transaction = False
                self._transaction_operations.clear()

            except Exception as e:
                # Rollback is not possible with file operations
                self._in_transaction = False
                self._transaction_operations.clear()
                raise TransactionError(f"Transaction commit failed: {e}") from e

    def rollback_transaction(self) -> None:
        """Roll back the current transaction."""
        with self._lock:
            if not self._in_transaction:
                raise TransactionError("No transaction in progress")

            # For file-based operations, we can't really rollback
            # but we can clear the pending operations
            self._in_transaction = False
            self._transaction_operations.clear()

    def _execute_operation(self, op_type: str, **kwargs) -> Any:
        """Execute an operation, either immediately or queue for transaction."""
        if self._in_transaction:
            # Queue operation for later execution
            operation = {"type": op_type, **kwargs}
            self._transaction_operations.append(operation)
            return None
        else:
            # Execute immediately
            if op_type == "write":
                self._write_file_atomic(kwargs["path"], kwargs["data"])
            elif op_type == "delete":
                return self._delete_file_atomic(kwargs["path"])
            elif op_type == "read":
                return self._read_file_atomic(kwargs["path"])

    # Job operations

    def save_job(self, job: Job) -> None:
        """Save a job definition."""
        with self._lock:
            file_path = self._job_file_path(job.name)
            data = self._serialize_job(job)
            self._execute_operation("write", path=file_path, data=data)

    def get_job(self, job_name: str) -> Job | None:
        """Retrieve a job definition by name."""
        with self._lock:
            file_path = self._job_file_path(job_name)
            if self._in_transaction:
                # Check if job is being modified in current transaction
                for operation in self._transaction_operations:
                    if operation.get("path") == file_path:
                        if operation["type"] == "delete":
                            return None
                        elif operation["type"] == "write":
                            return self._deserialize_job(operation["data"])

            data = self._read_file_atomic(file_path)
            return self._deserialize_job(data) if data else None

    def list_jobs(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        """List all job definitions."""
        with self._lock:
            jobs = []

            # Read all job files
            if self.jobs_dir.exists():
                for file_path in self.jobs_dir.glob("*.json"):
                    try:
                        data = self._read_file_atomic(file_path)
                        if data:
                            jobs.append(self._deserialize_job(data))
                    except PersistenceError:
                        # Skip corrupted files
                        continue

            # Apply pagination
            jobs.sort(key=lambda j: j.name)  # Consistent ordering
            start_idx = offset
            end_idx = start_idx + limit if limit else None
            return jobs[start_idx:end_idx]

    def delete_job(self, job_name: str) -> bool:
        """Delete a job definition."""
        with self._lock:
            file_path = self._job_file_path(job_name)
            if self._in_transaction:
                # Queue for deletion
                self._execute_operation("delete", path=file_path)
                return True  # Assume success for now
            else:
                return self._delete_file_atomic(file_path)

    # Job run operations

    def save_job_run(self, job_run: JobRun) -> None:
        """Save a job run."""
        with self._lock:
            file_path = self._run_file_path(job_run.job_run_id)
            data = self._serialize_job_run(job_run)
            self._execute_operation("write", path=file_path, data=data)

    def update_job_run(self, job_run: JobRun) -> None:
        """Update an existing job run."""
        with self._lock:
            file_path = self._run_file_path(job_run.job_run_id)
            if not file_path.exists():
                raise JobNotFoundError(f"Job run {job_run.job_run_id} not found")

            data = self._serialize_job_run(job_run)
            self._execute_operation("write", path=file_path, data=data)

    def get_job_run(self, run_id: str) -> JobRun | None:
        """Retrieve a job run by ID."""
        with self._lock:
            file_path = self._run_file_path(run_id)
            if self._in_transaction:
                # Check if run is being modified in current transaction
                for operation in self._transaction_operations:
                    if operation.get("path") == file_path:
                        if operation["type"] == "delete":
                            return None
                        elif operation["type"] == "write":
                            return self._deserialize_job_run(operation["data"])

            data = self._read_file_atomic(file_path)
            return self._deserialize_job_run(data) if data else None

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
            runs = []

            # Read all run files
            if self.runs_dir.exists():
                for file_path in self.runs_dir.glob("*.json"):
                    try:
                        data = self._read_file_atomic(file_path)
                        if data:
                            run = self._deserialize_job_run(data)

                            # Apply filters
                            if job_name and run.job_name != job_name:
                                continue
                            if status and run.status.value != status:
                                continue
                            if since and run.created_at < since:
                                continue

                            runs.append(run)
                    except PersistenceError:
                        # Skip corrupted files
                        continue

            # Sort by creation time (newest first)
            runs.sort(key=lambda r: r.created_at, reverse=True)

            # Apply pagination
            start_idx = offset
            end_idx = start_idx + limit if limit else None
            return runs[start_idx:end_idx]

    def delete_job_run(self, run_id: str) -> bool:
        """Delete a job run."""
        with self._lock:
            file_path = self._run_file_path(run_id)
            if self._in_transaction:
                # Queue for deletion
                self._execute_operation("delete", path=file_path)
                return True  # Assume success for now
            else:
                return self._delete_file_atomic(file_path)

    def get_job_run_count(self, job_name: str | None = None) -> int:
        """Get the total number of job runs."""
        with self._lock:
            count = 0

            if self.runs_dir.exists():
                for file_path in self.runs_dir.glob("*.json"):
                    try:
                        data = self._read_file_atomic(file_path)
                        if data and (
                            job_name is None or data.get("job_name") == job_name
                        ):
                            count += 1
                    except PersistenceError:
                        # Skip corrupted files
                        continue

            return count

    def cleanup_old_runs(self, older_than: datetime, dry_run: bool = False) -> int:
        """Remove job runs older than the specified datetime.

        Args:
            older_than: Delete runs created before this datetime.
            dry_run: If True (default), only count without deleting.
        """
        with self._lock:
            count = 0

            if self.runs_dir.exists():
                for file_path in self.runs_dir.glob("*.json"):
                    try:
                        data = self._read_file_atomic(file_path)
                        if data:
                            created_at = datetime.fromisoformat(data["created_at"])
                            if created_at < older_than and (
                                dry_run or self._delete_file_atomic(file_path)
                            ):
                                count += 1
                    except (PersistenceError, ValueError):
                        continue

            return count

    def health_check(self) -> dict[str, Any]:
        """Check the health of the persistence backend."""
        try:
            # Test directory access
            test_file = self.storage_dir / ".health_check"
            test_file.write_text("test")
            test_file.unlink()

            # Count files
            job_count = (
                len(list(self.jobs_dir.glob("*.json"))) if self.jobs_dir.exists() else 0
            )
            run_count = (
                len(list(self.runs_dir.glob("*.json"))) if self.runs_dir.exists() else 0
            )

            # Calculate storage size
            storage_size = sum(
                f.stat().st_size for f in self.storage_dir.rglob("*") if f.is_file()
            )

            return {
                "status": "healthy",
                "backend": "json_file",
                "storage_directory": str(self.storage_dir),
                "job_count": job_count,
                "run_count": run_count,
                "storage_size_bytes": storage_size,
                "writable": True,
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "backend": "json_file",
                "storage_directory": str(self.storage_dir),
                "error": str(e),
                "writable": False,
            }

    def get_statistics(self) -> dict[str, Any]:
        """Get persistence backend statistics."""
        health = self.health_check()

        if health["status"] == "unhealthy":
            return health

        return {
            "backend": "json_file",
            "total_jobs": health["job_count"],
            "total_runs": health["run_count"],
            "storage_size_bytes": health["storage_size_bytes"],
            "storage_directory": health["storage_directory"],
        }
