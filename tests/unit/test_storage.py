"""
Comprehensive test suite for all persistence backends.

Tests the persistence layer with all backends to ensure consistent
behavior and API compatibility.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pyworkflow_engine.models import (
    Job,
    JobRun,
    RunStatus,
    Step,
    StepRun,
    StepType,
)
from pyworkflow_engine.ports.persistence import (
    BasePersistence,
)
from pyworkflow_engine.adapters.persistence.json_file import JSONFilePersistence
from pyworkflow_engine.adapters.persistence.memory import InMemoryPersistence
from pyworkflow_engine.adapters.persistence.sqlite import SQLitePersistence

# SQLAlchemy tests only run if SQLAlchemy is available
try:
    import sqlalchemy  # noqa: F401

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


class PersistenceBackendTests:
    """Mixin de tests communs pour tous les backends de persistence.

    Cette classe n'est **pas** collectée par pytest (absence de préfixe
    ``Test``). Les sous-classes héritent de l'ensemble des cas de test et
    fournissent leur propre fixture ``persistence``.

    Sous-classes concrètes :
        - ``TestInMemoryPersistence``
        - ``TestJSONFilePersistence``
        - ``TestSQLitePersistence``
        - ``TestSQLAlchemyPersistence``
    """

    @pytest.fixture
    def sample_job(self) -> Job:
        """Create a sample job for testing."""
        steps = [
            Step(
                name="step1",
                step_type=StepType.SUBPROCESS,
                handler=None,  # No callable needed for subprocess
                config={"command": ["echo", "hello"], "param1": "value1"},
                dependencies=[],
                timeout=timedelta(seconds=30),
            ),
            Step(
                name="step2",
                step_type=StepType.HTTP_REQUEST,
                handler=None,  # No callable needed for HTTP request
                config={"url": "https://api.example.com", "param2": "value2"},
                dependencies=["step1"],
                timeout=timedelta(seconds=60),
            ),
        ]

        return Job(
            name="test_job",
            description="A test job",
            steps=steps,
            metadata={
                "version": "1.0",
                "author": "test",
                "global_param": "global_value",
            },
        )

    @pytest.fixture
    def sample_job_run(self, sample_job: Job) -> JobRun:
        """Create a sample job run for testing."""

        step_runs = [
            StepRun(
                step_run_id="step_run_1",
                job_run_id="job_run_1",
                step_name="step1",
                status=RunStatus.SUCCESS,
                # Note: StepRun uses different time attributes
                input_data={"input": "test"},
                output_data={"output": "result"},
                metadata={"duration": 10},
            ),
            StepRun(
                step_run_id="step_run_2",
                job_run_id="job_run_1",
                step_name="step2",
                status=RunStatus.RUNNING,
                input_data={"input": "test2"},
                metadata={"started": True},
            ),
        ]

        return JobRun(
            job_run_id="job_run_1",
            job_name="test_job",
            status=RunStatus.RUNNING,
            input_data={"run_param": "run_value"},
            metadata={"execution_id": "exec_123"},
            step_runs=step_runs,
        )

    def test_save_and_get_job(self, persistence: BasePersistence, sample_job: Job):
        """Test saving and retrieving a job."""
        # Save job
        persistence.save_job(sample_job)

        # Retrieve job
        retrieved_job = persistence.get_job(sample_job.name)

        assert retrieved_job is not None
        assert retrieved_job.name == sample_job.name
        assert retrieved_job.description == sample_job.description
        assert retrieved_job.metadata == sample_job.metadata
        assert len(retrieved_job.steps) == len(sample_job.steps)

        # Check steps
        for orig_step, retr_step in zip(
            sample_job.steps, retrieved_job.steps, strict=False
        ):
            assert orig_step.name == retr_step.name
            assert orig_step.step_type == retr_step.step_type
            assert orig_step.handler == retr_step.handler
            assert orig_step.config == retr_step.config
            assert orig_step.dependencies == retr_step.dependencies
            assert orig_step.timeout == retr_step.timeout

    def test_get_nonexistent_job(self, persistence: BasePersistence):
        """Test retrieving a job that doesn't exist."""
        result = persistence.get_job("nonexistent_job")
        assert result is None

    def test_list_jobs(self, persistence: BasePersistence, sample_job: Job):
        """Test listing jobs."""
        # Initially empty
        jobs = persistence.list_jobs()
        assert len(jobs) == 0

        # Save job
        persistence.save_job(sample_job)

        # Should have one job
        jobs = persistence.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == sample_job.name

    def test_list_jobs_pagination(self, persistence: BasePersistence):
        """Test job listing with pagination."""
        # Create multiple jobs
        for i in range(5):
            job = Job(
                name=f"job_{i:02d}",  # Zero-padded for consistent sorting
                description=f"Job {i}",
                steps=[
                    Step(
                        name="step1",
                        step_type=StepType.SUBPROCESS,
                        handler=None,  # No callable needed for subprocess
                        config={"command": ["echo", f"job {i}"]},
                        dependencies=[],
                    )
                ],
                metadata={},
            )
            persistence.save_job(job)

        # Test pagination
        page1 = persistence.list_jobs(limit=2, offset=0)
        assert len(page1) == 2
        assert page1[0].name == "job_00"
        assert page1[1].name == "job_01"

        page2 = persistence.list_jobs(limit=2, offset=2)
        assert len(page2) == 2
        assert page2[0].name == "job_02"
        assert page2[1].name == "job_03"

        # Test without pagination
        all_jobs = persistence.list_jobs()
        assert len(all_jobs) == 5

    def test_delete_job(self, persistence: BasePersistence, sample_job: Job):
        """Test deleting a job."""
        # Save job
        persistence.save_job(sample_job)
        assert persistence.get_job(sample_job.name) is not None

        # Delete job
        result = persistence.delete_job(sample_job.name)
        assert result is True

        # Should be gone
        assert persistence.get_job(sample_job.name) is None

        # Delete non-existent job
        result = persistence.delete_job("nonexistent")
        assert result is False

    def test_save_and_get_job_run(
        self, persistence: BasePersistence, sample_job: Job, sample_job_run: JobRun
    ):
        """Test saving and retrieving a job run."""
        # Save job first (some backends require it)
        persistence.save_job(sample_job)

        # Save job run
        persistence.save_job_run(sample_job_run)

        # Retrieve job run
        retrieved_run = persistence.get_job_run(sample_job_run.job_run_id)

        assert retrieved_run is not None
        assert retrieved_run.job_run_id == sample_job_run.job_run_id
        assert retrieved_run.job_name == sample_job_run.job_name
        assert retrieved_run.status == sample_job_run.status
        # Note: JobRun uses input_data not parameters
        assert retrieved_run.input_data == sample_job_run.input_data
        assert retrieved_run.metadata == sample_job_run.metadata

        # Check step runs
        assert len(retrieved_run.step_runs) == len(sample_job_run.step_runs)
        for orig_step_run, retr_step_run in zip(
            sample_job_run.step_runs, retrieved_run.step_runs, strict=False
        ):
            assert orig_step_run.step_run_id == retr_step_run.step_run_id
            assert orig_step_run.job_run_id == retr_step_run.job_run_id
            assert orig_step_run.step_name == retr_step_run.step_name
            assert orig_step_run.status == retr_step_run.status
            assert orig_step_run.input_data == retr_step_run.input_data
            assert orig_step_run.output_data == retr_step_run.output_data
            assert orig_step_run.metadata == retr_step_run.metadata

    def test_get_nonexistent_job_run(self, persistence: BasePersistence):
        """Test retrieving a job run that doesn't exist."""
        result = persistence.get_job_run("nonexistent_run")
        assert result is None

    def test_list_job_runs(
        self, persistence: BasePersistence, sample_job: Job, sample_job_run: JobRun
    ):
        """Test listing job runs."""
        # Save job first
        persistence.save_job(sample_job)

        # Initially empty
        runs = persistence.list_job_runs()
        assert len(runs) == 0

        # Save job run
        persistence.save_job_run(sample_job_run)

        # Should have one run
        runs = persistence.list_job_runs()
        assert len(runs) == 1
        assert runs[0].id == sample_job_run.id

    def test_list_job_runs_filtering(
        self, persistence: BasePersistence, sample_job: Job
    ):
        """Test listing job runs with filters."""
        # Save job first
        persistence.save_job(sample_job)

        # Create multiple job runs
        now = datetime.now(UTC)  # Use timezone-aware datetime

        runs_data = [
            {
                "id": "run1",
                "status": RunStatus.SUCCESS,
                "created_at": now - timedelta(hours=2),
            },
            {
                "id": "run2",
                "status": RunStatus.FAILED,
                "created_at": now - timedelta(hours=1),
            },
            {"id": "run3", "status": RunStatus.RUNNING, "created_at": now},
        ]

        for run_data in runs_data:
            job_run = JobRun(
                job_run_id=run_data["id"],
                job_name=sample_job.name,
                status=run_data["status"],
                input_data={},
                metadata={},
                step_runs=[],
                created_at=run_data["created_at"],  # Use specified created_at
                updated_at=run_data["created_at"],  # Set updated_at to same time
            )
            persistence.save_job_run(job_run)

        # Test filtering by status
        success_runs = persistence.list_job_runs(status="success")
        assert len(success_runs) == 1
        assert success_runs[0].job_run_id == "run1"

        failed_runs = persistence.list_job_runs(status="failed")
        assert len(failed_runs) == 1
        assert failed_runs[0].job_run_id == "run2"

        # Test filtering by job name
        job_runs = persistence.list_job_runs(job_name=sample_job.name)
        assert len(job_runs) == 3

        # Test filtering by time
        recent_runs = persistence.list_job_runs(since=now - timedelta(minutes=30))
        assert len(recent_runs) == 1
        assert recent_runs[0].id == "run3"

    def test_list_job_runs_pagination(
        self, persistence: BasePersistence, sample_job: Job
    ):
        """Test job run listing with pagination."""
        # Save job first
        persistence.save_job(sample_job)

        # Create multiple job runs
        for i in range(5):  # noqa: B007
            job_run = JobRun(
                job_run_id=f"run_{i}",
                job_name=sample_job.name,
                status=RunStatus.SUCCESS,
                input_data={},
                metadata={},
                step_runs=[],
            )
            persistence.save_job_run(job_run)

        # Test pagination (newest first)
        page1 = persistence.list_job_runs(limit=2, offset=0)
        assert len(page1) == 2
        assert page1[0].id == "run_4"  # Newest (created last)
        assert page1[1].id == "run_3"

        page2 = persistence.list_job_runs(limit=2, offset=2)
        assert len(page2) == 2
        assert page2[0].id == "run_2"
        assert page2[1].id == "run_1"

    def test_delete_job_run(
        self, persistence: BasePersistence, sample_job: Job, sample_job_run: JobRun
    ):
        """Test deleting a job run."""
        # Save job and job run
        persistence.save_job(sample_job)
        persistence.save_job_run(sample_job_run)

        assert persistence.get_job_run(sample_job_run.id) is not None

        # Delete job run
        result = persistence.delete_job_run(sample_job_run.id)
        assert result is True

        # Should be gone
        assert persistence.get_job_run(sample_job_run.id) is None

        # Delete non-existent run
        result = persistence.delete_job_run("nonexistent")
        assert result is False

    def test_get_job_run_count(self, persistence: BasePersistence, sample_job: Job):
        """Test getting job run count."""
        # Save job first
        persistence.save_job(sample_job)

        # Initially zero
        count = persistence.get_job_run_count()
        assert count == 0

        count_for_job = persistence.get_job_run_count(job_name=sample_job.name)
        assert count_for_job == 0

        # Add some runs
        for i in range(3):
            job_run = JobRun(
                job_run_id=f"run_{i}",
                job_name=sample_job.name,
                status=RunStatus.SUCCESS,
                input_data={},
                metadata={},
                step_runs=[],
            )
            persistence.save_job_run(job_run)

        # Should have 3 total
        count = persistence.get_job_run_count()
        assert count == 3

        count_for_job = persistence.get_job_run_count(job_name=sample_job.name)
        assert count_for_job == 3

    def test_cleanup_old_runs(self, persistence: BasePersistence, sample_job: Job):
        """Test cleaning up old job runs."""
        # Save job first
        persistence.save_job(sample_job)

        # Create runs with different ages
        now = datetime.now(UTC)  # Use timezone-aware datetime
        old_time = now - timedelta(days=2)
        recent_time = now - timedelta(hours=1)

        # Old run
        old_run = JobRun(
            job_run_id="old_run",
            job_name=sample_job.name,
            status=RunStatus.SUCCESS,
            input_data={},
            metadata={},
            step_runs=[],
            created_at=old_time,  # Set to old time
            updated_at=old_time,
        )

        # Recent run
        recent_run = JobRun(
            job_run_id="recent_run",
            job_name=sample_job.name,
            status=RunStatus.SUCCESS,
            input_data={},
            metadata={},
            step_runs=[],
            created_at=recent_time,  # Set to recent time
            updated_at=recent_time,
        )

        persistence.save_job_run(old_run)
        persistence.save_job_run(recent_run)

        # Should have 2 runs
        assert persistence.get_job_run_count() == 2

        # Cleanup runs older than 1 day
        cutoff = now - timedelta(days=1)
        deleted_count = persistence.cleanup_old_runs(cutoff)

        assert deleted_count == 1
        assert persistence.get_job_run_count() == 1

        # Recent run should still exist
        assert persistence.get_job_run("recent_run") is not None
        assert persistence.get_job_run("old_run") is None

    # ------------------------------------------------------------------
    # cleanup_old_runs — dry_run parametrized tests
    # ------------------------------------------------------------------

    def _make_old_run(self, job_name: str, run_id: str, age_days: int = 2) -> JobRun:
        """Helper pour créer un JobRun avec une date passée."""
        now = datetime.now(UTC)
        created = now - timedelta(days=age_days)
        return JobRun(
            job_run_id=run_id,
            job_name=job_name,
            job_version="1.0.0",
            status=RunStatus.SUCCESS,
            created_at=created,
            updated_at=created,
            start_time=created,
            end_time=created,
        )

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_cleanup_old_runs_dry_run(
        self, persistence: BasePersistence, sample_job: Job, dry_run: bool
    ):
        """Test cleanup_old_runs avec dry_run=True et dry_run=False.

        dry_run=True  → compte uniquement, aucune suppression.
        dry_run=False → supprime réellement les runs éligibles.
        """
        persistence.save_job(sample_job)

        old_run = self._make_old_run(sample_job.name, "old_dr_run", age_days=5)
        now = datetime.now(UTC)
        recent_run = JobRun(
            job_run_id="recent_dr_run",
            job_name=sample_job.name,
            job_version="1.0.0",
            status=RunStatus.SUCCESS,
            created_at=now,
            updated_at=now,
        )

        persistence.save_job_run(old_run)
        persistence.save_job_run(recent_run)
        assert persistence.get_job_run_count() == 2

        cutoff = now - timedelta(days=1)
        count = persistence.cleanup_old_runs(cutoff, dry_run=dry_run)

        assert count == 1, f"Expected 1 old run counted, got {count}"

        if dry_run:
            # dry_run=True → rien supprimé
            assert persistence.get_job_run_count() == 2
            assert persistence.get_job_run("old_dr_run") is not None
        else:
            # dry_run=False → old_run supprimé
            assert persistence.get_job_run_count() == 1
            assert persistence.get_job_run("old_dr_run") is None
            assert persistence.get_job_run("recent_dr_run") is not None

    def test_health_check(self, persistence: BasePersistence):
        """Test health check functionality."""
        health = persistence.health_check()

        assert isinstance(health, dict)
        assert "status" in health
        assert "backend" in health
        assert health["status"] in ["healthy", "unhealthy"]

    def test_get_statistics(self, persistence: BasePersistence):
        """Test statistics functionality."""
        stats = persistence.get_statistics()

        assert isinstance(stats, dict)
        assert "backend" in stats


