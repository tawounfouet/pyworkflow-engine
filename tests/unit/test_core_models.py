"""
Tests unitaires pour les modèles core.

Teste tous les modèles de base du système de workflow :
- Enums et leurs helpers
- Modèles design-time (Job, Step, SubJob)
- Modèles runtime (JobRun, StepRun, StepLog)
- Validation et edge cases
"""

import pytest
from datetime import datetime, timedelta, timezone
from dataclasses import FrozenInstanceError

from pyworkflow_engine.core.models import (
    # Enums
    TriggerType,
    StepType,
    ExecutorType,
    RunStatus,
    Priority,
    is_terminal,
    is_suspended,
    is_active,
    can_resume,
    can_cancel,
    TERMINAL_STATUSES,
    SUSPENDED_STATUSES,
    ACTIVE_STATUSES,
    # Design-time
    Step,
    SubJob,
    Job,
    # Runtime
    StepLog,
    StepRun,
    JobRun,
    utc_now,
    generate_id,
)


class TestEnums:
    """Tests pour les enums et leurs helpers."""

    def test_trigger_types(self):
        """Test des types de triggers."""
        assert TriggerType.MANUAL.value == "manual"
        assert TriggerType.SCHEDULE.value == "schedule"
        assert TriggerType.SIGNAL.value == "signal"
        assert TriggerType.WEBHOOK.value == "webhook"
        assert TriggerType.FILE_WATCHER.value == "file_watcher"

    def test_step_types(self):
        """Test des types de steps."""
        assert StepType.FUNCTION.value == "function"
        assert StepType.SUBPROCESS.value == "subprocess"
        assert StepType.HTTP_REQUEST.value == "http_request"
        assert StepType.SQL_QUERY.value == "sql_query"
        assert StepType.HUMAN_TASK.value == "human_task"
        assert StepType.EXTERNAL_TASK.value == "external_task"
        assert StepType.SUB_WORKFLOW.value == "sub_workflow"

    def test_executor_types(self):
        """Test des types d'executors."""
        assert ExecutorType.LOCAL.value == "local"
        assert ExecutorType.THREAD.value == "thread"
        assert ExecutorType.PROCESS.value == "process"
        assert ExecutorType.ASYNC.value == "async"
        assert ExecutorType.CELERY.value == "celery"
        assert ExecutorType.KUBERNETES.value == "kubernetes"
        assert ExecutorType.HUMAN.value == "human"
        assert ExecutorType.EXTERNAL.value == "external"

    def test_run_statuses(self):
        """Test des statuts d'exécution."""
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.RUNNING.value == "running"
        assert RunStatus.SUCCESS.value == "success"
        assert RunStatus.FAILED.value == "failed"
        assert RunStatus.CANCELLED.value == "cancelled"
        assert RunStatus.WAITING_HUMAN.value == "waiting_human"
        assert RunStatus.WAITING_EXTERNAL.value == "waiting_external"
        assert RunStatus.SUSPENDED.value == "suspended"
        assert RunStatus.TIMEOUT.value == "timeout"

    def test_priorities(self):
        """Test des priorités."""
        assert Priority.LOW.value == 1
        assert Priority.NORMAL.value == 5
        assert Priority.HIGH.value == 10
        assert Priority.CRITICAL.value == 20

    def test_status_helpers(self):
        """Test des fonctions d'aide pour les statuts."""
        # Terminal statuses
        assert is_terminal(RunStatus.SUCCESS)
        assert is_terminal(RunStatus.FAILED)
        assert is_terminal(RunStatus.CANCELLED)
        assert is_terminal(RunStatus.TIMEOUT)
        assert not is_terminal(RunStatus.PENDING)
        assert not is_terminal(RunStatus.RUNNING)
        assert not is_terminal(RunStatus.SUSPENDED)

        # Suspended statuses
        assert is_suspended(RunStatus.WAITING_HUMAN)
        assert is_suspended(RunStatus.WAITING_EXTERNAL)
        assert is_suspended(RunStatus.SUSPENDED)
        assert not is_suspended(RunStatus.SUCCESS)
        assert not is_suspended(RunStatus.RUNNING)

        # Active statuses
        assert is_active(RunStatus.PENDING)
        assert is_active(RunStatus.RUNNING)
        assert not is_active(RunStatus.SUCCESS)
        assert not is_active(RunStatus.SUSPENDED)

        # Can resume
        assert can_resume(RunStatus.SUSPENDED)
        assert can_resume(RunStatus.WAITING_HUMAN)
        assert can_resume(RunStatus.WAITING_EXTERNAL)
        assert not can_resume(RunStatus.SUCCESS)
        assert not can_resume(RunStatus.FAILED)

        # Can cancel
        assert can_cancel(RunStatus.PENDING)
        assert can_cancel(RunStatus.RUNNING)
        assert can_cancel(RunStatus.SUSPENDED)
        assert not can_cancel(RunStatus.SUCCESS)
        assert not can_cancel(RunStatus.FAILED)

    def test_status_sets(self):
        """Test des ensembles de statuts."""
        assert RunStatus.SUCCESS in TERMINAL_STATUSES
        assert RunStatus.FAILED in TERMINAL_STATUSES
        assert RunStatus.CANCELLED in TERMINAL_STATUSES
        assert RunStatus.TIMEOUT in TERMINAL_STATUSES

        assert RunStatus.WAITING_HUMAN in SUSPENDED_STATUSES
        assert RunStatus.WAITING_EXTERNAL in SUSPENDED_STATUSES
        assert RunStatus.SUSPENDED in SUSPENDED_STATUSES

        assert RunStatus.PENDING in ACTIVE_STATUSES
        assert RunStatus.RUNNING in ACTIVE_STATUSES


