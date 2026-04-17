"""
Tests d'intégration — PipelineRunner + ConnectorStep (Phase 5, ADR-014/ADR-016).

Couverture :
    5.1  PipelineRunner.execute() — pipeline 2 stages, contexte propagé
    5.2  WorkflowEngine.run_pipeline() — délègue correctement
    5.3  WorkflowEngine.run_pipeline_with_storage() — persist chaque JobRun
    5.4  Pipeline avec stage skippé (condition=False)
    5.5  Pipeline avec continue_on_failure sur un stage qui échoue
    5.6  Pipeline zéro stage
    5.7  ConnectorStep : StepExecutionError si pyconnectors absent
    5.8  ConnectorStep : ConnectorOutcome typé retourné si succès (mock)
    5.9  PipelineRun.summary — lisible
    5.10 run_pipeline (bridge compat depuis pipelines/shared/runner.py)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.adapters.steps.connector_step import execute_connector
from pyworkflow_engine.adapters.storage.memory import InMemoryStorage
from pyworkflow_engine.decorators import job, pipeline, stage, step
from pyworkflow_engine.engine.pipeline_runner import PipelineRunner
from pyworkflow_engine.exceptions import StepExecutionError
from pyworkflow_engine.models import Job, Pipeline, RunStatus, Step, StepType
from pyworkflow_engine.models.workflow.connector import ConnectorOutcome, ConnectorRef
from pyworkflow_engine.models.pipeline.pipeline import PipelineStage
from pyworkflow_engine.models.pipeline.pipeline_run import PipelineRun

# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture
def engine() -> WorkflowEngine:
    return WorkflowEngine()


@pytest.fixture
def persistent_engine() -> WorkflowEngine:
    return WorkflowEngine(storage=InMemoryStorage())


def _make_step_job(name: str, output: dict) -> Job:
    """Crée un Job impératif minimal avec un step qui retourne ``output``."""

    def handler(**_):
        return output

    s = Step(name="do_it", step_type=StepType.FUNCTION, handler=handler)
    return Job(name=name, steps=[s])


def _make_failing_job(name: str) -> Job:
    """Crée un Job impératif dont le step lève une exception."""

    def handler(**_):
        raise RuntimeError("intentional failure")

    s = Step(name="fail", step_type=StepType.FUNCTION, handler=handler)
    return Job(name=name, steps=[s])


# ------------------------------------------------------------------------------
# 5.1  PipelineRunner.execute() — deux stages, propagation contexte
# ------------------------------------------------------------------------------


class TestPipelineRunnerExecute:

    def test_two_stages_success(self, engine):
        job_a = _make_step_job("stage-a", {"value": 42})
        job_b = _make_step_job("stage-b", {"doubled": 84})

        p = Pipeline(
            name="two-stage",
            stages=[
                PipelineStage(job_name="stage-a", job=job_a),
                PipelineStage(job_name="stage-b", job=job_b),
            ],
        )

        runner = PipelineRunner(engine=engine)
        result = runner.execute(p)

        assert isinstance(result, PipelineRun)
        assert result.status == RunStatus.SUCCESS
        assert len(result.stage_runs) == 2
        assert result.stage_runs[0].status == RunStatus.SUCCESS
        assert result.stage_runs[1].status == RunStatus.SUCCESS

    def test_context_propagated_between_stages(self, engine):
        """Les sorties de stage A sont propagées dans pipeline_run.context."""

        def produce(**_):
            return {"secret": "xyz789"}

        job_a = Job(
            name="producer",
            steps=[Step(name="produce", step_type=StepType.FUNCTION, handler=produce)],
        )
        job_b = Job(
            name="consumer",
            steps=[
                Step(
                    name="consume",
                    step_type=StepType.FUNCTION,
                    handler=lambda **_: {"ok": True},
                )
            ],
        )

        p = Pipeline(
            name="ctx-prop",
            stages=[
                PipelineStage(job_name="producer", job=job_a),
                PipelineStage(job_name="consumer", job=job_b),
            ],
        )

        runner = PipelineRunner(engine=engine)
        result = runner.execute(p)

        assert result.status == RunStatus.SUCCESS
        # job_run.context["produce"] must be propagated into the pipeline context
        assert "produce" in result.context
        assert result.context["produce"] == {"secret": "xyz789"}

    def test_initial_context_injected(self, engine):
        """Le contexte initial est accessible dans pipeline_run.context."""
        job_a = Job(
            name="date-consumer",
            steps=[
                Step(
                    name="use_date",
                    step_type=StepType.FUNCTION,
                    handler=lambda **_: {"done": True},
                )
            ],
        )
        p = Pipeline(
            name="ctx-init",
            stages=[PipelineStage(job_name="date-consumer", job=job_a)],
        )

        runner = PipelineRunner(engine=engine)
        result = runner.execute(p, initial_context={"ingest_date": "2026-04-12"})

        assert result.status == RunStatus.SUCCESS
        # The initial_context should be in the accumulated pipeline context
        assert result.context.get("ingest_date") == "2026-04-12"

    def test_duration_recorded(self, engine):
        p = Pipeline(
            name="timing",
            stages=[PipelineStage(job_name="fast", job=_make_step_job("fast", {}))],
        )
        runner = PipelineRunner(engine=engine)
        result = runner.execute(p)

        assert result.duration_ms is not None
        assert result.duration_ms >= 0
        assert result.stage_runs[0].duration_ms is not None


# ------------------------------------------------------------------------------
# 5.2  WorkflowEngine.run_pipeline()
# ------------------------------------------------------------------------------


class TestWorkflowEngineRunPipeline:

    def test_run_pipeline_returns_pipeline_run(self, engine):
        p = Pipeline(
            name="simple",
            stages=[
                PipelineStage(
                    job_name="only-stage",
                    job=_make_step_job("only-stage", {"ok": True}),
                )
            ],
        )
        result = engine.run_pipeline(p)

        assert isinstance(result, PipelineRun)
        assert result.status == RunStatus.SUCCESS
        assert result.pipeline_name == "simple"

    def test_run_pipeline_triggered_by_forwarded(self, engine):
        p = Pipeline(
            name="triggered",
            stages=[PipelineStage(job_name="j", job=_make_step_job("j", {}))],
        )
        result = engine.run_pipeline(p, triggered_by="schedule")
        assert result.triggered_by == "schedule"

    def test_run_pipeline_with_decorator_api(self, engine):
        @step(name="greet")
        def greet() -> dict:
            return {"msg": "hello"}

        @job(name="greet-job")
        def greet_job():
            greet()

        @stage(job=greet_job)
        def greet_stage():
            """Single stage: greet."""

        @pipeline(name="greet-pipeline")
        def greet_pipeline():
            greet_stage()

        result = engine.run_pipeline(greet_pipeline.build())
        assert result.status == RunStatus.SUCCESS
        assert result.pipeline_name == "greet-pipeline"
        assert len(result.stage_runs) == 1


# ------------------------------------------------------------------------------
# 5.3  WorkflowEngine.run_pipeline_with_storage()
# ------------------------------------------------------------------------------


class TestRunPipelineWithStorage:

    def test_requires_storage(self, engine):
        p = Pipeline(name="no-storage", stages=[])
        from pyworkflow_engine.exceptions import WorkflowError

        with pytest.raises(WorkflowError, match="No persistence backend"):
            engine.run_pipeline_with_storage(p)

    def test_job_runs_persisted(self, persistent_engine):
        job_obj = _make_step_job("persisted-job", {"stored": True})
        p = Pipeline(
            name="with-storage",
            stages=[PipelineStage(job_name="persisted-job", job=job_obj)],
        )

        result = persistent_engine.run_pipeline_with_storage(p)
        assert result.status == RunStatus.SUCCESS

        # Le JobRun doit être persisté
        stored_runs = persistent_engine.list_job_runs(job_name="persisted-job")
        assert len(stored_runs) >= 1
        assert stored_runs[0].status == RunStatus.SUCCESS


# ------------------------------------------------------------------------------
# 5.4  Stage skippé via condition
# ------------------------------------------------------------------------------


class TestStageSkip:

    def test_condition_false_skips_stage(self, engine):
        p = Pipeline(
            name="conditional",
            stages=[
                PipelineStage(
                    job_name="skipped",
                    job=_make_step_job("skipped", {}),
                    condition=lambda ctx: False,
                ),
            ],
        )
        result = engine.run_pipeline(p)

        assert result.status == RunStatus.SUCCESS  # pipeline réussit quand même
        sr = result.stage_runs[0]
        assert sr.skipped is True
        assert sr.status == RunStatus.CANCELLED

    def test_disabled_stage_skipped(self, engine):
        p = Pipeline(
            name="disabled",
            stages=[
                PipelineStage(
                    job_name="dis",
                    job=_make_step_job("dis", {}),
                    enabled=False,
                ),
            ],
        )
        result = engine.run_pipeline(p)
        assert result.stage_runs[0].skipped is True

    def test_condition_true_runs_stage(self, engine):
        p = Pipeline(
            name="cond-true",
            stages=[
                PipelineStage(
                    job_name="runs",
                    job=_make_step_job("runs", {"x": 1}),
                    condition=lambda ctx: True,
                ),
            ],
        )
        result = engine.run_pipeline(p)
        assert result.stage_runs[0].status == RunStatus.SUCCESS


# ------------------------------------------------------------------------------
# 5.5  continue_on_failure
# ------------------------------------------------------------------------------


class TestContinueOnFailure:

    def test_pipeline_fails_fast_by_default(self, engine):
        """Sans continue_on_failure, le 2e stage ne doit pas s'exécuter."""
        p = Pipeline(
            name="fail-fast",
            stages=[
                PipelineStage(job_name="bad", job=_make_failing_job("bad")),
                PipelineStage(
                    job_name="never-run", job=_make_step_job("never-run", {})
                ),
            ],
        )
        result = engine.run_pipeline(p)
        assert result.status == RunStatus.FAILED
        # Le 2e stage n'a jamais été ajouté car on a breaked
        executed = [sr for sr in result.stage_runs if sr.status != RunStatus.PENDING]
        assert len(executed) == 1

    def test_continue_on_failure_runs_next_stage(self, engine):
        """Avec continue_on_failure=True sur le stage qui échoue,
        le stage suivant doit quand même s'exécuter."""
        p = Pipeline(
            name="continue",
            stages=[
                PipelineStage(
                    job_name="bad",
                    job=_make_failing_job("bad"),
                    continue_on_failure=True,
                ),
                PipelineStage(
                    job_name="still-runs", job=_make_step_job("still-runs", {})
                ),
            ],
        )
        result = engine.run_pipeline(p)
        assert result.status == RunStatus.FAILED  # pipeline globale en échec
        assert len(result.stage_runs) == 2
        assert result.stage_runs[0].status == RunStatus.FAILED
        assert result.stage_runs[1].status == RunStatus.SUCCESS