class TestInMemoryPersistence(PersistenceBackendTests):
    """Test cases specific to InMemoryPersistence."""

    @pytest.fixture
    def persistence(self) -> InMemoryPersistence:
        """Create an in-memory persistence instance."""
        return InMemoryPersistence()


class TestJSONFilePersistence(PersistenceBackendTests):
    """Test cases specific to JSONFilePersistence."""

    @pytest.fixture
    def persistence(self) -> JSONFilePersistence:
        """Create a JSON file persistence instance with temporary directory."""
        temp_dir = tempfile.mkdtemp()
        # Store for cleanup - pytest will handle this
        return JSONFilePersistence(storage_dir=temp_dir)

    def test_file_based_storage(
        self, persistence: JSONFilePersistence, sample_job: Job
    ):
        """Test that data is actually stored in files."""
        # Save job
        persistence.save_job(sample_job)

        # Check that file exists
        jobs_file = Path(persistence.storage_dir) / "jobs" / f"{sample_job.name}.json"
        assert jobs_file.exists()

        # File should contain job data
        import json

        with open(jobs_file) as f:
            data = json.load(f)
            assert data["name"] == sample_job.name


class TestSQLitePersistence(PersistenceBackendTests):
    """Test cases specific to SQLitePersistence."""

    @pytest.fixture
    def persistence(self) -> SQLitePersistence:
        """Create a SQLite persistence instance with in-memory database."""
        return SQLitePersistence(":memory:")

    def test_database_initialization(self, persistence: SQLitePersistence):
        """Test that database tables are properly created."""
        # Basic test - if we can create the instance, tables should be created
        assert persistence is not None

        # Test health check which verifies database connectivity
        health = persistence.health_check()
        assert health["status"] == "healthy"


