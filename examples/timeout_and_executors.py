#!/usr/bin/env python3
"""
Example: Timeout Handling and Advanced Executors

This example demonstrates the enhanced features in Phase 1 Week 4:
- Timeout handling for long-running steps
- Advanced executors (ThreadPool, ProcessPool, Async)
- Executor registry and management
"""

import sys
import asyncio
import time
from pathlib import Path
from datetime import timedelta

# Add the source directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyworkflow_engine import WorkflowEngine, Job, Step, StepType
from pyworkflow_engine.core.executors import (
    ThreadPoolStepExecutor,
    ProcessPoolStepExecutor,
    AsyncStepExecutor,
    RetryableExecutor,
)


def quick_function():
    """A function that completes quickly."""
    return {"result": "Quick completion", "duration": 0.1}


def slow_function():
    """A function that takes a long time - will timeout."""
    time.sleep(5)  # Simulate long operation
    return {"result": "Should not reach here", "duration": 5.0}


def cpu_intensive_function():
    """CPU-intensive function for process pool testing."""
    # Simulate CPU-intensive work
    result = sum(i * i for i in range(100000))
    return {"result": result, "type": "cpu_intensive"}


def io_bound_function():
    """I/O-bound function for thread pool testing."""
    import time

    time.sleep(0.5)  # Simulate I/O wait
    return {"result": "I/O completed", "duration": 0.5}


async def async_function():
    """Async function for async executor testing."""
    await asyncio.sleep(0.3)  # Simulate async I/O
    return {"result": "Async completed", "duration": 0.3}


def unreliable_function():
    """Function that fails sometimes - for retry testing."""
    import random

    if random.random() < 0.7:  # 70% failure rate
        raise RuntimeError("Random failure for testing")
    return {"result": "Eventually succeeded", "attempts": "multiple"}