class TestStep:
    """Tests pour le modèle Step."""

    def test_basic_step_creation(self):
        """Test de création basique d'une step."""

        def dummy_func():
            return {"result": "ok"}

        step = Step(name="test_step", step_type=StepType.FUNCTION, callable=dummy_func)

        assert step.name == "test_step"
        assert step.step_type == StepType.FUNCTION
        assert step.callable == dummy_func
        assert step.config == {}
        assert step.dependencies == []
        assert step.executor_type == ExecutorType.LOCAL
        assert step.timeout is None
        assert step.retry_count == 0
        assert step.retry_delay == timedelta(seconds=1)
        assert step.condition is None
        assert step.metadata == {}

    def test_step_with_dependencies(self):
        """Test step avec dépendances."""
        step = Step(
            name="dependent_step",
            step_type=StepType.FUNCTION,
            callable=lambda: None,
            dependencies=["step1", "step2"],
        )

        assert step.dependencies == ["step1", "step2"]

    def test_step_with_config(self):
        """Test step avec configuration."""
        config = {"url": "https://api.example.com", "method": "POST"}
        step = Step(name="http_step", step_type=StepType.HTTP_REQUEST, config=config)

        assert step.config == config
        assert step.callable is None  # HTTP steps n'ont pas de callable

    def test_step_validation_function_without_callable(self):
        """Test validation : FUNCTION step sans callable."""
        with pytest.raises(ValueError, match="StepType.FUNCTION requires callable"):
            Step(name="bad_step", step_type=StepType.FUNCTION, callable=None)

    def test_step_validation_negative_retry_count(self):
        """Test validation : retry_count négatif."""
        with pytest.raises(ValueError, match="retry_count must be >= 0"):
            Step(
                name="bad_step",
                step_type=StepType.FUNCTION,
                callable=lambda: None,
                retry_count=-1,
            )

    def test_step_validation_self_dependency(self):
        """Test validation : dépendance sur soi-même."""
        with pytest.raises(ValueError, match="cannot depend on itself"):
            Step(
                name="self_dep_step",
                step_type=StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["self_dep_step"],
            )

    def test_step_immutability(self):
        """Test que Step est immuable."""
        step = Step(name="test", step_type=StepType.FUNCTION, callable=lambda: None)

        with pytest.raises(FrozenInstanceError):
            step.name = "changed"

    def test_step_with_condition(self):
        """Test step avec condition."""

        def condition_func(context):
            return context.get("enable_step", True)

        step = Step(
            name="conditional_step",
            step_type=StepType.FUNCTION,
            callable=lambda: None,
            condition=condition_func,
        )

        assert step.condition == condition_func

    def test_step_with_timeout(self):
        """Test step avec timeout."""
        step = Step(
            name="timeout_step",
            step_type=StepType.FUNCTION,
            callable=lambda: None,
            timeout=timedelta(minutes=5),
        )

        assert step.timeout == timedelta(minutes=5)


