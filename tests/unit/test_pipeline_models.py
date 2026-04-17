"""
Tests unitaires — modèles Pipeline (design-time + runtime).

Couvre :
- PipelineStage : construction, validation, frozen, sérialisation
- Pipeline : construction, validation, propriétés, sérialisation
- StageRun : construction, transitions d'état, sérialisation
- PipelineRun : construction, transitions, properties, summary, sérialisation
- Enums ADR-013 : StepType IA, TriggerType.AI
- models/__init__.py exports
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyworkflow_engine.models.enums import (
    Priority,
    RunStatus,
    StepType,
    TriggerType,
)
from pyworkflow_engine.models.pipeline.pipeline import Pipeline, PipelineStage
from pyworkflow_engine.models.pipeline.pipeline_run import PipelineRun, StageRun
from pyworkflow_engine.models.workflow.run import JobRun

# ======================================================================
# PipelineStage (design-time, frozen)
# ======================================================================


class TestPipelineStage:
    """Tests pour PipelineStage."""

    def test_basic_construction(self):
        stage = PipelineStage(job_name="ingestion")
        assert stage.job_name == "ingestion"
        assert stage.job is None
        assert stage.initial_context == {}
        assert stage.context_mapping == {}
        assert stage.continue_on_failure is False
        assert stage.condition is None
        assert stage.enabled is True
        assert stage.metadata == {}

    def test_full_construction(self):
        cond = lambda ctx: ctx.get("ready", False)  # noqa: E731
        stage = PipelineStage(
            job_name="transform",
            initial_context={"mode": "full"},
            context_mapping={"input_data": "raw_data"},
            continue_on_failure=True,
            condition=cond,
            enabled=True,
            metadata={"team": "data"},
        )
        assert stage.job_name == "transform"
        assert stage.initial_context == {"mode": "full"}
        assert stage.context_mapping == {"input_data": "raw_data"}
        assert stage.continue_on_failure is True
        assert stage.condition is cond
        assert stage.metadata == {"team": "data"}

    def test_empty_job_name_raises(self):
        with pytest.raises(ValueError, match="job_name cannot be empty"):
            PipelineStage(job_name="")

    def test_frozen_immutability(self):
        stage = PipelineStage(job_name="ingestion")
        with pytest.raises(ValidationError):
            stage.job_name = "other"  # type: ignore[misc]

    def test_to_dict(self):
        stage = PipelineStage(
            job_name="ingestion",
            initial_context={"source": "api"},
            context_mapping={"out": "in"},
            continue_on_failure=True,
            enabled=False,
            metadata={"v": 1},
        )
        d = stage.to_dict()
        assert d["job_name"] == "ingestion"
        assert d["initial_context"] == {"source": "api"}
        assert d["context_mapping"] == {"out": "in"}
        assert d["continue_on_failure"] is True
        assert d["enabled"] is False
        assert d["metadata"] == {"v": 1}
        # Callables excluded
        assert "job" not in d
        assert "condition" not in d

    def test_from_dict(self):
        data = {
            "job_name": "ingestion",
            "initial_context": {"source": "api"},
            "context_mapping": {"out": "in"},
            "continue_on_failure": True,
            "enabled": False,
            "metadata": {"v": 1},
        }
        stage = PipelineStage.from_dict(data)
        assert stage.job_name == "ingestion"
        assert stage.initial_context == {"source": "api"}
        assert stage.continue_on_failure is True
        assert stage.enabled is False

    def test_from_dict_defaults(self):
        stage = PipelineStage.from_dict({"job_name": "simple"})
        assert stage.initial_context == {}
        assert stage.context_mapping == {}
        assert stage.continue_on_failure is False
        assert stage.enabled is True

    def test_serialization_roundtrip(self):
        stage = PipelineStage(
            job_name="quality-check",
            continue_on_failure=True,
            metadata={"critical": False},
        )
        restored = PipelineStage.from_dict(stage.to_dict())
        assert restored.job_name == stage.job_name
        assert restored.continue_on_failure == stage.continue_on_failure
        assert restored.metadata == stage.metadata

    def test_equality(self):
        s1 = PipelineStage(job_name="a", continue_on_failure=True)
        s2 = PipelineStage(job_name="a", continue_on_failure=True)
        assert s1 == s2

    def test_inequality(self):
        s1 = PipelineStage(job_name="a")
        s2 = PipelineStage(job_name="b")
        assert s1 != s2


# ======================================================================
# Pipeline (design-time, frozen)
# ======================================================================


class TestPipeline:
    """Tests pour Pipeline."""

    def test_basic_construction(self):
        p = Pipeline(name="my-pipeline")
        assert p.name == "my-pipeline"
        assert p.description == ""
        assert p.stages == []
        assert p.triggers == [TriggerType.MANUAL]
        assert p.schedule is None
        assert p.priority == Priority.NORMAL
        assert p.tags == []
        assert p.metadata == {}
        assert p.version == "1.0.0"
        assert p.enabled is True
        assert p.owner == ""
        assert p.on_success is None
        assert p.on_failure is None

    def test_full_construction(self):
        stages = [
            PipelineStage(job_name="ingest"),
            PipelineStage(job_name="transform"),
            PipelineStage(job_name="quality", continue_on_failure=True),
        ]
        p = Pipeline(
            name="weekly-etl",
            description="Weekly ETL pipeline",
            stages=stages,
            triggers=[TriggerType.SCHEDULE, TriggerType.MANUAL],
            schedule="0 1 * * 0",
            priority=Priority.HIGH,
            tags=["etl", "weekly"],
            metadata={"team": "data"},
            version="2.0.0",
            enabled=True,
            owner="data-team@company.com",
        )
        assert p.name == "weekly-etl"
        assert p.stage_count == 3
        assert p.schedule == "0 1 * * 0"
        assert p.priority == Priority.HIGH
        assert p.owner == "data-team@company.com"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="Pipeline name cannot be empty"):
            Pipeline(name="")

    def test_duplicate_job_names_raises(self):
        with pytest.raises(ValueError, match="job_names must be unique"):
            Pipeline(
                name="dup",
                stages=[
                    PipelineStage(job_name="a"),
                    PipelineStage(job_name="a"),
                ],
            )

    def test_frozen_immutability(self):
        p = Pipeline(name="test")
        with pytest.raises(ValidationError):
            p.name = "other"  # type: ignore[misc]

    def test_stage_count(self):
        p = Pipeline(
            name="test",
            stages=[
                PipelineStage(job_name="a"),
                PipelineStage(job_name="b"),
            ],
        )
        assert p.stage_count == 2

    def test_stage_count_empty(self):
        p = Pipeline(name="empty")
        assert p.stage_count == 0

    def test_job_names(self):
        p = Pipeline(
            name="test",
            stages=[
                PipelineStage(job_name="ingest"),
                PipelineStage(job_name="transform"),
                PipelineStage(job_name="quality"),
            ],
        )
        assert p.job_names == ["ingest", "transform", "quality"]

    def test_get_stage_found(self):
        stage = PipelineStage(job_name="transform", continue_on_failure=True)
        p = Pipeline(name="test", stages=[PipelineStage(job_name="ingest"), stage])
        found = p.get_stage("transform")
        assert found is stage

    def test_get_stage_not_found(self):
        p = Pipeline(name="test", stages=[PipelineStage(job_name="ingest")])
        assert p.get_stage("nonexistent") is None

    def test_get_stage_index(self):
        p = Pipeline(
            name="test",
            stages=[
                PipelineStage(job_name="a"),
                PipelineStage(job_name="b"),
                PipelineStage(job_name="c"),
            ],
        )
        assert p.get_stage_index("a") == 0
        assert p.get_stage_index("b") == 1
        assert p.get_stage_index("c") == 2
        assert p.get_stage_index("z") is None

    def test_to_dict(self):
        p = Pipeline(
            name="weekly-etl",
            description="ETL pipeline",
            stages=[PipelineStage(job_name="ingest")],
            triggers=[TriggerType.SCHEDULE],
            schedule="0 1 * * 0",
            priority=Priority.HIGH,
            tags=["etl"],
            metadata={"v": 1},
            version="2.0.0",
            enabled=False,
            owner="team@co.com",
        )
        d = p.to_dict()
        assert d["name"] == "weekly-etl"
        assert d["description"] == "ETL pipeline"
        assert len(d["stages"]) == 1
        assert d["stages"][0]["job_name"] == "ingest"
        assert d["triggers"] == ["schedule"]
        assert d["schedule"] == "0 1 * * 0"
        assert d["priority"] == Priority.HIGH.value
        assert d["tags"] == ["etl"]
        assert d["metadata"] == {"v": 1}
        assert d["version"] == "2.0.0"
        assert d["enabled"] is False
        assert d["owner"] == "team@co.com"
        # Callables excluded
        assert "on_success" not in d
        assert "on_failure" not in d

    def test_from_dict(self):
        data = {
            "name": "weekly-etl",
            "description": "ETL",
            "stages": [
                {"job_name": "ingest"},
                {"job_name": "transform", "continue_on_failure": True},
            ],
            "triggers": ["schedule", "manual"],
            "schedule": "0 1 * * 0",
            "priority": 10,
            "tags": ["etl"],
            "metadata": {"team": "data"},
            "version": "2.0.0",
            "enabled": True,
            "owner": "team@co.com",
        }
        p = Pipeline.from_dict(data)
        assert p.name == "weekly-etl"
        assert p.stage_count == 2
        assert p.stages[1].continue_on_failure is True
        assert p.triggers == [TriggerType.SCHEDULE, TriggerType.MANUAL]
        assert p.schedule == "0 1 * * 0"
        assert p.priority == Priority.HIGH
        assert p.owner == "team@co.com"

    def test_from_dict_defaults(self):
        p = Pipeline.from_dict({"name": "minimal"})
        assert p.stages == []
        assert p.triggers == [TriggerType.MANUAL]
        assert p.schedule is None
        assert p.priority == Priority.NORMAL
        assert p.version == "1.0.0"
        assert p.enabled is True
        assert p.owner == ""

    def test_serialization_roundtrip(self):
        p = Pipeline(
            name="roundtrip",
            stages=[
                PipelineStage(
                    job_name="a",
                    initial_context={"k": "v"},
                    context_mapping={"out": "in"},
                    continue_on_failure=True,
                ),
                PipelineStage(job_name="b"),
            ],
            triggers=[TriggerType.SCHEDULE, TriggerType.WEBHOOK],
            schedule="*/5 * * * *",
            priority=Priority.CRITICAL,
            tags=["test", "roundtrip"],
            metadata={"version_note": "test"},
            version="3.0.0",
            owner="qa@company.com",
        )
        restored = Pipeline.from_dict(p.to_dict())
        assert restored.name == p.name
        assert restored.stage_count == p.stage_count
        assert restored.stages[0].initial_context == {"k": "v"}
        assert restored.stages[0].context_mapping == {"out": "in"}
        assert restored.stages[0].continue_on_failure is True
        assert restored.triggers == p.triggers
        assert restored.schedule == p.schedule
        assert restored.priority == p.priority
        assert restored.tags == p.tags
        assert restored.version == p.version
        assert restored.owner == p.owner

    def test_repr(self):
        p = Pipeline(
            name="my-pipeline",
            stages=[PipelineStage(job_name="a")],
            version="1.2.0",
        )
        r = repr(p)
        assert "my-pipeline" in r
        assert "stages=1" in r
        assert "1.2.0" in r

    def test_ai_trigger(self):
        """Pipeline peut utiliser TriggerType.AI (ADR-013)."""
        p = Pipeline(
            name="ai-triggered",
            triggers=[TriggerType.AI, TriggerType.MANUAL],
        )
        assert TriggerType.AI in p.triggers
        d = p.to_dict()
        assert "ai" in d["triggers"]
        restored = Pipeline.from_dict(d)
        assert TriggerType.AI in restored.triggers


# ======================================================================
# StageRun (runtime, mutable)
# ======================================================================


class TestStageRun:
    """Tests pour StageRun."""

    def test_default_construction(self):
        sr = StageRun()
        assert sr.stage_run_id  # UUID generated
        assert sr.pipeline_run_id == ""
        assert sr.job_name == ""
        assert sr.stage_index == 0
        assert sr.status == RunStatus.PENDING
        assert sr.job_run is None
        assert sr.skipped is False
        assert sr.skip_reason == ""
        assert sr.error is None
        assert sr.start_time is None
        assert sr.end_time is None
        assert sr.duration_ms is None
        assert sr.metadata == {}

    def test_named_construction(self):
        sr = StageRun(job_name="ingestion", stage_index=2)
        assert sr.job_name == "ingestion"
        assert sr.stage_index == 2

    def test_start_execution(self):
        sr = StageRun(job_name="test")
        sr.start_execution()
        assert sr.status == RunStatus.RUNNING
        assert sr.start_time is not None

    def test_complete_success(self):
        sr = StageRun(job_name="test")
        sr.start_execution()
        sr.complete_success()
        assert sr.status == RunStatus.SUCCESS
        assert sr.end_time is not None
        assert sr.duration_ms is not None
        assert sr.duration_ms >= 0

    def test_complete_failure(self):
        sr = StageRun(job_name="test")
        sr.start_execution()
        sr.complete_failure("DB connection lost")
        assert sr.status == RunStatus.FAILED
        assert sr.error == "DB connection lost"
        assert sr.end_time is not None

    def test_mark_skipped(self):
        sr = StageRun(job_name="test")
        sr.mark_skipped("condition not met")
        assert sr.status == RunStatus.CANCELLED
        assert sr.skipped is True
        assert sr.skip_reason == "condition not met"

    def test_mark_skipped_no_reason(self):
        sr = StageRun(job_name="test")
        sr.mark_skipped()
        assert sr.skipped is True
        assert sr.skip_reason == ""

    def test_cancel(self):
        sr = StageRun(job_name="test")
        sr.start_execution()
        sr.cancel()
        assert sr.status == RunStatus.CANCELLED
        assert sr.end_time is not None

    def test_mark_timeout(self):
        sr = StageRun(job_name="test")
        sr.start_execution()
        sr.mark_timeout()
        assert sr.status == RunStatus.TIMEOUT
        assert sr.end_time is not None

    def test_is_terminal(self):
        sr = StageRun(job_name="test")
        assert sr.is_terminal is False
        sr.start_execution()
        assert sr.is_terminal is False
        sr.complete_success()
        assert sr.is_terminal is True

    def test_is_suspended(self):
        sr = StageRun(job_name="test")
        assert sr.is_suspended is False
        sr.status = RunStatus.SUSPENDED
        assert sr.is_suspended is True

    def test_duration_s(self):
        sr = StageRun(job_name="test")
        assert sr.duration_s == pytest.approx(0.0)
        sr.duration_ms = 1500
        assert sr.duration_s == pytest.approx(1.5)

    def test_with_job_run(self):
        jr = JobRun(job_name="sub-job")
        sr = StageRun(job_name="test", job_run=jr)
        assert sr.job_run is jr

    def test_to_dict(self):
        sr = StageRun(job_name="ingestion", stage_index=1)
        sr.start_execution()
        sr.complete_success()
        d = sr.to_dict()
        assert d["job_name"] == "ingestion"
        assert d["stage_index"] == 1
        assert d["status"] == "success"
        assert d["start_time"] is not None
        assert d["end_time"] is not None
        assert d["duration_ms"] is not None
        assert d["skipped"] is False
        assert d["job_run"] is None

    def test_to_dict_with_job_run(self):
        jr = JobRun(job_name="sub-job")
        sr = StageRun(job_name="test", job_run=jr)
        d = sr.to_dict()
        assert d["job_run"] is not None
        assert d["job_run"]["job_name"] == "sub-job"

    def test_from_dict(self):
        data = {
            "stage_run_id": "sr-123",
            "pipeline_run_id": "pr-456",
            "job_name": "ingestion",
            "stage_index": 0,
            "status": "success",
            "job_run": None,
            "skipped": False,
            "skip_reason": "",
            "error": None,
            "start_time": "2026-04-12T01:00:00+00:00",
            "end_time": "2026-04-12T01:01:00+00:00",
            "duration_ms": 60000,
            "metadata": {"k": "v"},
        }
        sr = StageRun.from_dict(data)
        assert sr.stage_run_id == "sr-123"
        assert sr.pipeline_run_id == "pr-456"
        assert sr.job_name == "ingestion"
        assert sr.status == RunStatus.SUCCESS
        assert sr.duration_ms == 60000
        assert sr.metadata == {"k": "v"}

    def test_from_dict_with_job_run(self):
        jr = JobRun(job_name="sub-job")
        jr.start_execution()
        jr.complete_success({"result": 42})
        sr = StageRun(
            stage_run_id="sr-x",
            job_name="test",
            job_run=jr,
        )
        d = sr.to_dict()
        restored = StageRun.from_dict(d)
        assert restored.job_run is not None
        assert restored.job_run.job_name == "sub-job"
        assert restored.job_run.status == RunStatus.SUCCESS

    def test_serialization_roundtrip(self):
        sr = StageRun(job_name="quality", stage_index=3)
        sr.pipeline_run_id = "pr-abc"
        sr.start_execution()
        sr.complete_failure("assertion error")
        d = sr.to_dict()
        restored = StageRun.from_dict(d)
        assert restored.stage_run_id == sr.stage_run_id
        assert restored.job_name == "quality"
        assert restored.stage_index == 3
        assert restored.status == RunStatus.FAILED
        assert restored.error == "assertion error"
        assert restored.pipeline_run_id == "pr-abc"


# ======================================================================
# PipelineRun (runtime, mutable)
# ======================================================================


class TestPipelineRun:
    """Tests pour PipelineRun."""

    def test_default_construction(self):
        pr = PipelineRun()
        assert pr.pipeline_run_id  # UUID generated
        assert pr.pipeline_name == ""
        assert pr.pipeline_version == "1.0.0"
        assert pr.status == RunStatus.PENDING
        assert pr.stage_runs == []
        assert pr.context == {}
        assert pr.error is None
        assert pr.start_time is None
        assert pr.end_time is None
        assert pr.duration_ms is None
        assert pr.triggered_by == "manual"
        assert pr.trigger_data == {}
        assert pr.metadata == {}
        assert pr.created_at is not None
        assert pr.updated_at is not None

    def test_named_construction(self):
        pr = PipelineRun(
            pipeline_name="weekly-etl",
            pipeline_version="2.0.0",
            triggered_by="schedule",
        )
        assert pr.pipeline_name == "weekly-etl"
        assert pr.pipeline_version == "2.0.0"
        assert pr.triggered_by == "schedule"

    def test_start_execution(self):
        pr = PipelineRun(pipeline_name="test")
        pr.start_execution()
        assert pr.status == RunStatus.RUNNING
        assert pr.start_time is not None

    def test_complete_success(self):
        pr = PipelineRun(pipeline_name="test")
        pr.start_execution()
        pr.complete_success()
        assert pr.status == RunStatus.SUCCESS
        assert pr.success is True
        assert pr.end_time is not None
        assert pr.duration_ms is not None
        assert pr.duration_ms >= 0

    def test_complete_failure(self):
        pr = PipelineRun(pipeline_name="test")
        pr.start_execution()
        pr.complete_failure("Stage 2 failed")
        assert pr.status == RunStatus.FAILED
        assert pr.success is False
        assert pr.error == "Stage 2 failed"

    def test_cancel(self):
        pr = PipelineRun(pipeline_name="test")
        pr.start_execution()
        pr.cancel()
        assert pr.status == RunStatus.CANCELLED
        assert pr.end_time is not None

    def test_mark_timeout(self):
        pr = PipelineRun(pipeline_name="test")
        pr.start_execution()
        pr.mark_timeout()
        assert pr.status == RunStatus.TIMEOUT
        assert pr.end_time is not None

    def test_add_stage_run(self):
        pr = PipelineRun(pipeline_name="test")
        sr = StageRun(job_name="ingest", stage_index=0)
        pr.add_stage_run(sr)
        assert len(pr.stage_runs) == 1
        assert sr.pipeline_run_id == pr.pipeline_run_id

    def test_add_multiple_stage_runs(self):
        pr = PipelineRun(pipeline_name="test")
        sr1 = StageRun(job_name="ingest", stage_index=0)
        sr2 = StageRun(job_name="transform", stage_index=1)
        pr.add_stage_run(sr1)
        pr.add_stage_run(sr2)
        assert len(pr.stage_runs) == 2
        assert pr.stage_runs[0].job_name == "ingest"
        assert pr.stage_runs[1].job_name == "transform"

    def test_get_stage_run_found(self):
        pr = PipelineRun(pipeline_name="test")
        sr = StageRun(job_name="ingest", stage_index=0)
        pr.add_stage_run(sr)
        found = pr.get_stage_run("ingest")
        assert found is sr

    def test_get_stage_run_not_found(self):
        pr = PipelineRun(pipeline_name="test")
        assert pr.get_stage_run("nonexistent") is None

    def test_get_stage_runs_by_status(self):
        pr = PipelineRun(pipeline_name="test")
        sr1 = StageRun(job_name="a", stage_index=0)
        sr1.start_execution()
        sr1.complete_success()
        sr2 = StageRun(job_name="b", stage_index=1)
        sr2.start_execution()
        sr2.complete_failure("error")
        sr3 = StageRun(job_name="c", stage_index=2)
        sr3.start_execution()
        sr3.complete_success()
        pr.add_stage_run(sr1)
        pr.add_stage_run(sr2)
        pr.add_stage_run(sr3)
        successes = pr.get_stage_runs_by_status(RunStatus.SUCCESS)
        assert len(successes) == 2
        failures = pr.get_stage_runs_by_status(RunStatus.FAILED)
        assert len(failures) == 1

    def test_is_terminal(self):
        pr = PipelineRun(pipeline_name="test")
        assert pr.is_terminal is False
        pr.start_execution()
        assert pr.is_terminal is False
        pr.complete_success()
        assert pr.is_terminal is True

    def test_is_suspended(self):
        pr = PipelineRun(pipeline_name="test")
        assert pr.is_suspended is False
        pr.status = RunStatus.SUSPENDED
        assert pr.is_suspended is True

    def test_duration_s(self):
        pr = PipelineRun(pipeline_name="test")
        assert pr.duration_s == pytest.approx(0.0)
        pr.duration_ms = 2500
        assert pr.duration_s == pytest.approx(2.5)

    def test_progress_percentage_empty(self):
        pr = PipelineRun(pipeline_name="test")
        assert pr.progress_percentage == pytest.approx(0.0)

    def test_progress_percentage(self):
        pr = PipelineRun(pipeline_name="test")
        sr1 = StageRun(job_name="a", stage_index=0)
        sr1.start_execution()
        sr1.complete_success()
        sr2 = StageRun(job_name="b", stage_index=1)
        # still pending
        pr.add_stage_run(sr1)
        pr.add_stage_run(sr2)
        assert pr.progress_percentage == pytest.approx(50.0)

    def test_progress_percentage_all_done(self):
        pr = PipelineRun(pipeline_name="test")
        for i, name in enumerate(["a", "b", "c"]):
            sr = StageRun(job_name=name, stage_index=i)
            sr.start_execution()
            sr.complete_success()
            pr.add_stage_run(sr)
        assert pr.progress_percentage == pytest.approx(100.0)

    def test_success_property(self):
        pr = PipelineRun(pipeline_name="test")
        assert pr.success is False
        pr.start_execution()
        assert pr.success is False
        pr.complete_success()
        assert pr.success is True

    def test_summary_success(self):
        pr = PipelineRun(pipeline_name="weekly-etl")
        pr.start_execution()

        sr1 = StageRun(job_name="ingest", stage_index=0)
        sr1.start_execution()
        sr1.duration_ms = 18420
        sr1.status = RunStatus.SUCCESS
        pr.add_stage_run(sr1)

        sr2 = StageRun(job_name="transform", stage_index=1)
        sr2.start_execution()
        sr2.duration_ms = 3110
        sr2.status = RunStatus.SUCCESS
        pr.add_stage_run(sr2)

        pr.complete_success()
        summary = pr.summary
        assert "weekly-etl" in summary
        assert "SUCCESS" in summary
        assert "✓" in summary
        assert "ingest" in summary
        assert "transform" in summary

    def test_summary_with_skipped(self):
        pr = PipelineRun(pipeline_name="test")
        pr.start_execution()

        sr1 = StageRun(job_name="a", stage_index=0)
        sr1.start_execution()
        sr1.complete_success()
        sr1.duration_ms = 100
        pr.add_stage_run(sr1)

        sr2 = StageRun(job_name="b", stage_index=1)
        sr2.mark_skipped("disabled")
        pr.add_stage_run(sr2)

        pr.complete_success()
        summary = pr.summary
        assert "⊘" in summary
        assert "skipped" in summary

    def test_summary_with_failure(self):
        pr = PipelineRun(pipeline_name="test")
        pr.start_execution()

        sr1 = StageRun(job_name="a", stage_index=0)
        sr1.start_execution()
        sr1.complete_failure("timeout")
        pr.add_stage_run(sr1)

        pr.complete_failure("Stage a failed")
        summary = pr.summary
        assert "✗" in summary
        assert "FAILED" in summary
        assert "timeout" in summary

    def test_to_dict(self):
        pr = PipelineRun(
            pipeline_name="weekly-etl",
            pipeline_version="2.0.0",
            triggered_by="schedule",
            trigger_data={"cron": "0 1 * * 0"},
            metadata={"team": "data"},
        )
        pr.start_execution()
        sr = StageRun(job_name="ingest", stage_index=0)
        pr.add_stage_run(sr)
        pr.context["raw_data"] = [1, 2, 3]
        pr.complete_success()

        d = pr.to_dict()
        assert d["pipeline_name"] == "weekly-etl"
        assert d["pipeline_version"] == "2.0.0"
        assert d["status"] == "success"
        assert len(d["stage_runs"]) == 1
        assert d["stage_runs"][0]["job_name"] == "ingest"
        assert d["context"] == {"raw_data": [1, 2, 3]}
        assert d["triggered_by"] == "schedule"
        assert d["trigger_data"] == {"cron": "0 1 * * 0"}
        assert d["metadata"] == {"team": "data"}
        assert d["start_time"] is not None
        assert d["end_time"] is not None
        assert d["created_at"] is not None
        assert d["updated_at"] is not None

    def test_from_dict(self):
        data = {
            "pipeline_run_id": "pr-123",
            "pipeline_name": "weekly-etl",
            "pipeline_version": "2.0.0",
            "status": "success",
            "stage_runs": [
                {
                    "stage_run_id": "sr-1",
                    "pipeline_run_id": "pr-123",
                    "job_name": "ingest",
                    "stage_index": 0,
                    "status": "success",
                    "job_run": None,
                    "skipped": False,
                    "skip_reason": "",
                    "error": None,
                    "start_time": "2026-04-12T01:00:00+00:00",
                    "end_time": "2026-04-12T01:01:00+00:00",
                    "duration_ms": 60000,
                    "metadata": {},
                }
            ],
            "context": {"raw": [1]},
            "error": None,
            "start_time": "2026-04-12T01:00:00+00:00",
            "end_time": "2026-04-12T01:02:00+00:00",
            "duration_ms": 120000,
            "triggered_by": "schedule",
            "trigger_data": {},
            "metadata": {},
            "created_at": "2026-04-12T00:59:00+00:00",
            "updated_at": "2026-04-12T01:02:00+00:00",
        }
        pr = PipelineRun.from_dict(data)
        assert pr.pipeline_run_id == "pr-123"
        assert pr.pipeline_name == "weekly-etl"
        assert pr.status == RunStatus.SUCCESS
        assert len(pr.stage_runs) == 1
        assert pr.stage_runs[0].job_name == "ingest"
        assert pr.duration_ms == 120000
        assert pr.context == {"raw": [1]}

    def test_serialization_roundtrip(self):
        pr = PipelineRun(
            pipeline_name="roundtrip",
            pipeline_version="3.0.0",
            triggered_by="webhook",
            trigger_data={"payload": "test"},
            metadata={"env": "staging"},
        )
        pr.start_execution()

        sr1 = StageRun(job_name="a", stage_index=0)
        sr1.start_execution()
        sr1.complete_success()
        pr.add_stage_run(sr1)

        sr2 = StageRun(job_name="b", stage_index=1)
        sr2.mark_skipped("condition false")
        pr.add_stage_run(sr2)

        pr.context["result_a"] = {"count": 42}
        pr.complete_success()

        d = pr.to_dict()
        restored = PipelineRun.from_dict(d)

        assert restored.pipeline_run_id == pr.pipeline_run_id
        assert restored.pipeline_name == "roundtrip"
        assert restored.pipeline_version == "3.0.0"
        assert restored.status == RunStatus.SUCCESS
        assert len(restored.stage_runs) == 2
        assert restored.stage_runs[0].status == RunStatus.SUCCESS
        assert restored.stage_runs[1].skipped is True
        assert restored.stage_runs[1].skip_reason == "condition false"
        assert restored.context == {"result_a": {"count": 42}}
        assert restored.triggered_by == "webhook"
        assert restored.trigger_data == {"payload": "test"}
        assert restored.duration_ms is not None

    def test_repr(self):
        pr = PipelineRun(pipeline_name="my-pipeline")
        r = repr(pr)
        assert "my-pipeline" in r
        assert "pending" in r
        assert "stages=0" in r


# ======================================================================
# Enums ADR-013 : StepType IA + TriggerType.AI
# ======================================================================


class TestAIEnums:
    """Vérifie les nouveaux enums IA (ADR-013) et Connector (ADR-016)."""

    def test_step_type_llm_call(self):
        assert StepType.LLM_CALL.value == "llm_call"
        assert StepType("llm_call") == StepType.LLM_CALL

    def test_step_type_tool_call(self):
        assert StepType.TOOL_CALL.value == "tool_call"
        assert StepType("tool_call") == StepType.TOOL_CALL

    def test_step_type_tool_result(self):
        assert StepType.TOOL_RESULT.value == "tool_result"
        assert StepType("tool_result") == StepType.TOOL_RESULT

    def test_step_type_ai_decision(self):
        assert StepType.AI_DECISION.value == "ai_decision"
        assert StepType("ai_decision") == StepType.AI_DECISION

    def test_step_type_skill_execution(self):
        assert StepType.SKILL_EXECUTION.value == "skill_execution"
        assert StepType("skill_execution") == StepType.SKILL_EXECUTION

    def test_step_type_connector(self):
        assert StepType.CONNECTOR.value == "connector"
        assert StepType("connector") == StepType.CONNECTOR

    def test_trigger_type_ai(self):
        assert TriggerType.AI.value == "ai"
        assert TriggerType("ai") == TriggerType.AI

    def test_all_step_types_complete(self):
        """Vérifie que tous les StepType attendus sont présents."""
        expected = {
            "function",
            "subprocess",
            "http_request",
            "sql_query",
            "human_task",
            "external_task",
            "sub_workflow",
            "connector",
            "llm_call",
            "tool_call",
            "tool_result",
            "ai_decision",
            "skill_execution",
        }
        actual = {st.value for st in StepType}
        assert expected == actual

    def test_all_trigger_types_complete(self):
        """Vérifie que tous les TriggerType attendus sont présents."""
        expected = {
            "manual",
            "schedule",
            "signal",
            "webhook",
            "file_watcher",
            "ai",
        }
        actual = {tt.value for tt in TriggerType}
        assert expected == actual


# ======================================================================
# models/__init__.py exports — Pipeline + PipelineRun
# ======================================================================


class TestPipelineExports:
    """Vérifie que les modèles Pipeline sont exportés dans models/__init__.py."""

    def test_pipeline_importable(self):
        from pyworkflow_engine.models import Pipeline as P

        assert P is Pipeline

    def test_pipeline_stage_importable(self):
        from pyworkflow_engine.models import PipelineStage as PS

        assert PS is PipelineStage

    def test_pipeline_run_importable(self):
        from pyworkflow_engine.models import PipelineRun as PR

        assert PR is PipelineRun

    def test_stage_run_importable(self):
        from pyworkflow_engine.models import StageRun as SR

        assert SR is StageRun

    def test_in_all(self):
        import pyworkflow_engine.models as m

        assert "Pipeline" in m.__all__
        assert "PipelineStage" in m.__all__
        assert "PipelineRun" in m.__all__
        assert "StageRun" in m.__all__

    def test_serialization_wrappers_in_all(self):
        import pyworkflow_engine.models as m

        assert "pipeline_to_dict" in m.__all__
        assert "dict_to_pipeline" in m.__all__
        assert "pipeline_stage_to_dict" in m.__all__
        assert "dict_to_pipeline_stage" in m.__all__
        assert "pipeline_run_to_dict" in m.__all__
        assert "dict_to_pipeline_run" in m.__all__
        assert "stage_run_to_dict" in m.__all__
        assert "dict_to_stage_run" in m.__all__

    def test_serialization_wrappers_work(self):
        from pyworkflow_engine.models import (
            dict_to_pipeline,
            dict_to_pipeline_run,
            dict_to_pipeline_stage,
            dict_to_stage_run,
            pipeline_run_to_dict,
            pipeline_stage_to_dict,
            pipeline_to_dict,
            stage_run_to_dict,
        )

        # Pipeline roundtrip via wrappers
        p = Pipeline(name="test", stages=[PipelineStage(job_name="j1")])
        d = pipeline_to_dict(p)
        assert d["name"] == "test"
        restored_p = dict_to_pipeline(d)
        assert restored_p.name == "test"

        # PipelineStage roundtrip
        s = PipelineStage(job_name="j1")
        ds = pipeline_stage_to_dict(s)
        assert ds["job_name"] == "j1"
        restored_s = dict_to_pipeline_stage(ds)
        assert restored_s.job_name == "j1"

        # PipelineRun roundtrip
        pr = PipelineRun(pipeline_name="test")
        dpr = pipeline_run_to_dict(pr)
        assert dpr["pipeline_name"] == "test"
        restored_pr = dict_to_pipeline_run(dpr)
        assert restored_pr.pipeline_name == "test"

        # StageRun roundtrip
        sr = StageRun(job_name="j1", stage_index=0)
        dsr = stage_run_to_dict(sr)
        assert dsr["job_name"] == "j1"
        restored_sr = dict_to_stage_run(dsr)
        assert restored_sr.job_name == "j1"
