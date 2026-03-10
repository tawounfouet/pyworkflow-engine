"""Tests for timeout handling and advanced executors."""

import pytest
import asyncio
import time
from datetime import timedelta
from unittest.mock import Mock, patch

from pyworkflow_engine import WorkflowEngine, Job, Step, StepType, RunStatus
from pyworkflow_engine.core.exceptions import StepExecutionError
from pyworkflow_engine.core.executors import (
    ThreadPoolStepExecutor,
    ProcessPoolStepExecutor,
    AsyncStepExecutor,
    RetryableExecutor,
    ExecutorRegistry,
)


# Add helper function for creating context
def create_test_context():
    """Create a test WorkflowContext with minimal JobRun."""
    from pyworkflow_engine.core.context import WorkflowContext
    from pyworkflow_engine import JobRun

    job_run = JobRun(job_name="test_job")
    return WorkflowContext(job_run)


# Module-level functions for process pool testing (must be picklable)
def picklable_cpu_function():
    """CPU function that can be pickled for multiprocessing."""
    return {"process_result": sum(range(1000))}


def picklable_slow_cpu_function():
    """Slow CPU function that can be pickled for multiprocessing."""
    import time

    time.sleep(2)
    return {"slow_result": "completed"}


def picklable_cpu_function_with_context(context_data):
    """CPU function that accepts context and can be pickled."""
    multiplier = context_data.get("multiplier", 1)
    return {"process_result": sum(i * multiplier for i in range(100))}


class TestTimeoutHandling:
    """Test timeout functionality in workflow engine."""

    def test_step_timeout_success_within_limit(self):
        """Test that steps completing within timeout succeed."""
        engine = WorkflowEngine()

        def quick_function():
            time.sleep(0.1)  # 100ms
            return {"completed": True}

        job = Job(
            name="timeout_success_test",
            steps=[
                Step(
                    name="quick_step",
                    step_type=StepType.FUNCTION,
                    callable=quick_function,
                    timeout=timedelta(seconds=1),  # 1 second timeout
                )
            ],
        )

        result = engine.run(job)
        assert result.status == RunStatus.SUCCESS
        assert result.step_runs[0].output_data["completed"] is True

    def test_step_timeout_failure_exceeds_limit(self):
        """Test that steps exceeding timeout fail appropriately."""
        engine = WorkflowEngine()

        def slow_function():
            time.sleep(2)  # 2 seconds
            return {"should_not_reach": True}

        job = Job(
            name="timeout_failure_test",
            steps=[
                Step(
                    name="slow_step",
                    step_type=StepType.FUNCTION,
                    callable=slow_function,
                    timeout=timedelta(milliseconds=500),  # 500ms timeout
                )
            ],
        )

        with pytest.raises(StepExecutionError) as exc_info:
            engine.run(job)

        assert "timed out" in str(exc_info.value).lower()
        assert "slow_step" in str(exc_info.value)

    def test_no_timeout_specified(self):
        """Test that steps without timeout run normally."""
        engine = WorkflowEngine()

        def normal_function():
            time.sleep(0.1)
            return {"no_timeout": True}

        job = Job(
            name="no_timeout_test",
            steps=[
                Step(
                    name="normal_step",
                    step_type=StepType.FUNCTION,
                    callable=normal_function,
                    # No timeout specified
                )
            ],
        )

        result = engine.run(job)
        assert result.status == RunStatus.SUCCESS
        assert result.step_runs[0].output_data["no_timeout"] is True


class TestThreadPoolExecutor:
    """Test ThreadPoolExecutor functionality."""

    def test_thread_pool_basic_execution(self):
        """Test basic thread pool execution."""
        executor = ThreadPoolStepExecutor(max_workers=2)

        def io_function():
            time.sleep(0.1)
            return {"thread_result": True}

        step = Step(
            name="thread_test", step_type=StepType.FUNCTION, callable=io_function
        )

        context = create_test_context()
        result = executor.execute(step, context)
        assert result["thread_result"] is True

        executor.shutdown()

    def test_thread_pool_with_timeout(self):
        """Test thread pool executor with timeout."""

        executor = ThreadPoolStepExecutor(max_workers=2)

        def slow_function():
            time.sleep(2)
            return {"should_timeout": False}

        step = Step(
            name="timeout_test",
            step_type=StepType.FUNCTION,
            callable=slow_function,
            timeout=timedelta(milliseconds=500),
        )

        context = create_test_context()
        with pytest.raises(Exception):  # Should timeout
            executor.execute(step, context)

        executor.shutdown()

    def test_thread_pool_function_with_context(self):
        """Test thread pool execution with context."""

        executor = ThreadPoolStepExecutor(max_workers=2)

        def context_function(context):
            return {"context_received": context is not None}

        step = Step(
            name="context_test", step_type=StepType.FUNCTION, callable=context_function
        )

        mock_context = create_test_context()
        result = executor.execute(step, mock_context)
        assert result["context_received"] is True

        executor.shutdown()