class TestSubJob:
    """Tests pour le modèle SubJob."""

    def test_basic_subjob_creation(self):
        """Test de création basique d'un SubJob."""
        sub_job = SubJob(job_name="child_workflow")

        assert sub_job.job_name == "child_workflow"
        assert sub_job.input_mapping == {}
        assert sub_job.output_mapping == {}
        assert sub_job.inherit_context is True

    def test_subjob_with_mappings(self):
        """Test SubJob avec mappings."""
        sub_job = SubJob(
            job_name="data_processor",
            input_mapping={"data": "raw_data"},
            output_mapping={"result": "processed_data"},
            inherit_context=False,
        )

        assert sub_job.input_mapping == {"data": "raw_data"}
        assert sub_job.output_mapping == {"result": "processed_data"}
        assert sub_job.inherit_context is False

    def test_subjob_immutability(self):
        """Test que SubJob est immuable."""
        sub_job = SubJob(job_name="test")

        with pytest.raises(FrozenInstanceError):
            sub_job.job_name = "changed"


class TestJob:
    """Tests pour le modèle Job."""

    def test_basic_job_creation(self):
        """Test de création basique d'un Job."""
        job = Job(name="test_job")

        assert job.name == "test_job"
        assert job.description == ""
        assert job.steps == []
        assert job.sub_jobs == []
        assert job.triggers == [TriggerType.MANUAL]
        assert job.default_executor == ExecutorType.LOCAL
        assert job.priority == Priority.NORMAL
        assert job.timeout is None
        assert job.max_concurrent_steps == 10
        assert job.input_schema is None
        assert job.output_schema is None
        assert job.tags == []
        assert job.metadata == {}
        assert job.version == "1.0.0"
        assert job.enabled is True

    def test_job_with_steps(self):
        """Test Job avec steps."""

        def step1_func():
            return {"data": "from_step1"}

        def step2_func():
            return {"processed": True}

        steps = [
            Step("step1", StepType.FUNCTION, callable=step1_func),
            Step(
                "step2", StepType.FUNCTION, callable=step2_func, dependencies=["step1"]
            ),
        ]

        job = Job(name="multi_step_job", steps=steps)

        assert len(job.steps) == 2
        assert job.steps[0].name == "step1"
        assert job.steps[1].name == "step2"
        assert job.steps[1].dependencies == ["step1"]

    def test_job_validation_empty_name(self):
        """Test validation : nom vide."""
        with pytest.raises(ValueError, match="Job name cannot be empty"):
            Job(name="")

    def test_job_validation_invalid_name(self):
        """Test validation : nom invalide."""
        with pytest.raises(
            ValueError, match="Job name must contain only alphanumeric characters"
        ):
            Job(name="invalid name with spaces!")

    def test_job_valid_names(self):
        """Test noms valides."""
        # Ces noms doivent être acceptés
        valid_names = ["simple", "with_underscore", "with-dash", "alpha123"]

        for name in valid_names:
            job = Job(name=name)  # Ne doit pas lever d'exception
            assert job.name == name

    def test_job_validation_duplicate_step_names(self):
        """Test validation : noms de steps dupliqués."""
        steps = [
            Step("duplicate", StepType.FUNCTION, callable=lambda: None),
            Step("duplicate", StepType.FUNCTION, callable=lambda: None),
        ]

        with pytest.raises(ValueError, match="Step names must be unique"):
            Job(name="test_job", steps=steps)

    def test_job_validation_missing_dependency(self):
        """Test validation : dépendance manquante."""
        steps = [
            Step("step1", StepType.FUNCTION, callable=lambda: None),
            Step(
                "step2",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["nonexistent"],
            ),
        ]

        with pytest.raises(ValueError, match="dependency 'nonexistent' not found"):
            Job(name="test_job", steps=steps)

    def test_job_validation_max_concurrent_steps(self):
        """Test validation : max_concurrent_steps invalide."""
        with pytest.raises(ValueError, match="max_concurrent_steps must be positive"):
            Job(name="test_job", max_concurrent_steps=0)

    def test_job_get_step(self):
        """Test récupération d'une step par nom."""
        step = Step("target_step", StepType.FUNCTION, callable=lambda: None)
        job = Job(name="test_job", steps=[step])

        found = job.get_step("target_step")
        assert found == step

        not_found = job.get_step("nonexistent")
        assert not_found is None

    def test_job_get_dependencies(self):
        """Test récupération des dépendances."""
        steps = [
            Step("step1", StepType.FUNCTION, callable=lambda: None),
            Step(
                "step2",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step1"],
            ),
            Step(
                "step3",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step1", "step2"],
            ),
        ]
        job = Job(name="test_job", steps=steps)

        assert job.get_dependencies("step1") == []
        assert job.get_dependencies("step2") == ["step1"]
        assert job.get_dependencies("step3") == ["step1", "step2"]
        assert job.get_dependencies("nonexistent") == []

    def test_job_get_dependents(self):
        """Test récupération des dépendants."""
        steps = [
            Step("step1", StepType.FUNCTION, callable=lambda: None),
            Step(
                "step2",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step1"],
            ),
            Step(
                "step3",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step1"],
            ),
        ]
        job = Job(name="test_job", steps=steps)

        dependents = job.get_dependents("step1")
        assert set(dependents) == {"step2", "step3"}

        assert job.get_dependents("step2") == []
        assert job.get_dependents("nonexistent") == []

    def test_job_entry_and_exit_steps(self):
        """Test identification des steps d'entrée et de sortie."""
        steps = [
            Step("entry1", StepType.FUNCTION, callable=lambda: None),
            Step("entry2", StepType.FUNCTION, callable=lambda: None),
            Step(
                "middle",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["entry1"],
            ),
            Step(
                "exit",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["middle"],
            ),
        ]
        job = Job(name="test_job", steps=steps)

        entry_steps = job.get_entry_steps()
        assert set(entry_steps) == {"entry1", "entry2"}

        exit_steps = job.get_exit_steps()
        assert set(exit_steps) == {"entry2", "exit"}

    def test_job_has_cycles_simple(self):
        """Test détection de cycles simple."""
        # Job sans cycles
        steps = [
            Step("step1", StepType.FUNCTION, callable=lambda: None),
            Step(
                "step2",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step1"],
            ),
            Step(
                "step3",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step2"],
            ),
        ]
        job = Job(name="test_job", steps=steps)

        assert not job.has_cycles()

    def test_job_has_cycles_with_cycle(self):
        """Test détection de cycles avec cycle."""
        # Job avec cycle : step1 -> step2 -> step3 -> step1
        steps = [
            Step(
                "step1",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step3"],
            ),
            Step(
                "step2",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step1"],
            ),
            Step(
                "step3",
                StepType.FUNCTION,
                callable=lambda: None,
                dependencies=["step2"],
            ),
        ]
        job = Job(name="test_job", steps=steps)

        assert job.has_cycles()

    def test_job_immutability(self):
        """Test que Job est immuable."""
        job = Job(name="test")

        with pytest.raises(FrozenInstanceError):
            job.name = "changed"


