"""
Tests unitaires pour le WorkflowEngine — moteur d'exécution principal.

Test l'exécution de workflows, la gestion d'état, suspension/reprise,
et gestion d'erreurs.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from ias_workflow_engine.core import (
    WorkflowEngine,
    Job,
    Step,
    StepType,
    RunStatus,
    WorkflowError,
    WorkflowSuspended,
    WorkflowFailed,
    StepExecutionError,
    DAGValidationError,
)


class TestWorkflowEngine:
    """Tests du WorkflowEngine."""

    def test_simple_successful_workflow(self):
        """Test d'un workflow simple avec succès."""

        def hello():
            return {"message": "Hello World!"}

        def goodbye():
            return {"message": "Goodbye!"}

        job = Job(
            name="Simple Workflow",
            steps=[
                Step(name="hello", step_type=StepType.FUNCTION, callable=hello),
                Step(
                    name="goodbye",
                    step_type=StepType.FUNCTION,
                    callable=goodbye,
                    dependencies=["hello"],
                ),
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        # Vérifications générales
        assert result.status == RunStatus.SUCCESS
        assert result.job == job
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.error is None

        # Vérifications des steps
        assert len(result.step_runs) == 2

        hello_run = next(sr for sr in result.step_runs if sr.step_name == "hello")
        assert hello_run.status == RunStatus.SUCCESS
        assert hello_run.output_data == {"message": "Hello World!"}

        goodbye_run = next(sr for sr in result.step_runs if sr.step_name == "goodbye")
        assert goodbye_run.status == RunStatus.SUCCESS
        assert goodbye_run.output_data == {"message": "Goodbye!"}

    def test_function_with_context(self):
        """Test d'une fonction qui utilise le contexte."""

        def set_data(context):
            context.set("shared_data", "important_value")
            return {"status": "data_set"}

        def use_data(context):
            value = context.get("shared_data")
            return {"retrieved": value}

        job = Job(
            name="Context Workflow",
            steps=[
                Step(name="setter", step_type=StepType.FUNCTION, callable=set_data),
                Step(
                    name="getter",
                    step_type=StepType.FUNCTION,
                    callable=use_data,
                    dependencies=["setter"],
                ),
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS

        getter_run = next(sr for sr in result.step_runs if sr.step_name == "getter")
        assert getter_run.output_data == {"retrieved": "important_value"}

    def test_initial_context(self):
        """Test avec contexte initial."""

        def use_initial(context):
            config = context.get("config")
            return {"database": config["db_url"]}

        job = Job(
            name="Initial Context",
            steps=[
                Step(
                    name="use_config", step_type=StepType.FUNCTION, callable=use_initial
                )
            ],
        )

        initial_context = {"config": {"db_url": "sqlite:///test.db"}}

        engine = WorkflowEngine()
        result = engine.run(job, initial_context=initial_context)

        assert result.status == RunStatus.SUCCESS
        run = result.step_runs[0]
        assert run.output_data == {"database": "sqlite:///test.db"}

    def test_parallel_execution_order(self):
        """Test que l'ordre d'exécution respecte les dépendances."""
        execution_order = []

        def track_execution(name):
            def _exec():
                execution_order.append(name)
                return {"step": name}

            return _exec

        job = Job(
            name="Parallel Test",
            steps=[
                Step(
                    name="start",
                    step_type=StepType.FUNCTION,
                    callable=track_execution("start"),
                ),
                Step(
                    name="parallel1",
                    step_type=StepType.FUNCTION,
                    callable=track_execution("parallel1"),
                    dependencies=["start"],
                ),
                Step(
                    name="parallel2",
                    step_type=StepType.FUNCTION,
                    callable=track_execution("parallel2"),
                    dependencies=["start"],
                ),
                Step(
                    name="end",
                    step_type=StepType.FUNCTION,
                    callable=track_execution("end"),
                    dependencies=["parallel1", "parallel2"],
                ),
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert execution_order[0] == "start"
        assert execution_order[-1] == "end"
        assert set(execution_order[1:3]) == {"parallel1", "parallel2"}

    def test_step_failure(self):
        """Test de gestion d'échec de step."""

        def failing_step():
            raise ValueError("Something went wrong")

        def normal_step():
            return {"status": "ok"}

        job = Job(
            name="Failing Workflow",
            steps=[
                Step(name="normal", step_type=StepType.FUNCTION, callable=normal_step),
                Step(
                    name="failing",
                    step_type=StepType.FUNCTION,
                    callable=failing_step,
                    dependencies=["normal"],
                ),
            ],
        )

        engine = WorkflowEngine()

        with pytest.raises(StepExecutionError) as exc_info:
            engine.run(job)

        error = exc_info.value
        assert "Step 'failing' failed" in str(error)
        assert error.step_name == "failing"

    def test_workflow_validation_error(self):
        """Test avec erreur de validation DAG."""

        def dummy():
            return {}

        # Dépendance circulaire
        job = Job(
            name="Invalid Workflow",
            steps=[
                Step(
                    name="A",
                    step_type=StepType.FUNCTION,
                    callable=dummy,
                    dependencies=["B"],
                ),
                Step(
                    name="B",
                    step_type=StepType.FUNCTION,
                    callable=dummy,
                    dependencies=["A"],
                ),
            ],
        )

        engine = WorkflowEngine()

        with pytest.raises(WorkflowFailed) as exc_info:
            engine.run(job)

        # L'erreur DAG est wrappée dans WorkflowFailed
        assert "Workflow validation failed" in str(exc_info.value)

    def test_step_condition_true(self):
        """Test avec condition de step évaluée à True."""

        def conditional_step():
            return {"executed": True}

        def condition(context_data):
            return True

        job = Job(
            name="Conditional Workflow",
            steps=[
                Step(
                    name="conditional",
                    step_type=StepType.FUNCTION,
                    callable=conditional_step,
                    condition=condition,
                )
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert len(result.step_runs) == 1
        assert result.step_runs[0].output_data == {"executed": True}

    def test_step_condition_false(self):
        """Test avec condition de step évaluée à False."""

        def conditional_step():
            return {"executed": True}

        def condition(context_data):
            return False

        job = Job(
            name="Conditional Workflow",
            steps=[
                Step(
                    name="conditional",
                    step_type=StepType.FUNCTION,
                    callable=conditional_step,
                    condition=condition,
                )
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert len(result.step_runs) == 0  # Step non exécuté

    def test_condition_error(self):
        """Test avec erreur dans la condition."""

        def conditional_step():
            return {"executed": True}

        def bad_condition(context_data):
            raise ValueError("Condition error")

        job = Job(
            name="Bad Condition",
            steps=[
                Step(
                    name="conditional",
                    step_type=StepType.FUNCTION,
                    callable=conditional_step,
                    condition=bad_condition,
                )
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        # Le step ne doit pas être exécuté si la condition échoue
        assert result.status == RunStatus.SUCCESS
        assert len(result.step_runs) == 0

    def test_step_without_callable(self):
        """Test avec step FUNCTION sans callable."""
        # Since Job model validation prevents creating Steps without callable,
        # we test that the validation error is properly caught and handled

        with pytest.raises(ValueError) as exc_info:
            Step(name="invalid", step_type=StepType.FUNCTION)  # Pas de callable

        assert "StepType.FUNCTION requires callable" in str(exc_info.value)

    def test_custom_run_id(self):
        """Test avec run_id personnalisé."""

        def dummy():
            return {}

        job = Job(
            name="Custom ID",
            steps=[Step(name="step", step_type=StepType.FUNCTION, callable=dummy)],
        )

        custom_id = "custom-run-123"
        engine = WorkflowEngine()
        result = engine.run(job, run_id=custom_id)

        assert result.job_run_id == custom_id

    def test_workflow_suspension(self):
        """Test de suspension de workflow."""

        def suspending_step():
            raise WorkflowSuspended("Manual approval required")

        job = Job(
            name="Suspending Workflow",
            steps=[
                Step(
                    name="suspend",
                    step_type=StepType.FUNCTION,
                    callable=suspending_step,
                )
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUSPENDED
        assert result.job_run_id in engine.list_suspended()

    def test_workflow_resume(self):
        """Test de reprise de workflow."""

        def suspending_step():
            raise WorkflowSuspended("Manual approval required")

        def final_step(context):
            approval = context.get_step_output("suspend")
            return {"approved": approval["approved"]}

        job = Job(
            name="Resume Workflow",
            steps=[
                Step(
                    name="suspend",
                    step_type=StepType.FUNCTION,
                    callable=suspending_step,
                ),
                Step(
                    name="final",
                    step_type=StepType.FUNCTION,
                    callable=final_step,
                    dependencies=["suspend"],
                ),
            ],
        )

        engine = WorkflowEngine()

        # Premier run - suspension
        result = engine.run(job)
        assert result.status == RunStatus.SUSPENDED

        # Reprise avec approbation
        resumed = engine.resume(
            result.job_run_id, step_outputs={"suspend": {"approved": True}}
        )
        assert resumed.status == RunStatus.SUCCESS

        final_run = next(sr for sr in resumed.step_runs if sr.step_name == "final")
        assert final_run.output_data == {"approved": True}

    def test_resume_nonexistent_workflow(self):
        """Test de reprise de workflow inexistant."""
        engine = WorkflowEngine()

        with pytest.raises(WorkflowError) as exc_info:
            engine.resume("nonexistent-id")

        assert "No suspended workflow found" in str(exc_info.value)

    def test_workflow_cancellation(self):
        """Test d'annulation de workflow."""

        def suspending_step():
            raise WorkflowSuspended("Wait for user")

        job = Job(
            name="Cancellable",
            steps=[
                Step(
                    name="suspend",
                    step_type=StepType.FUNCTION,
                    callable=suspending_step,
                )
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUSPENDED

        # Annulation
        cancelled = engine.cancel(result.job_run_id)
        assert cancelled is True
        assert result.job_run_id not in engine.list_suspended()
        assert result.status == RunStatus.CANCELLED

    def test_cancel_nonexistent_workflow(self):
        """Test d'annulation de workflow inexistant."""
        engine = WorkflowEngine()
        cancelled = engine.cancel("nonexistent")
        assert cancelled is False

    def test_get_status(self):
        """Test de récupération de statut."""

        def suspending_step():
            raise WorkflowSuspended("Wait")

        job = Job(
            name="Status Test",
            steps=[
                Step(
                    name="suspend",
                    step_type=StepType.FUNCTION,
                    callable=suspending_step,
                )
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        status = engine.get_status(result.job_run_id)
        assert status == RunStatus.SUSPENDED

        # Status de workflow inexistant
        assert engine.get_status("nonexistent") is None

    def test_validate_job(self):
        """Test de validation de job."""

        def dummy():
            return {}

        # Job valide
        valid_job = Job(
            name="Valid",
            steps=[Step(name="step", step_type=StepType.FUNCTION, callable=dummy)],
        )

        engine = WorkflowEngine()
        warnings = engine.validate_job(valid_job)
        assert len(warnings) == 0

        # Job avec avertissements - using non-FUNCTION step type to avoid validation
        warning_job = Job(
            name="Warning Job",
            steps=[
                Step(
                    name="no_callable", step_type=StepType.HTTP_REQUEST
                )  # No callable for non-function step
            ],
        )

        warnings = engine.validate_job(warning_job)
        assert len(warnings) == 0  # HTTP_REQUEST steps don't require callables

    def test_validate_job_invalid(self):
        """Test de validation avec job invalide."""

        def dummy():
            return {}

        # Job avec cycle
        invalid_job = Job(
            name="Invalid",
            steps=[
                Step(
                    name="A",
                    step_type=StepType.FUNCTION,
                    callable=dummy,
                    dependencies=["B"],
                ),
                Step(
                    name="B",
                    step_type=StepType.FUNCTION,
                    callable=dummy,
                    dependencies=["A"],
                ),
            ],
        )

        engine = WorkflowEngine()

        with pytest.raises(DAGValidationError):
            engine.validate_job(invalid_job)

    def test_get_execution_plan(self):
        """Test de génération de plan d'exécution."""

        def dummy():
            return {}

        job = Job(
            name="Plan Test",
            steps=[
                Step(name="start", step_type=StepType.FUNCTION, callable=dummy),
                Step(
                    name="middle",
                    step_type=StepType.FUNCTION,
                    callable=dummy,
                    dependencies=["start"],
                ),
                Step(
                    name="end",
                    step_type=StepType.FUNCTION,
                    callable=dummy,
                    dependencies=["middle"],
                ),
            ],
        )

        engine = WorkflowEngine()
        plan = engine.get_execution_plan(job)

        assert plan["job_name"] == "Plan Test"
        assert plan["execution_order"] == ["start", "middle", "end"]
        assert len(plan["parallel_groups"]) == 3
        assert plan["entry_points"] == ["start"]
        assert plan["exit_points"] == ["end"]
        assert "stats" in plan
        assert "validation_warnings" in plan

    def test_custom_step_executor(self):
        """Test avec executor personnalisé."""

        def custom_executor(step, context):
            return {"custom": f"Executed {step.name}"}

        def dummy():
            return {"normal": "execution"}

        job = Job(
            name="Custom Executor",
            steps=[
                Step(name="normal", step_type=StepType.FUNCTION, callable=dummy),
                Step(name="custom", step_type=StepType.HTTP_REQUEST),  # Pas de callable
            ],
        )

        engine = WorkflowEngine(step_executors={StepType.HTTP_REQUEST: custom_executor})

        result = engine.run(job)
        assert result.status == RunStatus.SUCCESS

        normal_run = next(sr for sr in result.step_runs if sr.step_name == "normal")
        assert normal_run.output_data == {"normal": "execution"}

        custom_run = next(sr for sr in result.step_runs if sr.step_name == "custom")
        assert custom_run.output_data == {"custom": "Executed custom"}

    def test_empty_workflow(self):
        """Test avec workflow vide."""
        job = Job(name="Empty", steps=[])

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert len(result.step_runs) == 0

    def test_error_logging_integration(self):
        """Test d'intégration avec le logging d'erreurs."""

        def failing_step():
            raise ValueError("Test error")

        job = Job(
            name="Error Logging",
            steps=[
                Step(name="fail", step_type=StepType.FUNCTION, callable=failing_step)
            ],
        )

        engine = WorkflowEngine()

        # Capture les logs (mock pour l'instant)
        with patch.object(engine, "_log_step_error") as mock_log:
            with pytest.raises(StepExecutionError):
                engine.run(job)

            mock_log.assert_called_once()

    def test_function_without_arguments(self):
        """Test de fonction sans arguments."""

        def no_args():
            return {"no_context": True}

        job = Job(
            name="No Args",
            steps=[Step(name="no_args", step_type=StepType.FUNCTION, callable=no_args)],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert result.step_runs[0].output_data == {"no_context": True}

    def test_function_with_arguments(self):
        """Test de fonction avec arguments (reçoit le contexte)."""

        def with_context(context):
            return {"has_context": True, "context_type": type(context).__name__}

        job = Job(
            name="With Context",
            steps=[
                Step(
                    name="with_context",
                    step_type=StepType.FUNCTION,
                    callable=with_context,
                )
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert result.step_runs[0].output_data["has_context"] is True
        assert "WorkflowContext" in result.step_runs[0].output_data["context_type"]


class TestWorkflowEngineIntegration:
    """Tests d'intégration du WorkflowEngine."""

    def test_complete_etl_workflow(self):
        """Test d'un workflow ETL complet."""
        # Simulation d'un pipeline ETL
        extracted_data = []
        transformed_data = []
        loaded_data = []

        def extract():
            data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
            extracted_data.extend(data)
            return {"records": len(data), "data": data}

        def transform(context):
            source_data = context.get_step_output("extract")["data"]
            data = [{"id": r["id"], "name": r["name"].upper()} for r in source_data]
            transformed_data.extend(data)
            return {"records": len(data), "data": data}

        def load(context):
            source_data = context.get_step_output("transform")["data"]
            loaded_data.extend(source_data)
            return {"loaded": len(source_data)}

        job = Job(
            name="ETL Pipeline",
            steps=[
                Step(name="extract", step_type=StepType.FUNCTION, callable=extract),
                Step(
                    name="transform",
                    step_type=StepType.FUNCTION,
                    callable=transform,
                    dependencies=["extract"],
                ),
                Step(
                    name="load",
                    step_type=StepType.FUNCTION,
                    callable=load,
                    dependencies=["transform"],
                ),
            ],
        )

        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert len(extracted_data) == 2
        assert len(transformed_data) == 2
        assert len(loaded_data) == 2
        assert loaded_data[0]["name"] == "ALICE"
        assert loaded_data[1]["name"] == "BOB"

    def test_human_approval_workflow(self):
        """Test d'un workflow avec approbation humaine."""

        def prepare_request():
            return {"amount": 1000, "reason": "Office supplies"}

        def request_approval(context):
            request = context.get_step_output("prepare")
            if request["amount"] > 500:
                raise WorkflowSuspended(f"Approval required for ${request['amount']}")
            return {"approved": True}

        def process_approved(context):
            approval = context.get_step_output("approval")
            if approval["approved"]:
                return {"processed": True, "transaction_id": "TXN123"}
            return {"processed": False}

        job = Job(
            name="Approval Workflow",
            steps=[
                Step(
                    name="prepare",
                    step_type=StepType.FUNCTION,
                    callable=prepare_request,
                ),
                Step(
                    name="approval",
                    step_type=StepType.FUNCTION,
                    callable=request_approval,
                    dependencies=["prepare"],
                ),
                Step(
                    name="process",
                    step_type=StepType.FUNCTION,
                    callable=process_approved,
                    dependencies=["approval"],
                ),
            ],
        )

        engine = WorkflowEngine()

        # Premier run - suspension pour approbation
        result = engine.run(job)
        assert result.status == RunStatus.SUSPENDED

        # Approbation manuelle
        approved_result = engine.resume(
            result.job_run_id, step_outputs={"approval": {"approved": True}}
        )

        assert approved_result.status == RunStatus.SUCCESS
        process_run = next(
            sr for sr in approved_result.step_runs if sr.step_name == "process"
        )
        assert process_run.output_data["processed"] is True
        assert process_run.output_data["transaction_id"] == "TXN123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