class TestProcessPoolExecutor:
    """Test ProcessPoolExecutor functionality."""

    def test_process_pool_basic_execution(self):
        """Test basic process pool execution."""

        executor = ProcessPoolStepExecutor(max_workers=2)

        step = Step(
            name="process_test",
            step_type=StepType.FUNCTION,
            callable=picklable_cpu_function,
        )

        context = create_test_context()
        result = executor.execute(step, context)
        assert result["process_result"] == sum(range(1000))

        executor.shutdown()

    def test_process_pool_with_timeout(self):
        """Test process pool executor with timeout."""

        executor = ProcessPoolStepExecutor(max_workers=2)

        step = Step(
            name="cpu_timeout_test",
            step_type=StepType.FUNCTION,
            callable=picklable_slow_cpu_function,
            timeout=timedelta(milliseconds=500),
        )

        context = create_test_context()
        with pytest.raises(Exception):  # Should timeout
            executor.execute(step, context)

        executor.shutdown()


class TestAsyncExecutor:
    """Test AsyncExecutor functionality."""

    def test_async_basic_execution(self):
        """Test basic async execution."""

        executor = AsyncStepExecutor()

        async def async_function():
            await asyncio.sleep(0.1)
            return {"async_result": True}

        step = Step(
            name="async_test", step_type=StepType.FUNCTION, callable=async_function
        )

        context = create_test_context()
        result = executor.execute(step, context)
        assert result["async_result"] is True

    def test_async_with_context(self):
        """Test async execution with context."""

        executor = AsyncStepExecutor()

        async def async_context_function(context):
            await asyncio.sleep(0.05)
            return {"has_context": context is not None}

        step = Step(
            name="async_context_test",
            step_type=StepType.FUNCTION,
            callable=async_context_function,
        )

        mock_context = create_test_context()
        result = executor.execute(step, mock_context)
        assert result["has_context"] is True

    def test_async_with_timeout(self):
        """Test async execution with timeout."""

        executor = AsyncStepExecutor()

        async def slow_async_function():
            await asyncio.sleep(2)
            return {"should_timeout": False}

        step = Step(
            name="async_timeout_test",
            step_type=StepType.FUNCTION,
            callable=slow_async_function,
            timeout=timedelta(milliseconds=500),
        )

        context = create_test_context()
        with pytest.raises(Exception):  # Should timeout
            executor.execute(step, context)

    def test_non_async_function_error(self):
        """Test that non-async functions raise appropriate error."""

        executor = AsyncStepExecutor()

        def regular_function():
            return {"not_async": True}

        step = Step(
            name="non_async_test",
            step_type=StepType.FUNCTION,
            callable=regular_function,
        )

        context = create_test_context()
        with pytest.raises(StepExecutionError) as exc_info:
            executor.execute(step, context)

        assert "not an async function" in str(exc_info.value)


class TestRetryableExecutor:
    """Test RetryableExecutor functionality."""

    def test_retryable_success_on_retry(self):
        """Test that retryable executor succeeds after failures."""
        base_executor = Mock()

        # Fail twice, then succeed
        base_executor.execute.side_effect = [
            RuntimeError("First failure"),
            RuntimeError("Second failure"),
            {"retry_success": True},
        ]

        executor = RetryableExecutor(
            base_executor=base_executor,
            max_retries=3,
            base_delay=0.01,  # Very short delay for testing
        )

        step = Mock()
        context = Mock()

        result = executor.execute(step, context)
        assert result["retry_success"] is True
        assert base_executor.execute.call_count == 3

    def test_retryable_failure_after_max_retries(self):
        """Test that retryable executor fails after max retries exceeded."""
        base_executor = Mock()
        base_executor.execute.side_effect = RuntimeError("Persistent failure")

        executor = RetryableExecutor(
            base_executor=base_executor, max_retries=2, base_delay=0.01
        )

        step = Mock()
        context = Mock()

        with pytest.raises(RuntimeError, match="Persistent failure"):
            executor.execute(step, context)

        assert base_executor.execute.call_count == 3  # Initial + 2 retries

    def test_retryable_exponential_backoff(self):
        """Test exponential backoff in retryable executor."""
        base_executor = Mock()
        base_executor.execute.side_effect = [RuntimeError("Fail"), {"success": True}]

        executor = RetryableExecutor(
            base_executor=base_executor,
            max_retries=2,
            base_delay=0.1,
            exponential_base=2.0,
            jitter=False,  # Disable jitter for predictable testing
        )

        step = Mock()
        context = Mock()

        start_time = time.time()
        result = executor.execute(step, context)
        duration = time.time() - start_time

        assert result["success"] is True
        # Should have at least base_delay (0.1s) between attempts
        assert duration >= 0.1


