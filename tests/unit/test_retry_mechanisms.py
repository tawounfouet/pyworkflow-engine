"""Tests for retry mechanisms in the workflow engine."""

import pytest
from datetime import timedelta
from unittest.mock import Mock

from ias_workflow_engine import WorkflowEngine, Job, Step, StepType, RunStatus
from ias_workflow_engine.core.exceptions import StepExecutionError


class TestRetryMechanisms:
    """Test retry functionality in the workflow engine."""

    def test_successful_retry_after_failures(self):
        """Test that a step succeeds after initial failures with retry."""
        engine = WorkflowEngine()

        # Create a function that fails first 2 times, succeeds on 3rd
        call_count = 0

        def unstable_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError(f"Failure {call_count}")
            return {"success": True, "attempts": call_count}

        job = Job(
            name="retry_success_test",
            steps=[
                Step(
                    name="unstable_step",
                    step_type=StepType.FUNCTION,
                    callable=unstable_function,
                    retry_count=3,
                    retry_delay=timedelta(milliseconds=1),  # Very short delay for tests
                )
            ],
        )

        result = engine.run(job)

        # Verify successful execution
        assert result.status == RunStatus.SUCCESS
        assert len(result.step_runs) == 1

        step_run = result.step_runs[0]
        assert step_run.status == RunStatus.SUCCESS
        assert step_run.retry_count == 2  # 2 retries were needed
        assert step_run.output_data == {"success": True, "attempts": 3}
        assert call_count == 3  # Function was called 3 times total

    def test_retry_exhaustion_failure(self):
        """Test that a step fails when all retries are exhausted."""
        engine = WorkflowEngine()

        call_count = 0

        def always_fail_function():
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"Persistent failure {call_count}")

        job = Job(
            name="retry_exhaustion_test",
            steps=[
                Step(
                    name="failing_step",
                    step_type=StepType.FUNCTION,
                    callable=always_fail_function,
                    retry_count=2,  # Only 2 retries
                    retry_delay=timedelta(milliseconds=1),
                )
            ],
        )

        # Should fail after exhausting retries
        with pytest.raises(StepExecutionError) as exc_info:
            engine.run(job)

        # Verify the function was called the expected number of times (1 initial + 2 retries = 3)
        assert call_count == 3
        assert "failing_step" in str(exc_info.value)

    def test_no_retry_on_success(self):
        """Test that no retries are performed when step succeeds immediately."""
        engine = WorkflowEngine()

        call_count = 0

        def success_function():
            nonlocal call_count
            call_count += 1
            return {"success": True, "call_count": call_count}

        job = Job(
            name="no_retry_test",
            steps=[
                Step(
                    name="success_step",
                    step_type=StepType.FUNCTION,
                    callable=success_function,
                    retry_count=5,  # High retry count, but shouldn't be used
                )
            ],
        )

        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        step_run = result.step_runs[0]
        assert step_run.status == RunStatus.SUCCESS
        assert step_run.retry_count == 0  # No retries needed
        assert call_count == 1  # Function called only once

    def test_zero_retry_count(self):
        """Test behavior when retry_count is 0 (no retries)."""
        engine = WorkflowEngine()

        call_count = 0

        def fail_function():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Immediate failure")

        job = Job(
            name="zero_retry_test",
            steps=[
                Step(
                    name="fail_step",
                    step_type=StepType.FUNCTION,
                    callable=fail_function,
                    retry_count=0,  # No retries
                )
            ],
        )

        with pytest.raises(StepExecutionError):
            engine.run(job)

        # Should only be called once (no retries)
        assert call_count == 1

    def test_retry_with_context_preservation(self):
        """Test that context is preserved across retries."""
        engine = WorkflowEngine()

        call_count = 0

        def context_dependent_function(context):
            nonlocal call_count
            call_count += 1

            # Check that context is available
            assert context is not None

            if call_count < 2:
                raise RuntimeError(f"Context failure {call_count}")

            return {"context_available": True, "attempts": call_count}

        job = Job(
            name="context_retry_test",
            steps=[
                Step(
                    name="context_step",
                    step_type=StepType.FUNCTION,
                    callable=context_dependent_function,
                    retry_count=2,
                )
            ],
        )

        # Provide initial context
        result = engine.run(job, initial_context={"test_data": "value"})

        assert result.status == RunStatus.SUCCESS
        step_run = result.step_runs[0]
        assert step_run.retry_count == 1
        assert step_run.output_data["context_available"] is True

    def test_retry_delay_timing(self):
        """Test that retry delays are respected (basic timing test)."""
        engine = WorkflowEngine()

        import time

        start_times = []

        def time_tracking_function():
            start_times.append(time.time())
            if len(start_times) < 3:
                raise RuntimeError("Timing failure")
            return {"success": True}

        job = Job(
            name="timing_test",
            steps=[
                Step(
                    name="timing_step",
                    step_type=StepType.FUNCTION,
                    callable=time_tracking_function,
                    retry_count=3,
                    retry_delay=timedelta(milliseconds=50),  # 50ms delay
                )
            ],
        )

        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert len(start_times) == 3

        # Verify there was some delay between calls (allowing for timing variance)
        time_diff_1 = start_times[1] - start_times[0]
        time_diff_2 = start_times[2] - start_times[1]

        # Should be at least 40ms (allowing 10ms variance for test timing)
        assert time_diff_1 >= 0.04
        assert time_diff_2 >= 0.04

    def test_retry_in_complex_workflow(self):
        """Test retry functionality in a multi-step workflow."""
        engine = WorkflowEngine()

        def reliable_step_a():
            return {"data": "from_a"}

        call_count_b = 0

        def unreliable_step_b(context):
            nonlocal call_count_b
            call_count_b += 1

            if call_count_b < 2:
                raise RuntimeError("Step B failure")

            a_data = context.get_step_output("step_a")
            return {"data": "from_b", "input": a_data}

        def final_step_c(context):
            a_data = context.get_step_output("step_a")
            b_data = context.get_step_output("step_b")
            return {"combined": [a_data, b_data]}

        job = Job(
            name="complex_retry_workflow",
            steps=[
                Step(
                    name="step_a", step_type=StepType.FUNCTION, callable=reliable_step_a
                ),
                Step(
                    name="step_b",
                    step_type=StepType.FUNCTION,
                    callable=unreliable_step_b,
                    dependencies=["step_a"],
                    retry_count=3,
                    retry_delay=timedelta(milliseconds=1),
                ),
                Step(
                    name="step_c",
                    step_type=StepType.FUNCTION,
                    callable=final_step_c,
                    dependencies=["step_a", "step_b"],
                ),
            ],
        )

        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert len(result.step_runs) == 3

        # Check step A (no retries)
        step_a_run = next(sr for sr in result.step_runs if sr.step_name == "step_a")
        assert step_a_run.retry_count == 0

        # Check step B (should have retried once)
        step_b_run = next(sr for sr in result.step_runs if sr.step_name == "step_b")
        assert step_b_run.retry_count == 1
        assert call_count_b == 2  # Called twice (initial + 1 retry)

        # Check step C (no retries)
        step_c_run = next(sr for sr in result.step_runs if sr.step_name == "step_c")
        assert step_c_run.retry_count == 0

        # Verify final output
        final_output = step_c_run.output_data
        assert "combined" in final_output
        assert len(final_output["combined"]) == 2