def main():
    """Demonstrate timeout handling and advanced executors."""
    print("=== IAS Workflow Engine - Timeout & Advanced Executors ===\n")

    engine = WorkflowEngine()

    # Register advanced executors
    thread_executor = ThreadPoolStepExecutor(max_workers=4)
    process_executor = ProcessPoolStepExecutor(max_workers=2)
    async_executor = AsyncStepExecutor()

    engine.register_executor("thread_pool", thread_executor)
    engine.register_executor("process_pool", process_executor)
    engine.register_executor("async", async_executor)

    # Create retryable version of thread executor
    retryable_thread = RetryableExecutor(
        base_executor=thread_executor,
        max_retries=5,
        base_delay=0.1,
        exponential_base=2.0,
        jitter=True,
    )
    engine.register_executor("retryable_thread", retryable_thread)

    print(f"Registered executors: {engine.list_executors()}\n")

    # Example 1: Timeout Handling
    print("1. Testing timeout handling...")

    # Quick function - should succeed
    quick_job = Job(
        name="quick_timeout_test",
        steps=[
            Step(
                name="quick_step",
                step_type=StepType.FUNCTION,
                callable=quick_function,
                timeout=timedelta(seconds=2),  # 2 second timeout
            )
        ],
    )

    try:
        result = engine.run(quick_job)
        print(f"✓ Quick step completed: {result.step_runs[0].output_data}")
    except Exception as e:
        print(f"✗ Quick step failed: {e}")

    # Slow function - should timeout
    slow_job = Job(
        name="slow_timeout_test",
        steps=[
            Step(
                name="slow_step",
                step_type=StepType.FUNCTION,
                callable=slow_function,
                timeout=timedelta(seconds=1),  # 1 second timeout
            )
        ],
    )

    try:
        result = engine.run(slow_job)
        print(f"Slow step completed: {result.step_runs[0].output_data}")
    except Exception as e:
        print(f"✓ Slow step timed out as expected: {type(e).__name__}")

    print()

    # Example 2: ThreadPool Executor
    print("2. Testing ThreadPool executor...")

    thread_job = Job(
        name="thread_pool_test",
        steps=[
            Step(
                name="io_step",
                step_type=StepType.FUNCTION,
                callable=io_bound_function,
                # executor_name="thread_pool"  # Would use if Step model supported it
            )
        ],
    )

    start_time = time.time()
    try:
        # Manually test thread executor
        thread_result = thread_executor.execute(
            thread_job.steps[0], None  # Simple test without context
        )
        duration = time.time() - start_time
        print(f"✓ ThreadPool execution completed in {duration:.2f}s: {thread_result}")
    except Exception as e:
        print(f"✗ ThreadPool execution failed: {e}")

    print()

    # Example 3: ProcessPool Executor
    print("3. Testing ProcessPool executor...")

    try:
        # Test process executor directly
        process_step = Step(
            name="cpu_step",
            step_type=StepType.FUNCTION,
            callable=cpu_intensive_function,
        )

        start_time = time.time()
        process_result = process_executor.execute(process_step, {})
        duration = time.time() - start_time
        print(f"✓ ProcessPool execution completed in {duration:.2f}s: {process_result}")
    except Exception as e:
        print(f"✗ ProcessPool execution failed: {e}")

    print()

    # Example 4: Async Executor
    print("4. Testing Async executor...")

    try:
        async_step = Step(
            name="async_step", step_type=StepType.FUNCTION, callable=async_function
        )

        start_time = time.time()
        async_result = async_executor.execute(async_step, None)
        duration = time.time() - start_time
        print(f"✓ Async execution completed in {duration:.2f}s: {async_result}")
    except Exception as e:
        print(f"✗ Async execution failed: {e}")

    print()

    # Example 5: Retryable Executor
    print("5. Testing Retryable executor...")

    try:
        retry_step = Step(
            name="unreliable_step",
            step_type=StepType.FUNCTION,
            callable=unreliable_function,
        )

        start_time = time.time()
        retry_result = retryable_thread.execute(retry_step, None)
        duration = time.time() - start_time
        print(f"✓ Retryable execution succeeded in {duration:.2f}s: {retry_result}")
    except Exception as e:
        print(f"✗ Retryable execution failed after all retries: {e}")

    print()

    # Example 6: Complex workflow with mixed executors
    print("6. Testing complex workflow with multiple executor types...")

    def step_a():
        return {"data": "from_step_a", "executor": "default"}

    def step_b():
        time.sleep(0.1)  # Simulate some work
        return {"data": "from_step_b", "executor": "thread_pool"}

    def step_c():
        import math

        result = sum(math.sqrt(i) for i in range(1000))
        return {"data": result, "executor": "process_pool"}

    complex_job = Job(
        name="mixed_executor_workflow",
        steps=[
            Step(name="step_a", step_type=StepType.FUNCTION, callable=step_a),
            Step(
                name="step_b",
                step_type=StepType.FUNCTION,
                callable=step_b,
                dependencies=["step_a"],
                timeout=timedelta(seconds=2),
            ),
            Step(
                name="step_c",
                step_type=StepType.FUNCTION,
                callable=step_c,
                dependencies=["step_a"],
                timeout=timedelta(seconds=5),
            ),
        ],
    )

    try:
        start_time = time.time()
        complex_result = engine.run(complex_job)
        duration = time.time() - start_time

        print(f"✓ Complex workflow completed in {duration:.2f}s")
        print(f"Status: {complex_result.status}")

        for step_run in complex_result.step_runs:
            print(
                f"  - {step_run.step_name}: {step_run.status} -> {step_run.output_data}"
            )

    except Exception as e:
        print(f"✗ Complex workflow failed: {e}")

    print()

    # Cleanup
    print("7. Cleaning up executors...")
    engine.shutdown_executors()
    print("✓ All executors shut down")

    print("\n=== Timeout & Advanced Executors Demo Complete ===")


if __name__ == "__main__":
    main()