class TestExecutorRegistry:
    """Test ExecutorRegistry functionality."""

    def test_executor_registration_and_retrieval(self):
        """Test registering and retrieving executors."""
        registry = ExecutorRegistry()

        mock_executor = Mock()
        registry.register("test_executor", mock_executor)

        retrieved = registry.get("test_executor")
        assert retrieved is mock_executor

    def test_list_executors(self):
        """Test listing registered executors."""
        registry = ExecutorRegistry()

        executor1 = Mock()
        executor2 = Mock()

        registry.register("executor1", executor1)
        registry.register("executor2", executor2)

        executors = registry.list_executors()
        assert "executor1" in executors
        assert "executor2" in executors
        assert len(executors) == 2

    def test_get_nonexistent_executor(self):
        """Test getting non-existent executor returns None."""
        registry = ExecutorRegistry()

        result = registry.get("nonexistent")
        assert result is None

    def test_shutdown_all_executors(self):
        """Test shutting down all executors."""
        registry = ExecutorRegistry()

        executor1 = Mock()
        executor2 = Mock()

        registry.register("executor1", executor1)
        registry.register("executor2", executor2)

        registry.shutdown_all()

        # Should call shutdown if method exists
        if hasattr(executor1, "shutdown"):
            executor1.shutdown.assert_called_once()
        if hasattr(executor2, "shutdown"):
            executor2.shutdown.assert_called_once()


class TestWorkflowEngineExecutorIntegration:
    """Test WorkflowEngine integration with advanced executors."""

    def test_engine_executor_registration(self):
        """Test registering executors with workflow engine."""
        engine = WorkflowEngine()

        mock_executor = Mock()
        engine.register_executor("test_executor", mock_executor)

        retrieved = engine.get_executor("test_executor")
        assert retrieved is mock_executor

    def test_engine_list_executors(self):
        """Test listing executors from workflow engine."""
        engine = WorkflowEngine()

        executor1 = Mock()
        executor2 = Mock()

        engine.register_executor("executor1", executor1)
        engine.register_executor("executor2", executor2)

        executors = engine.list_executors()
        assert "executor1" in executors
        assert "executor2" in executors

    def test_engine_shutdown_executors(self):
        """Test shutting down executors from workflow engine."""
        engine = WorkflowEngine()

        mock_executor = Mock()
        engine.register_executor("test_executor", mock_executor)

        engine.shutdown_executors()

        # Should call shutdown if method exists
        if hasattr(mock_executor, "shutdown"):
            mock_executor.shutdown.assert_called_once()


class TestIntegrationTimeoutAndExecutors:
    """Integration tests combining timeout and executors."""

    def test_thread_executor_with_timeout_success(self):
        """Test thread executor with timeout that succeeds."""

        engine = WorkflowEngine()
        thread_executor = ThreadPoolStepExecutor(max_workers=2)
        engine.register_executor("thread_pool", thread_executor)

        def quick_io():
            time.sleep(0.1)
            return {"io_result": "success"}

        # Since we haven't extended Step model to support executor_name,
        # test the executor directly
        step = Step(
            name="io_test",
            step_type=StepType.FUNCTION,
            callable=quick_io,
            timeout=timedelta(seconds=1),
        )

        context = create_test_context()
        result = thread_executor.execute(step, context)
        assert result["io_result"] == "success"

        engine.shutdown_executors()

    def test_async_executor_with_timeout_failure(self):
        """Test async executor with timeout that fails."""

        async_executor = AsyncStepExecutor()

        async def slow_async():
            await asyncio.sleep(2)
            return {"should_not_reach": True}

        step = Step(
            name="slow_async_test",
            step_type=StepType.FUNCTION,
            callable=slow_async,
            timeout=timedelta(milliseconds=500),
        )

        context = create_test_context()
        with pytest.raises(Exception):  # Should timeout
            async_executor.execute(step, context)