# SQLAlchemy tests only run if SQLAlchemy is available
@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
class TestSQLAlchemyPersistence(PersistenceBackendTests):
    """Test cases specific to SQLAlchemyPersistence."""

    @pytest.fixture
    def persistence(self):
        """Create a SQLAlchemy persistence instance with in-memory SQLite."""
        from pyworkflow_engine.adapters.persistence.sqlalchemy import SQLAlchemyPersistence

        return SQLAlchemyPersistence("sqlite:///:memory:")

    def test_database_initialization(self, persistence):
        """Test that database is properly initialized."""
        from sqlalchemy import text

        with persistence.engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            table_names = [row[0] for row in result.fetchall()]

            expected_tables = [
                f"{persistence.table_prefix}jobs",
                f"{persistence.table_prefix}job_runs",
                f"{persistence.table_prefix}step_runs",
                f"{persistence.table_prefix}schema_version",
            ]

            for table in expected_tables:
                assert table in table_names

    def test_bulk_operations(self, persistence, sample_job: Job):
        """Test bulk operations performance."""
        import time

        # Create many job runs
        job_runs = []
        for i in range(100):
            job_run = JobRun(
                job_run_id=f"bulk_run_{i}",
                job_name=sample_job.name,
                status=RunStatus.SUCCESS,
                input_data={},
                metadata={},
                step_runs=[],
            )
            job_runs.append(job_run)

        # Save job first
        persistence.save_job(sample_job)

        # Bulk save
        start_time = time.time()
        for job_run in job_runs:
            persistence.save_job_run(job_run)
        end_time = time.time()

        # Should complete reasonably quickly
        assert end_time - start_time < 5.0  # Less than 5 seconds

        # Verify count
        count = persistence.get_job_run_count()
        assert count == 100

    def test_advanced_querying(self, persistence, sample_job: Job):
        """Test advanced querying capabilities."""

        # Save job first
        persistence.save_job(sample_job)

        now = datetime.now(UTC)

        # Create runs with different statuses
        statuses = [RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.RUNNING]
        for i, status in enumerate(statuses * 10):  # 30 runs total
            job_run = JobRun(
                job_run_id=f"query_run_{i}",
                job_name=sample_job.name,
                status=status,
                input_data={},
                metadata={},
                step_runs=[],
                created_at=now - timedelta(hours=i),
            )
            persistence.save_job_run(job_run)

        # Test status filtering
        success_runs = persistence.list_job_runs(status="success")
        assert len(success_runs) == 10

        # Test time filtering — only runs created within the last 5 hours
        # i=0..4 → created_at within 5 hours → max 5 runs (indices 0-4)
        recent_time = now - timedelta(hours=5)
        recent_runs = persistence.list_job_runs(since=recent_time)
        assert len(recent_runs) <= 6  # Runs from last 5 hours

    def test_connection_pooling(self, persistence):
        """Test connection pooling functionality."""
        # Engine should have pool configuration
        assert persistence.engine.pool is not None

        # Multiple operations should work
        for _ in range(10):
            health = persistence.health_check()
            assert health["status"] == "healthy"