# ------------------------------------------------------------------------------
# 5.6  Pipeline zéro stage
# ------------------------------------------------------------------------------


class TestEmptyPipeline:

    def test_zero_stages_succeeds(self, engine):
        p = Pipeline(name="empty", stages=[])
        result = engine.run_pipeline(p)
        assert result.status == RunStatus.SUCCESS
        assert result.stage_runs == []


# ------------------------------------------------------------------------------
# 5.7  ConnectorStep — StepExecutionError si pyconnectors absent
# ------------------------------------------------------------------------------


class TestConnectorStepMissingDependency:

    def test_import_error_raises_step_execution_error(self):
        ref = ConnectorRef(connector_name="database.postgresql")

        with (
            patch.dict(
                "sys.modules",
                {
                    "pyconnectors": None,
                    "pyconnectors.config": None,
                    "pyconnectors.factory": None,
                },
            ),
            pytest.raises(StepExecutionError, match="pyconnectors"),
        ):
            execute_connector(ref)


# ------------------------------------------------------------------------------
# 5.8  ConnectorStep — ConnectorOutcome typé avec mock pyconnectors
# ------------------------------------------------------------------------------


class TestConnectorStepWithMock:

    def test_returns_connector_outcome(self):
        ref = ConnectorRef(
            connector_name="http.rest",
            config={"params": {"url": "https://example.com"}},
        )

        # Mock ConnectorResult
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.error = None
        mock_result.data = [{"id": 1}, {"id": 2}]
        mock_result.metadata = {"records_affected": 2}

        mock_connector = MagicMock()
        mock_connector.execute.return_value = mock_result

        mock_config_cls = MagicMock()
        mock_config_cls.from_dict.return_value = MagicMock()

        mock_factory = MagicMock()
        mock_factory.create.return_value = mock_connector

        with patch.dict(
            "sys.modules",
            {
                "pyconnectors": MagicMock(),
                "pyconnectors.config": MagicMock(ConnectorConfig=mock_config_cls),
                "pyconnectors.factory": MagicMock(ConnectorFactory=mock_factory),
            },
        ):
            outcome = execute_connector(ref)

        assert isinstance(outcome, ConnectorOutcome)
        assert outcome.success is True
        assert outcome.connector_name == "http.rest"
        assert outcome.connector_type == "http"
        assert outcome.records_affected == 2
        assert outcome.data_summary == {"type": "list", "count": 2}

    def test_connector_failure_raises_step_execution_error(self):
        ref = ConnectorRef(connector_name="database.postgresql")

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "connection refused"
        mock_result.data = None
        mock_result.metadata = {}

        mock_connector = MagicMock()
        mock_connector.execute.return_value = mock_result

        mock_config_cls = MagicMock()
        mock_config_cls.from_dict.return_value = MagicMock()

        mock_factory = MagicMock()
        mock_factory.create.return_value = mock_connector

        with (
            patch.dict(
                "sys.modules",
                {
                    "pyconnectors": MagicMock(),
                    "pyconnectors.config": MagicMock(ConnectorConfig=mock_config_cls),
                    "pyconnectors.factory": MagicMock(ConnectorFactory=mock_factory),
                },
            ),
            pytest.raises(StepExecutionError, match="connection refused"),
        ):
            execute_connector(ref)


