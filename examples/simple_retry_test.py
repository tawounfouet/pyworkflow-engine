#!/usr/bin/env python3
"""Simple test of retry mechanisms in PyWorkflow Engine."""

import sys
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyworkflow_engine import WorkflowEngine, Job, Step, StepType


def unstable_function():
    """Fails first two times, succeeds on third."""
    if not hasattr(unstable_function, "count"):
        unstable_function.count = 0
    unstable_function.count += 1
    print(f"Attempt {unstable_function.count}")

    if unstable_function.count < 3:
        raise RuntimeError(f"Failure {unstable_function.count}")
    return {"success": True, "attempts": unstable_function.count}


def main():
    print("Testing retry mechanisms...")

    engine = WorkflowEngine()
    job = Job(
        name="retry_test",
        steps=[
            Step(
                name="test_step",
                step_type=StepType.FUNCTION,
                callable=unstable_function,
                retry_count=3,
                retry_delay=timedelta(milliseconds=100),
            )
        ],
    )

    try:
        result = engine.run(job)
        print(f"Success! Status: {result.status}")
        print(f"Output: {result.step_runs[0].output_data}")
        print(f"Retries used: {result.step_runs[0].retry_count}")
    except Exception as e:
        print(f"Failed: {e}")


if __name__ == "__main__":
    main()