class TestStepLog:
    """Tests pour le modèle StepLog."""

    def test_basic_step_log_creation(self):
        """Test de création basique d'un StepLog."""
        timestamp = datetime.now(timezone.utc)
        log = StepLog(timestamp=timestamp, level="INFO", message="Step started")

        assert log.timestamp == timestamp
        assert log.level == "INFO"
        assert log.message == "Step started"
        assert log.data == {}
        assert log.source == "step"

    def test_step_log_with_data(self):
        """Test StepLog avec données."""
        timestamp = datetime.now(timezone.utc)
        data = {"duration": 100, "records_processed": 50}
        log = StepLog(
            timestamp=timestamp,
            level="INFO",
            message="Processing complete",
            data=data,
            source="processor",
        )

        assert log.data == data
        assert log.source == "processor"

    def test_step_log_validation_invalid_level(self):
        """Test validation : niveau de log invalide."""
        with pytest.raises(ValueError, match="Invalid log level"):
            StepLog(
                timestamp=datetime.now(timezone.utc), level="INVALID", message="test"
            )

    def test_step_log_valid_levels(self):
        """Test niveaux de log valides."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        timestamp = datetime.now(timezone.utc)

        for level in valid_levels:
            log = StepLog(timestamp=timestamp, level=level, message="test")
            assert log.level == level


class TestStepRun:
    """Tests pour le modèle StepRun."""

    def test_basic_step_run_creation(self):
        """Test de création basique d'un StepRun."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")

        assert step_run.step_name == "test_step"
        assert step_run.job_run_id == "job-123"
        assert step_run.status == RunStatus.PENDING
        assert step_run.executor_type == ExecutorType.LOCAL
        assert step_run.input_data == {}
        assert step_run.output_data == {}
        assert step_run.error is None
        assert step_run.start_time is None
        assert step_run.end_time is None
        assert step_run.duration_ms is None
        assert step_run.retry_count == 0
        assert step_run.logs == []
        assert len(step_run.step_run_id) > 0  # UUID généré

    def test_step_run_start_execution(self):
        """Test démarrage d'exécution."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")

        before_start = datetime.now(timezone.utc)
        step_run.start_execution()
        after_start = datetime.now(timezone.utc)

        assert step_run.status == RunStatus.RUNNING
        assert step_run.start_time is not None
        assert before_start <= step_run.start_time <= after_start
        assert len(step_run.logs) == 1
        assert step_run.logs[0].level == "INFO"
        assert "Starting execution" in step_run.logs[0].message

    def test_step_run_complete_success(self):
        """Test completion réussie."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")
        step_run.start_execution()

        output_data = {"result": "success", "count": 42}
        step_run.complete_success(output_data)

        assert step_run.status == RunStatus.SUCCESS
        assert step_run.output_data == output_data
        assert step_run.end_time is not None
        assert step_run.duration_ms is not None
        assert step_run.duration_ms >= 0
        assert len(step_run.logs) == 2
        assert "completed successfully" in step_run.logs[1].message

    def test_step_run_complete_failure(self):
        """Test completion échouée."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")
        step_run.start_execution()

        error_message = "Division by zero"
        step_run.complete_failure(error_message)

        assert step_run.status == RunStatus.FAILED
        assert step_run.error == error_message
        assert step_run.end_time is not None
        assert step_run.duration_ms is not None
        assert len(step_run.logs) == 2
        assert "failed" in step_run.logs[1].message

    def test_step_run_suspend(self):
        """Test suspension."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")

        reason = "Waiting for approval"
        step_run.suspend(reason)

        assert step_run.status == RunStatus.SUSPENDED
        assert len(step_run.logs) == 1
        assert "suspended" in step_run.logs[0].message

    def test_step_run_wait_human(self):
        """Test attente humaine."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")

        reason = "Manual approval required"
        step_run.wait_human(reason)

        assert step_run.status == RunStatus.WAITING_HUMAN
        assert len(step_run.logs) == 1
        assert "waiting for human" in step_run.logs[0].message

    def test_step_run_wait_external(self):
        """Test attente externe."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")

        reason = "API callback expected"
        step_run.wait_external(reason)

        assert step_run.status == RunStatus.WAITING_EXTERNAL
        assert len(step_run.logs) == 1
        assert "waiting for external" in step_run.logs[0].message

    def test_step_run_cancel(self):
        """Test annulation."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")
        step_run.start_execution()

        step_run.cancel()

        assert step_run.status == RunStatus.CANCELLED
        assert step_run.end_time is not None
        assert step_run.duration_ms is not None

    def test_step_run_timeout(self):
        """Test timeout."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")
        step_run.start_execution()

        step_run.timeout()

        assert step_run.status == RunStatus.TIMEOUT
        assert step_run.end_time is not None
        assert step_run.duration_ms is not None

    def test_step_run_add_log(self):
        """Test ajout de log."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")

        data = {"key": "value"}
        step_run.add_log("WARNING", "Custom message", data)

        assert len(step_run.logs) == 1
        log = step_run.logs[0]
        assert log.level == "WARNING"
        assert log.message == "Custom message"
        assert log.data == data
        assert log.source == "step:test_step"

    def test_step_run_properties(self):
        """Test propriétés calculées."""
        step_run = StepRun(step_name="test_step", job_run_id="job-123")

        # État initial
        assert not step_run.is_terminal
        assert not step_run.is_suspended
        assert not step_run.can_resume

        # Après suspension
        step_run.suspend("test")
        assert not step_run.is_terminal
        assert step_run.is_suspended
        assert step_run.can_resume

        # Après completion
        step_run.complete_success({})
        assert step_run.is_terminal
        assert not step_run.is_suspended
        assert not step_run.can_resume


class TestJobRun:
    """Tests pour le modèle JobRun."""

    def test_basic_job_run_creation(self):
        """Test de création basique d'un JobRun."""
        job_run = JobRun(job_name="test_job")

        assert job_run.job_name == "test_job"
        assert job_run.job_version == "1.0.0"
        assert job_run.status == RunStatus.PENDING
        assert job_run.input_data == {}
        assert job_run.output_data == {}
        assert job_run.context == {}
        assert job_run.step_runs == []
        assert job_run.error is None
        assert job_run.start_time is None
        assert job_run.end_time is None
        assert job_run.duration_ms is None
        assert job_run.triggered_by == "manual"
        assert job_run.trigger_data == {}
        assert job_run.priority == 5  # Priority.NORMAL.value
        assert job_run.executor_config == {}
        assert job_run.metadata == {}
        assert len(job_run.job_run_id) > 0  # UUID généré
        assert job_run.created_at is not None
        assert job_run.updated_at is not None

    def test_job_run_start_execution(self):
        """Test démarrage d'exécution."""
        job_run = JobRun(job_name="test_job")

        before_start = datetime.now(timezone.utc)
        job_run.start_execution()
        after_start = datetime.now(timezone.utc)

        assert job_run.status == RunStatus.RUNNING
        assert job_run.start_time is not None
        assert before_start <= job_run.start_time <= after_start
        assert job_run.updated_at is not None

    def test_job_run_complete_success(self):
        """Test completion réussie."""
        job_run = JobRun(job_name="test_job")
        job_run.start_execution()

        output_data = {"final_result": "success"}
        job_run.complete_success(output_data)

        assert job_run.status == RunStatus.SUCCESS
        assert job_run.output_data == output_data
        assert job_run.end_time is not None
        assert job_run.duration_ms is not None

    def test_job_run_complete_failure(self):
        """Test completion échouée."""
        job_run = JobRun(job_name="test_job")
        job_run.start_execution()

        error_message = "Critical error in workflow"
        job_run.complete_failure(error_message)

        assert job_run.status == RunStatus.FAILED
        assert job_run.error == error_message
        assert job_run.end_time is not None

    def test_job_run_step_management(self):
        """Test gestion des step runs."""
        job_run = JobRun(job_name="test_job")

        # Ajout d'une step run
        step_run = StepRun(step_name="step1")
        job_run.add_step_run(step_run)

        assert len(job_run.step_runs) == 1
        assert step_run.job_run_id == job_run.job_run_id

        # Récupération par nom
        found = job_run.get_step_run("step1")
        assert found == step_run

        not_found = job_run.get_step_run("nonexistent")
        assert not_found is None

    def test_job_run_step_filtering(self):
        """Test filtrage des step runs."""
        job_run = JobRun(job_name="test_job")

        # Création de plusieurs step runs avec différents statuts
        step_run1 = StepRun(step_name="step1")
        step_run1.complete_success({"result": "ok"})

        step_run2 = StepRun(step_name="step2")
        step_run2.complete_failure("error")

        step_run3 = StepRun(step_name="step3")
        step_run3.complete_success({"result": "ok"})

        job_run.add_step_run(step_run1)
        job_run.add_step_run(step_run2)
        job_run.add_step_run(step_run3)

        # Test filtrage par statut
        success_runs = job_run.get_step_runs_by_status(RunStatus.SUCCESS)
        assert len(success_runs) == 2
        assert step_run1 in success_runs
        assert step_run3 in success_runs

        failed_runs = job_run.get_step_runs_by_status(RunStatus.FAILED)
        assert len(failed_runs) == 1
        assert step_run2 in failed_runs

        # Test méthodes de convenance
        completed_runs = job_run.get_completed_step_runs()
        assert len(completed_runs) == 2

        failed_runs = job_run.get_failed_step_runs()
        assert len(failed_runs) == 1

    def test_job_run_context_update(self):
        """Test mise à jour du contexte."""
        job_run = JobRun(job_name="test_job")

        output_data = {"processed_count": 100}
        job_run.update_context("step1", output_data)

        assert job_run.context["step1"] == output_data
        assert job_run.updated_at is not None

    def test_job_run_progress_calculation(self):
        """Test calcul du pourcentage de progression."""
        job_run = JobRun(job_name="test_job")

        # Aucune step = 0%
        assert job_run.progress_percentage == 0.0

        # Ajout de steps
        step_run1 = StepRun(step_name="step1")
        step_run2 = StepRun(step_name="step2")
        step_run3 = StepRun(step_name="step3")

        job_run.add_step_run(step_run1)
        job_run.add_step_run(step_run2)
        job_run.add_step_run(step_run3)

        # Aucune step terminée = 0%
        assert job_run.progress_percentage == 0.0

        # 1 step terminée = 33.33%
        step_run1.complete_success({})
        assert abs(job_run.progress_percentage - 33.33) < 0.1

        # 2 steps terminées = 66.67%
        step_run2.complete_failure("error")
        assert abs(job_run.progress_percentage - 66.67) < 0.1

        # 3 steps terminées = 100%
        step_run3.complete_success({})
        assert job_run.progress_percentage == 100.0

    def test_job_run_properties(self):
        """Test propriétés calculées."""
        job_run = JobRun(job_name="test_job")

        # État initial
        assert not job_run.is_terminal
        assert not job_run.is_suspended
        assert not job_run.can_resume

        # Après suspension
        job_run.suspend("test")
        assert not job_run.is_terminal
        assert job_run.is_suspended
        assert job_run.can_resume

        # Après completion
        job_run.complete_success({})
        assert job_run.is_terminal
        assert not job_run.is_suspended
        assert not job_run.can_resume


class TestUtilities:
    """Tests pour les fonctions utilitaires."""

    def test_utc_now(self):
        """Test fonction utc_now."""
        before = datetime.now(timezone.utc)
        now = utc_now()
        after = datetime.now(timezone.utc)

        assert before <= now <= after
        assert now.tzinfo == timezone.utc

    def test_generate_id(self):
        """Test génération d'ID unique."""
        id1 = generate_id()
        id2 = generate_id()

        assert id1 != id2
        assert len(id1) > 0
        assert len(id2) > 0
        assert isinstance(id1, str)
        assert isinstance(id2, str)

        # Vérifier format UUID
        import uuid

        uuid.UUID(id1)  # Lèvera une exception si pas un UUID valide
        uuid.UUID(id2)  # Lèvera une exception si pas un UUID valide
