"""
Integration tests — round-trip storage for all backends.

Each test saves a model, retrieves it, and asserts field equality.
This validates that serialization ↔ deserialization is fully symmetric
across InMemory, JSONFile, and SQLite backends.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pyworkflow_engine.models import (
    Job,
    JobRun,
    RunStatus,
    Step,
    StepRun,
    StepType,
)
from pyworkflow_engine.adapters.storage.json_file import JSONFileStorage
from pyworkflow_engine.adapters.storage.memory import InMemoryStorage
from pyworkflow_engine.adapters.storage.sqlite import SQLiteStorage

# ---------------------------------------------------------------------------
# SQLAlchemy — optional
# ---------------------------------------------------------------------------
try:
    from pyworkflow_engine.adapters.storage.sqlalchemy import (
        SQLAlchemyStorage,
    )  # noqa: F401

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_job(name: str = "test_job") -> Job:
    """Create a minimal but realistic Job for testing."""
    return Job(
        name=name,
        description="Integration test job",
        steps=[
            Step(
                name="extract",
                step_type=StepType.SUBPROCESS,
                handler=None,
                config={"command": ["echo", "hello"]},
                dependencies=[],
                timeout=timedelta(seconds=30),
                retry_count=2,
            ),
            Step(
                name="transform",
                step_type=StepType.HTTP_REQUEST,
                handler=None,
                config={"url": "https://api.example.com"},
                dependencies=["extract"],
                timeout=timedelta(seconds=60),
            ),
        ],
        tags=["integration", "test"],
        metadata={"owner": "test_suite"},
        version="2.0.0",
    )


def _make_job_run(job: Job) -> JobRun:
    """Create a completed JobRun with step runs for round-trip testing."""
    now = datetime.now(UTC)
    job_run = JobRun(
        job_name=job.name,
        status=RunStatus.SUCCESS,
        input_data={"key": "value"},
        output_data={"result": 42},
        context={"extract": {"data": [1, 2, 3]}},
        error=None,
        start_time=now - timedelta(seconds=5),
        end_time=now,
        duration_ms=5000,
        triggered_by="pytest",
        priority=10,
        metadata={"run_env": "ci"},
    )

    step_run = StepRun(
        step_name="extract",
        job_run_id=job_run.job_run_id,
        status=RunStatus.SUCCESS,
        input_data={},
        output_data={"data": [1, 2, 3]},
        start_time=now - timedelta(seconds=5),
        end_time=now - timedelta(seconds=2),
        duration_ms=3000,
        retry_count=1,
    )
    job_run.step_runs.append(step_run)
    return job_run


# ---------------------------------------------------------------------------
# Backend factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_backend():
    return InMemoryStorage()


@pytest.fixture()
def json_backend(tmp_path):
    return JSONFileStorage(str(tmp_path / "workflow_data"))


@pytest.fixture()
def sqlite_backend():
    return SQLiteStorage(":memory:")


@pytest.fixture(
    params=["memory", "json_file", "sqlite"],
)
def backend(request, memory_backend, json_backend, sqlite_backend):
    """Parametrized fixture that yields all three backends in turn."""
    return {
        "memory": memory_backend,
        "json_file": json_backend,
        "sqlite": sqlite_backend,
    }[request.param]


# ---------------------------------------------------------------------------
# Job round-trip tests
# ---------------------------------------------------------------------------


class TestJobRoundTrip:
    """Round-trip: save_job → get_job."""

    def test_basic_fields(self, backend):
        job = _make_job()
        backend.save_job(job)

        retrieved = backend.get_job(job.name)
        assert retrieved is not None
        assert retrieved.name == job.name
        assert retrieved.description == job.description
        assert retrieved.version == job.version
        assert retrieved.enabled == job.enabled
        assert retrieved.tags == job.tags
        assert retrieved.metadata == job.metadata

    def test_steps_count_preserved(self, backend):
        job = _make_job()
        backend.save_job(job)

        retrieved = backend.get_job(job.name)
        assert len(retrieved.steps) == len(job.steps)

    def test_step_fields_preserved(self, backend):
        job = _make_job()
        backend.save_job(job)

        retrieved = backend.get_job(job.name)
        for original, restored in zip(job.steps, retrieved.steps, strict=False):
            assert restored.name == original.name
            assert restored.step_type == original.step_type
            assert restored.config == original.config
            assert restored.dependencies == original.dependencies
            assert restored.retry_count == original.retry_count
            # callable is intentionally None after deserialization
            assert restored.handler is None

    def test_step_timeout_preserved(self, backend):
        job = _make_job()
        backend.save_job(job)

        retrieved = backend.get_job(job.name)
        extract = next(s for s in retrieved.steps if s.name == "extract")
        assert extract.timeout == timedelta(seconds=30)

    def test_overwrite_job(self, backend):
        job = _make_job()
        backend.save_job(job)

        # Overwrite with a different description
        updated = job.model_copy(update={"description": "Updated description"})
        backend.save_job(updated)

        retrieved = backend.get_job(job.name)
        assert retrieved.description == "Updated description"

    def test_list_jobs(self, backend):
        job1 = _make_job("job_alpha")
        job2 = _make_job("job_beta")
        backend.save_job(job1)
        backend.save_job(job2)

        jobs = backend.list_jobs()
        names = {j.name for j in jobs}
        assert "job_alpha" in names
        assert "job_beta" in names

    def test_delete_job(self, backend):
        job = _make_job()
        backend.save_job(job)
        backend.delete_job(job.name)

        retrieved = backend.get_job(job.name)
        assert retrieved is None

    def test_get_nonexistent_job_returns_none(self, backend):
        assert backend.get_job("does_not_exist") is None


# ---------------------------------------------------------------------------
# JobRun round-trip tests
# ---------------------------------------------------------------------------


class TestJobRunRoundTrip:
    """Round-trip: save_job_run → get_job_run."""

    def test_basic_fields(self, backend):
        job = _make_job()
        backend.save_job(job)
        job_run = _make_job_run(job)
        backend.save_job_run(job_run)

        retrieved = backend.get_job_run(job_run.job_run_id)
        assert retrieved is not None
        assert retrieved.job_run_id == job_run.job_run_id
        assert retrieved.job_name == job_run.job_name
        assert retrieved.status == job_run.status
        assert retrieved.input_data == job_run.input_data
        assert retrieved.output_data == job_run.output_data
        assert retrieved.triggered_by == job_run.triggered_by

    def test_step_runs_preserved(self, backend):
        job = _make_job()
        backend.save_job(job)
        job_run = _make_job_run(job)
        backend.save_job_run(job_run)

        retrieved = backend.get_job_run(job_run.job_run_id)
        assert len(retrieved.step_runs) == len(job_run.step_runs)

    def test_step_run_fields_preserved(self, backend):
        job = _make_job()
        backend.save_job(job)
        job_run = _make_job_run(job)
        backend.save_job_run(job_run)

        retrieved = backend.get_job_run(job_run.job_run_id)
        original_sr = job_run.step_runs[0]
        restored_sr = retrieved.step_runs[0]

        assert restored_sr.step_run_id == original_sr.step_run_id
        assert restored_sr.step_name == original_sr.step_name
        assert restored_sr.status == original_sr.status
        assert restored_sr.output_data == original_sr.output_data
        assert restored_sr.retry_count == original_sr.retry_count

    def test_update_job_run_status(self, backend):
        job = _make_job()
        backend.save_job(job)
        job_run = _make_job_run(job)
        job_run.status = RunStatus.RUNNING
        backend.save_job_run(job_run)

        job_run.complete_failure("something went wrong")
        backend.update_job_run(job_run)

        retrieved = backend.get_job_run(job_run.job_run_id)
        assert retrieved.status == RunStatus.FAILED
        assert retrieved.error == "something went wrong"

    def test_list_job_runs_by_job_name(self, backend):
        job = _make_job()
        backend.save_job(job)

        run1 = _make_job_run(job)
        run2 = _make_job_run(job)
        backend.save_job_run(run1)
        backend.save_job_run(run2)

        runs = backend.list_job_runs(job_name=job.name)
        assert len(runs) >= 2

    def test_list_job_runs_by_status(self, backend):
        job = _make_job()
        backend.save_job(job)

        run = _make_job_run(job)  # status = SUCCESS
        backend.save_job_run(run)

        success_runs = backend.list_job_runs(status="success")
        assert any(r.job_run_id == run.job_run_id for r in success_runs)

    def test_delete_job_run(self, backend):
        job = _make_job()
        backend.save_job(job)
        job_run = _make_job_run(job)
        backend.save_job_run(job_run)
        backend.delete_job_run(job_run.job_run_id)

        retrieved = backend.get_job_run(job_run.job_run_id)
        assert retrieved is None

    def test_get_nonexistent_run_returns_none(self, backend):
        assert backend.get_job_run("does_not_exist") is None


# ---------------------------------------------------------------------------
# Full lifecycle test
# ---------------------------------------------------------------------------


def test_full_lifecycle(backend):
    """End-to-end: define job → run → persist → retrieve → assert."""
    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.models.enums import StepType

    def step_fn():
        return {"ok": True}

    runnable_job = Job(
        name="lifecycle_job",
        description="Lifecycle integration test",
        steps=[
            Step(
                name="step_a",
                step_type=StepType.FUNCTION,
                handler=step_fn,
            )
        ],
    )

    engine = WorkflowEngine(storage=backend)

    # SQLite enforces a FK constraint: job must exist before saving a job_run.
    backend.save_job(runnable_job)

    run = engine.run_with_storage(runnable_job)

    # Retrieve persisted run
    retrieved = backend.get_job_run(run.job_run_id)
    assert retrieved is not None
    assert retrieved.job_name == "lifecycle_job"
    assert retrieved.status == run.status
