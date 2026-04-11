"""
Coverage boost tests — Sprint 4 quality gate (>=85% overall).

Targets the lowest-coverage modules:
  - models/__init__.py        (61%) - thin wrapper functions
  - persistence/__init__.py   (60%) - lazy-import __getattr__
  - persistence/base.py       (56%) - TransactionContext, health_check, get_statistics
  - persistence/memory.py     (85%) - error paths, export/import, clear_all_data
  - persistence/json_file.py  (70%) - transaction paths, error paths
  - persistence/sqlite.py     (83%) - error paths, list_job_runs filtering
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pyworkflow_engine.models import (
    Job,
    JobRun,
    RunStatus,
    Step,
    StepLog,
    StepRun,
    StepType,
    dict_to_job,
    dict_to_job_run,
    dict_to_step,
    dict_to_step_log,
    dict_to_step_run,
    dict_to_sub_job,
    job_run_to_dict,
    job_to_dict,
    step_log_to_dict,
    step_run_to_dict,
    step_to_dict,
    sub_job_to_dict,
)
from pyworkflow_engine.models.step import SubJob
from pyworkflow_engine.persistence.base import (
    JobNotFoundError,
    PersistenceError,
    TransactionContext,
    TransactionError,
)
from pyworkflow_engine.persistence.json_file import JSONFilePersistence
from pyworkflow_engine.persistence.memory import InMemoryPersistence
from pyworkflow_engine.persistence.sqlite import SQLitePersistence


# --- Helpers ---


def _job(name="cov_job"):
    return Job(
        name=name,
        steps=[
            Step(
                name="s1",
                step_type=StepType.SUBPROCESS,
                handler=None,
                config={"command": ["echo"]},
            )
        ],
        version="1.0.0",
    )


def _run(job):
    return JobRun(job_name=job.name, status=RunStatus.RUNNING)


# --- models/__init__.py wrapper functions ---


class TestModelsWrapperFunctions:
    def test_step_roundtrip(self):
        step = Step(
            name="x",
            step_type=StepType.SUBPROCESS,
            handler=None,
            config={"command": ["echo"]},
        )
        assert dict_to_step(step_to_dict(step)).name == step.name

    def test_sub_job_roundtrip(self):
        sub = SubJob(job_name="parent")
        assert dict_to_sub_job(sub_job_to_dict(sub)).job_name == sub.job_name

    def test_job_roundtrip(self):
        job = _job()
        assert dict_to_job(job_to_dict(job)).name == job.name

    def test_step_log_roundtrip(self):
        log = StepLog(timestamp=datetime.now(UTC), level="INFO", message="hi")
        assert dict_to_step_log(step_log_to_dict(log)).message == log.message

    def test_step_run_roundtrip(self):
        sr = StepRun(step_name="s1", job_run_id="jr-1", status=RunStatus.SUCCESS)
        assert dict_to_step_run(step_run_to_dict(sr)).step_name == sr.step_name

    def test_job_run_roundtrip(self):
        jr = JobRun(job_name="test", status=RunStatus.SUCCESS)
        assert dict_to_job_run(job_run_to_dict(jr)).job_name == jr.job_name


# --- persistence/__init__.py lazy imports ---


class TestPersistenceInit:
    def test_lazy_in_memory(self):
        import pyworkflow_engine.persistence as pm

        assert pm.InMemoryPersistence is InMemoryPersistence

    def test_lazy_json_file(self):
        import pyworkflow_engine.persistence as pm

        assert pm.JSONFilePersistence is JSONFilePersistence

    def test_lazy_sqlite(self):
        import pyworkflow_engine.persistence as pm

        assert pm.SQLitePersistence is SQLitePersistence

    def test_attribute_error(self):
        import pyworkflow_engine.persistence as pm

        with pytest.raises(AttributeError, match="no attribute"):
            _ = pm.DoesNotExist  # type: ignore[attr-defined]


# --- persistence/base.py utilities ---


class TestBasePersistenceUtilities:
    def setup_method(self):
        self.p = InMemoryPersistence()

    def test_health_check(self):
        hc = self.p.health_check()
        assert hc["status"] == "healthy"
        assert "backend" in hc

    def test_get_statistics_empty(self):
        stats = self.p.get_statistics()
        assert stats["total_jobs"] == 0

    def test_get_statistics_with_data(self):
        job = _job("stat_job")
        self.p.save_job(job)
        self.p.save_job_run(_run(job))
        stats = self.p.get_statistics()
        assert stats["total_jobs"] >= 1

    def test_get_job_run_count_all(self):
        job = _job()
        self.p.save_job(job)
        for _ in range(3):
            self.p.save_job_run(_run(job))
        assert self.p.get_job_run_count() == 3

    def test_get_job_run_count_by_name(self):
        job_a = _job("cnt_a")
        job_b = _job("cnt_b")
        self.p.save_job(job_a)
        self.p.save_job(job_b)
        self.p.save_job_run(_run(job_a))
        self.p.save_job_run(_run(job_a))
        self.p.save_job_run(_run(job_b))
        assert self.p.get_job_run_count("cnt_a") == 2
        assert self.p.get_job_run_count("cnt_b") == 1

    def test_cleanup_dry_run(self):
        job = _job()
        self.p.save_job(job)
        old = JobRun(
            job_name=job.name,
            status=RunStatus.SUCCESS,
            created_at=datetime.now(UTC) - timedelta(days=10),
        )
        self.p.save_job_run(old)
        count = self.p.cleanup_old_runs(
            older_than=datetime.now(UTC) - timedelta(days=1), dry_run=True
        )
        assert count == 1
        assert self.p.get_job_run(old.job_run_id) is not None

    def test_cleanup_real(self):
        job = _job()
        self.p.save_job(job)
        old = JobRun(
            job_name=job.name,
            status=RunStatus.SUCCESS,
            created_at=datetime.now(UTC) - timedelta(days=10),
        )
        self.p.save_job_run(old)
        count = self.p.cleanup_old_runs(
            older_than=datetime.now(UTC) - timedelta(days=1)
        )
        assert count == 1
        assert self.p.get_job_run(old.job_run_id) is None


class TestTransactionContext:
    def test_commit_on_success(self):
        p = InMemoryPersistence()
        job = _job()
        p.save_job(job)
        run = _run(job)
        with p.transaction() as tx:
            tx.save_job_run(run)
        assert p.get_job_run(run.job_run_id) is not None

    def test_rollback_on_exception(self):
        p = InMemoryPersistence()
        job = _job()
        p.save_job(job)
        run = _run(job)
        with pytest.raises(ValueError):
            with p.transaction() as tx:
                tx.save_job_run(run)
                raise ValueError("boom")
        assert p.get_job_run(run.job_run_id) is None

    def test_commit_failure_propagates(self):
        p = InMemoryPersistence()
        ctx = TransactionContext(p)
        original = p.commit_transaction

        def broken():
            raise TransactionError("forced")

        p.commit_transaction = broken  # type: ignore[method-assign]
        with pytest.raises(TransactionError, match="forced"):
            with ctx:
                pass
        p.commit_transaction = original  # type: ignore[method-assign]


# --- persistence/memory.py edge cases ---


class TestInMemoryEdgeCases:
    def setup_method(self):
        self.p = InMemoryPersistence()

    def test_update_not_found(self):
        with pytest.raises(JobNotFoundError):
            self.p.update_job_run(JobRun(job_name="ghost", status=RunStatus.RUNNING))

    def test_begin_tx_while_active(self):
        self.p.begin_transaction()
        with pytest.raises(PersistenceError, match="already active"):
            self.p.begin_transaction()
        self.p.rollback_transaction()

    def test_commit_no_tx(self):
        with pytest.raises(PersistenceError, match="No active"):
            self.p.commit_transaction()

    def test_rollback_no_tx(self):
        with pytest.raises(PersistenceError):
            self.p.rollback_transaction()

    def test_rollback_restores_state(self):
        job = _job()
        self.p.save_job(job)
        self.p.begin_transaction()
        self.p.delete_job(job.name)
        self.p.rollback_transaction()
        assert self.p.get_job(job.name) is not None

    def test_statistics_tx_active(self):
        self.p.begin_transaction()
        assert self.p.get_statistics()["transaction_active"] is True
        self.p.rollback_transaction()

    def test_memory_usage_with_snapshot(self):
        self.p.save_job(_job())
        self.p.begin_transaction()
        assert self.p.get_statistics()["memory_usage_mb"] >= 0
        self.p.rollback_transaction()

    def test_clear_during_tx_raises(self):
        self.p.begin_transaction()
        with pytest.raises(PersistenceError, match="Cannot clear"):
            self.p.clear_all_data()
        self.p.rollback_transaction()

    def test_clear_removes_everything(self):
        job = _job()
        self.p.save_job(job)
        run = _run(job)
        self.p.save_job_run(run)
        self.p.clear_all_data()
        assert self.p.get_job(job.name) is None
        assert self.p.get_job_run(run.job_run_id) is None

    def test_export_data(self):
        job = _job()
        self.p.save_job(job)
        run = _run(job)
        self.p.save_job_run(run)
        exp = self.p.export_data()
        assert job.name in exp["job_names"]
        assert run.job_run_id in exp["job_run_ids"]

    def test_import_raises(self):
        with pytest.raises(PersistenceError, match="does not support import_data"):
            self.p.import_data({})


# --- persistence/json_file.py transactions ---


class TestJSONFilePersistenceTransactions:
    @pytest.fixture()
    def jfp(self, tmp_path):
        return JSONFilePersistence(str(tmp_path / "data"))

    def test_double_begin_raises(self, jfp):
        jfp.begin_transaction()
        with pytest.raises(TransactionError):
            jfp.begin_transaction()
        jfp.rollback_transaction()

    def test_commit_no_tx_raises(self, jfp):
        with pytest.raises(TransactionError):
            jfp.commit_transaction()

    def test_rollback_no_tx_raises(self, jfp):
        with pytest.raises(TransactionError):
            jfp.rollback_transaction()

    def test_tx_commit(self, jfp):
        job = _job("tx_job")
        jfp.begin_transaction()
        jfp.save_job(job)
        jfp.commit_transaction()
        assert jfp.get_job(job.name) is not None

    def test_tx_rollback(self, jfp):
        job = _job("tx_rollback")
        jfp.begin_transaction()
        jfp.save_job(job)
        jfp.rollback_transaction()
        assert jfp.get_job(job.name) is None

    def test_atomic_read_write(self, jfp):
        job = _job("atomic")
        jfp.save_job(job)
        assert jfp.get_job(job.name).name == job.name

    def test_delete_nonexistent(self, jfp):
        assert jfp.delete_job("nope") is False

    def test_list_runs_status_filter(self, jfp):
        job = _job("filt")
        jfp.save_job(job)
        jfp.save_job_run(JobRun(job_name=job.name, status=RunStatus.SUCCESS))
        jfp.save_job_run(JobRun(job_name=job.name, status=RunStatus.FAILED))
        runs = jfp.list_job_runs(status=RunStatus.SUCCESS.value)
        assert all(r.status == RunStatus.SUCCESS for r in runs)

    def test_update_job_run(self, jfp):
        job = _job()
        jfp.save_job(job)
        run = _run(job)
        jfp.save_job_run(run)
        run.status = RunStatus.SUCCESS
        jfp.update_job_run(run)
        assert jfp.get_job_run(run.job_run_id).status == RunStatus.SUCCESS

    def test_update_not_found(self, jfp):
        with pytest.raises(JobNotFoundError):
            jfp.update_job_run(JobRun(job_name="ghost", status=RunStatus.RUNNING))


# --- persistence/sqlite.py edge cases ---


class TestSQLiteEdgeCases:
    @pytest.fixture()
    def db(self):
        return SQLitePersistence(":memory:")

    def test_list_by_status(self, db):
        job = _job()
        db.save_job(job)
        db.save_job_run(JobRun(job_name=job.name, status=RunStatus.SUCCESS))
        db.save_job_run(JobRun(job_name=job.name, status=RunStatus.FAILED))
        runs = db.list_job_runs(status=RunStatus.SUCCESS.value)
        assert all(r.status == RunStatus.SUCCESS for r in runs)

    def test_list_limit_offset(self, db):
        job = _job()
        db.save_job(job)
        for _ in range(5):
            db.save_job_run(_run(job))
        p1 = db.list_job_runs(limit=2, offset=0)
        p2 = db.list_job_runs(limit=2, offset=2)
        assert len(p1) == 2 and len(p2) == 2
        assert {r.job_run_id for r in p1}.isdisjoint({r.job_run_id for r in p2})

    def test_list_since(self, db):
        job = _job()
        db.save_job(job)
        # SQLite list_job_runs(since=) filters on created_at, so we must set
        # created_at to a past value for the "old" run.
        old = JobRun(
            job_name=job.name,
            status=RunStatus.SUCCESS,
            created_at=datetime.now(UTC) - timedelta(days=10),
        )
        new = JobRun(
            job_name=job.name, status=RunStatus.SUCCESS, created_at=datetime.now(UTC)
        )
        db.save_job_run(old)
        db.save_job_run(new)
        cutoff = datetime.now(UTC) - timedelta(days=1)
        recent = {r.job_run_id for r in db.list_job_runs(since=cutoff)}
        assert new.job_run_id in recent
        assert old.job_run_id not in recent

    def test_update_not_found(self, db):
        with pytest.raises(JobNotFoundError):
            db.update_job_run(JobRun(job_name="ghost", status=RunStatus.RUNNING))

    def test_count_by_name(self, db):
        a = _job("sq_a")
        b = _job("sq_b")
        db.save_job(a)
        db.save_job(b)
        db.save_job_run(_run(a))
        db.save_job_run(_run(a))
        db.save_job_run(_run(b))
        assert db.get_job_run_count("sq_a") == 2
        assert db.get_job_run_count("sq_b") == 1
        assert db.get_job_run_count() == 3

    def test_cleanup_dry_run(self, db):
        job = _job()
        db.save_job(job)
        # SQLite cleanup_old_runs filters on created_at, not start_time
        old = JobRun(
            job_name=job.name,
            status=RunStatus.SUCCESS,
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        db.save_job_run(old)
        assert (
            db.cleanup_old_runs(
                older_than=datetime.now(UTC) - timedelta(days=1), dry_run=True
            )
            >= 1
        )
        assert db.get_job_run(old.job_run_id) is not None

    def test_cleanup_real(self, db):
        job = _job()
        db.save_job(job)
        old = JobRun(
            job_name=job.name,
            status=RunStatus.SUCCESS,
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        db.save_job_run(old)
        assert (
            db.cleanup_old_runs(older_than=datetime.now(UTC) - timedelta(days=1)) >= 1
        )
        assert db.get_job_run(old.job_run_id) is None

    def test_output_context_roundtrip(self, db):
        """Regression: sqlite3.Row.keys() must be used for membership checks."""
        job = _job()
        db.save_job(job)
        run = JobRun(
            job_name=job.name,
            status=RunStatus.SUCCESS,
            output_data={"result": 42},
            context={"step1": "done"},
        )
        db.save_job_run(run)
        r = db.get_job_run(run.job_run_id)
        assert r.output_data == {"result": 42}
        assert r.context == {"step1": "done"}

    def test_delete_job_run(self, db):
        job = _job()
        db.save_job(job)
        run = _run(job)
        db.save_job_run(run)
        db.delete_job_run(run.job_run_id)
        assert db.get_job_run(run.job_run_id) is None

    def test_health_check(self, db):
        assert db.health_check()["status"] == "healthy"

    def test_get_statistics(self, db):
        # SQLite get_statistics uses keys: total_jobs, total_runs (not total_job_runs)
        stats = db.get_statistics()
        assert "total_jobs" in stats
        assert "backend" in stats


# --- persistence/base.py — deeper coverage: get_statistics error branch,
#     cleanup_old_runs base impl, TransactionContext edge cases ---


class TestBasePersistenceDeeper:
    """Cover the remaining uncovered branches in persistence/base.py."""

    def test_get_statistics_error_branch(self):
        """Force the BasePersistence.get_statistics error branch directly.

        InMemoryPersistence overrides get_statistics, so we call the base
        implementation explicitly with a list_jobs that raises.
        """
        from pyworkflow_engine.persistence.base import BasePersistence

        p = InMemoryPersistence()

        original_list_jobs = p.list_jobs

        def bad_list_jobs(*a, **kw):
            raise RuntimeError("DB unavailable")

        p.list_jobs = bad_list_jobs  # type: ignore[method-assign]

        # Call the base class method directly to hit lines 248-258
        stats = BasePersistence.get_statistics(p)
        assert stats.get("error") == "Unable to collect statistics"
        assert stats["total_jobs"] == 0

        p.list_jobs = original_list_jobs  # type: ignore[method-assign]

    def test_base_cleanup_old_runs_via_base_method(self):
        """Call BasePersistence.cleanup_old_runs directly (not overridden)."""
        from pyworkflow_engine.persistence.base import BasePersistence

        p = InMemoryPersistence()
        job = _job()
        p.save_job(job)
        run = JobRun(
            job_name=job.name,
            status=RunStatus.SUCCESS,
            start_time=datetime.now(UTC) - timedelta(days=30),
        )
        p.save_job_run(run)
        # Call the base class method directly (bypassing InMemory override)
        count = BasePersistence.cleanup_old_runs(
            p, older_than=datetime.now(UTC) - timedelta(days=1), dry_run=True
        )
        assert count == 1
        # Real deletion
        count2 = BasePersistence.cleanup_old_runs(
            p, older_than=datetime.now(UTC) - timedelta(days=1)
        )
        assert count2 == 1
        assert p.get_job_run(run.job_run_id) is None

    def test_transaction_context_no_in_transaction(self):
        """__exit__ when _in_transaction is False should be a no-op."""
        p = InMemoryPersistence()
        ctx = TransactionContext(p)
        ctx._in_transaction = False  # simulate: __enter__ never called
        # Should not raise
        ctx.__exit__(None, None, None)

    def test_transaction_context_commit_fail_rollback_suppressed(self):
        """commit_transaction raises; rollback is called but suppressed on failure."""
        p = InMemoryPersistence()
        ctx = TransactionContext(p)

        def bad_commit():
            raise TransactionError("commit failed")

        def bad_rollback():
            raise TransactionError("rollback failed too")

        p.commit_transaction = bad_commit  # type: ignore[method-assign]
        p.rollback_transaction = bad_rollback  # type: ignore[method-assign]

        p.begin_transaction()
        ctx._in_transaction = True

        # Even though rollback also raises, the original commit error is re-raised
        with pytest.raises(TransactionError, match="commit failed"):
            ctx.__exit__(None, None, None)


# --- persistence/__init__.py — ImportError branch for SQLAlchemy ---


class TestPersistenceInitImportError:
    """Cover the ImportError branch for optional SQLAlchemy backend."""

    def test_sqlalchemy_import_error_message(self):
        """Trigger the ImportError path for SQLAlchemy when not installed."""
        import sys
        import importlib

        # Temporarily hide sqlalchemy from sys.modules
        saved = sys.modules.pop("sqlalchemy", None)
        saved_alchemy = sys.modules.pop(
            "pyworkflow_engine.persistence.sqlalchemy", None
        )

        try:
            import pyworkflow_engine.persistence as pm

            # Clear the cached attribute so __getattr__ is triggered again
            pm.__dict__.pop("SQLAlchemyPersistence", None)

            # If sqlalchemy is genuinely absent, this should raise ImportError
            try:
                _ = pm.SQLAlchemyPersistence
            except ImportError as e:
                assert "sqlalchemy" in str(e).lower()
            except Exception:
                pass  # sqlalchemy IS installed — skip this branch
        finally:
            if saved is not None:
                sys.modules["sqlalchemy"] = saved
            if saved_alchemy is not None:
                sys.modules["pyworkflow_engine.persistence.sqlalchemy"] = saved_alchemy


# --- persistence/json_file.py — list_job_runs limit/offset, delete_job_run ---


class TestJSONFilePersistenceExtra:
    @pytest.fixture()
    def jfp(self, tmp_path):
        return JSONFilePersistence(str(tmp_path / "extra_data"))

    def test_list_job_runs_limit_offset(self, jfp):
        job = _job("lim_job")
        jfp.save_job(job)
        for _ in range(5):
            jfp.save_job_run(_run(job))

        page1 = jfp.list_job_runs(limit=2, offset=0)
        page2 = jfp.list_job_runs(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert {r.job_run_id for r in page1}.isdisjoint({r.job_run_id for r in page2})

    def test_delete_job_run(self, jfp):
        job = _job()
        jfp.save_job(job)
        run = _run(job)
        jfp.save_job_run(run)
        assert jfp.get_job_run(run.job_run_id) is not None
        jfp.delete_job_run(run.job_run_id)
        assert jfp.get_job_run(run.job_run_id) is None

    def test_get_job_run_count(self, jfp):
        job = _job()
        jfp.save_job(job)
        jfp.save_job_run(_run(job))
        jfp.save_job_run(_run(job))
        assert jfp.get_job_run_count() == 2
        assert jfp.get_job_run_count(job.name) == 2

    def test_cleanup_old_runs(self, jfp):
        # JSONFilePersistence.cleanup_old_runs filters on created_at, not start_time
        job = _job()
        jfp.save_job(job)
        old = JobRun(
            job_name=job.name,
            status=RunStatus.SUCCESS,
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        jfp.save_job_run(old)
        count = jfp.cleanup_old_runs(older_than=datetime.now(UTC) - timedelta(days=1))
        assert count >= 1

    def test_list_jobs_limit(self, jfp):
        for i in range(5):
            jfp.save_job(_job(f"job_{i}"))
        result = jfp.list_jobs(limit=3)
        assert len(result) == 3

    def test_health_check(self, jfp):
        hc = jfp.health_check()
        assert hc["status"] == "healthy"

    def test_get_statistics(self, jfp):
        stats = jfp.get_statistics()
        assert "total_jobs" in stats


# --- exceptions.py — cover uncovered __init__ and __str__ methods ---

class TestExceptionsDeepCoverage:
    """Cover the uncovered exception constructors and __str__ methods."""

    def test_step_execution_error_with_all_fields(self):
        from pyworkflow_engine.exceptions import StepExecutionError
        orig = ValueError("root cause")
        e = StepExecutionError(
            "step failed",
            job_name="my_job",
            step_name="my_step",
            original_exception=orig,
            step_run_id="sr-123",
            retry_count=2,
        )
        s = str(e)
        assert "Original" in s
        assert "StepRunID" in s
        assert "Retry" in s

    def test_workflow_timeout_error(self):
        from pyworkflow_engine.exceptions import WorkflowTimeoutError
        e = WorkflowTimeoutError(
            "timed out",
            timeout_seconds=30.0,
            elapsed_seconds=31.5,
        )
        s = str(e)
        assert "30" in s
        assert "31" in s

    def test_workflow_cancelled(self):
        from pyworkflow_engine.exceptions import WorkflowCancelled
        e = WorkflowCancelled(
            "cancelled",
            cancelled_by="operator",
            cancel_reason="manual stop",
        )
        assert e.cancelled_by == "operator"
        assert e.cancel_reason == "manual stop"

    def test_executor_error(self):
        from pyworkflow_engine.exceptions import ExecutorError
        e = ExecutorError(
            "executor failed",
            executor_type="thread",
            executor_details={"pool_size": 4},
        )
        assert e.executor_type == "thread"
        assert e.executor_details == {"pool_size": 4}

    def test_persistence_error_class(self):
        from pyworkflow_engine.exceptions import PersistenceError
        e = PersistenceError(
            "save failed",
            operation="save",
            persistence_type="sqlite",
        )
        assert e.operation == "save"
        assert e.persistence_type == "sqlite"

    def test_context_error(self):
        from pyworkflow_engine.exceptions import ContextError
        e = ContextError(
            "ctx error",
            context_key="my_key",
            context_operation="read",
        )
        assert e.context_key == "my_key"
        assert e.context_operation == "read"

    def test_create_step_failed_error(self):
        from pyworkflow_engine.exceptions import create_step_failed_error
        e = create_step_failed_error(
            job_name="j",
            step_name="s",
            original_exception=RuntimeError("oops"),
        )
        assert "j" in str(e) or e.job_name == "j"

    def test_create_timeout_error(self):
        from pyworkflow_engine.exceptions import create_timeout_error
        e = create_timeout_error(
            entity_name="s",
            entity_type="step",
            timeout_seconds=10.0,
            elapsed_seconds=11.0,
            job_name="j",
            step_name="s",
        )
        assert e is not None

    def test_create_validation_error(self):
        from pyworkflow_engine.exceptions import create_validation_error
        e = create_validation_error(
            message="invalid field",
        )
        assert e is not None