# ------------------------------------------------------------------------------
# 5.9  PipelineRun.summary lisible
# ------------------------------------------------------------------------------


class TestPipelineRunSummary:

    def test_summary_contains_pipeline_name(self, engine):
        p = Pipeline(
            name="my-pipeline",
            stages=[PipelineStage(job_name="s", job=_make_step_job("s", {}))],
        )
        result = engine.run_pipeline(p)
        assert "my-pipeline" in result.summary
        assert "SUCCESS" in result.summary.upper() or "success" in result.summary

    def test_summary_contains_stage_names(self, engine):
        p = Pipeline(
            name="named-stages",
            stages=[
                PipelineStage(job_name="alpha", job=_make_step_job("alpha", {})),
                PipelineStage(job_name="beta", job=_make_step_job("beta", {})),
            ],
        )
        result = engine.run_pipeline(p)
        assert "alpha" in result.summary
        assert "beta" in result.summary

    def test_summary_shows_failure(self, engine):
        p = Pipeline(
            name="fail-summary",
            stages=[PipelineStage(job_name="bad", job=_make_failing_job("bad"))],
        )
        result = engine.run_pipeline(p)
        assert "bad" in result.summary
        assert "FAILED" in result.summary.upper() or "failed" in result.summary


# ------------------------------------------------------------------------------
# 5.10  Bridge compat: pipelines/shared/runner.run_pipeline()
# ------------------------------------------------------------------------------


class TestSharedRunnerBridge:

    def test_run_pipeline_bridge_delegates_to_engine(self, engine):
        from pipelines.shared.runner import run_pipeline

        p = Pipeline(
            name="bridge-test",
            stages=[PipelineStage(job_name="j", job=_make_step_job("j", {"ok": 1}))],
        )
        result = run_pipeline(p, engine=engine)

        assert isinstance(result, PipelineRun)
        assert result.status == RunStatus.SUCCESS
        assert result.pipeline_name == "bridge-test"

    def test_legacy_pipeline_runner_still_works(self):
        """L'ancien PipelineRunner impératif reste fonctionnel."""
        from pipelines.shared.runner import PipelineRunner as LegacyRunner

        job_obj = _make_step_job("legacy", {"out": 1})
        runner = LegacyRunner("legacy-pipeline", engine=WorkflowEngine())
        runner.add_job(job_obj)
        result = runner.execute()
        assert result.success
        assert result.pipeline_name == "legacy-pipeline"