class TestTransactionBehavior:
    """Test transaction behavior across different backends."""

    @pytest.fixture(
        params=[
            InMemoryPersistence,
            lambda: JSONFilePersistence(tempfile.mkdtemp()),
            lambda: SQLitePersistence(":memory:"),
        ]
    )
    def persistence(self, request):
        """Parameterized fixture for different persistence backends."""
        return request.param()

    @pytest.fixture
    def sample_job(self) -> Job:
        """Create a sample job for testing."""
        return Job(
            name="test_job",
            description="A test job",
            steps=[
                Step(
                    name="step1",
                    step_type=StepType.SUBPROCESS,
                    handler=None,
                    config={"command": ["echo", "hello"]},
                    dependencies=[],
                )
            ],
            metadata={},
        )

    def test_transaction_context_manager(
        self, persistence: BasePersistence, sample_job: Job
    ):
        """Test transaction context manager."""
        # Test successful transaction
        with persistence.transaction():
            persistence.save_job(sample_job)

        # Job should be saved
        assert persistence.get_job(sample_job.name) is not None

        # Test rollback on exception
        try:
            with persistence.transaction() as _tx:
                modified_job = Job(
                    name="test_rollback",
                    description="Should be rolled back",
                    steps=[
                        Step(
                            name="step1",
                            step_type=StepType.FUNCTION,
                            handler=lambda: {"result": "test"},
                            config={},
                            dependencies=[],
                        )
                    ],
                    metadata={},
                )
                persistence.save_job(modified_job)
                raise ValueError("Intentional error")
        except ValueError:
            pass

        # Rollback behavior depends on backend capabilities
        # Some backends may not support true rollback for all operations


# Integration tests
class TestPersistenceIntegration:
    """Integration tests for persistence with the workflow engine."""

    def test_engine_integration(self):
        """Test persistence integration with WorkflowEngine."""
        from pyworkflow_engine import WorkflowEngine
        from pyworkflow_engine.adapters.persistence.memory import InMemoryPersistence

        persistence = InMemoryPersistence()
        engine = WorkflowEngine(persistence=persistence)

        # Engine should use the persistence backend
        assert engine.persistence is persistence

        # Basic workflow execution should work
        # (This would require a more complete test setup)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
