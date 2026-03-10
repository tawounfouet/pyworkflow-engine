"""
Simple Workflow Examples: Demonstrating Core Features

Collection of simple examples showing the basic features of the IAS Workflow Engine.
"""

from pyworkflow_engine import WorkflowEngine, Job, Step, StepType, WorkflowContext
import time


def simple_step_1() -> dict:
    """First step in a simple workflow."""
    print("🚀 Executing Step 1")
    return {"step1_data": "Hello from step 1", "timestamp": time.time()}


def simple_step_2(context: WorkflowContext) -> dict:
    """Second step that uses output from first step."""
    step1_output = context.get_step_output("step1")
    print(f"📝 Executing Step 2, got data: {step1_output['step1_data']}")

    return {
        "step2_data": f"Processed: {step1_output['step1_data']}",
        "total_time": time.time() - step1_output["timestamp"],
    }


def simple_step_3(context: WorkflowContext) -> dict:
    """Final step that combines all outputs."""
    step1_output = context.get_step_output("step1")
    step2_output = context.get_step_output("step2")

    print("✅ Executing Final Step")

    return {
        "final_result": "Workflow completed successfully",
        "summary": {
            "step1": step1_output["step1_data"],
            "step2": step2_output["step2_data"],
            "processing_time": step2_output["total_time"],
        },
    }


def parallel_task_a() -> dict:
    """Parallel task A."""
    time.sleep(0.1)  # Simulate work
    print("🔄 Task A completed")
    return {"task": "A", "result": "Task A result", "duration": 0.1}


def parallel_task_b() -> dict:
    """Parallel task B."""
    time.sleep(0.15)  # Simulate work
    print("🔄 Task B completed")
    return {"task": "B", "result": "Task B result", "duration": 0.15}


def parallel_task_c() -> dict:
    """Parallel task C."""
    time.sleep(0.05)  # Simulate work
    print("🔄 Task C completed")
    return {"task": "C", "result": "Task C result", "duration": 0.05}


def combine_parallel_results(context: WorkflowContext) -> dict:
    """Combine results from parallel tasks."""
    task_a = context.get_step_output("task_a")
    task_b = context.get_step_output("task_b")
    task_c = context.get_step_output("task_c")

    total_duration = task_a["duration"] + task_b["duration"] + task_c["duration"]

    print(f"🎯 Combined results from {len([task_a, task_b, task_c])} parallel tasks")

    return {
        "combined_results": [task_a["result"], task_b["result"], task_c["result"]],
        "total_sequential_time": total_duration,
        "tasks_completed": 3,
    }


def example_1_simple_linear():
    """Example 1: Simple linear workflow with step dependencies."""
    print("=" * 60)
    print("🚀 Example 1: Simple Linear Workflow")
    print("=" * 60)

    # Create a simple linear workflow
    steps = [
        Step(name="step1", step_type=StepType.FUNCTION, callable=simple_step_1),
        Step(
            name="step2",
            step_type=StepType.FUNCTION,
            callable=simple_step_2,
            dependencies=["step1"],
        ),
        Step(
            name="step3",
            step_type=StepType.FUNCTION,
            callable=simple_step_3,
            dependencies=["step2"],
        ),
    ]

    job = Job(name="Simple Linear Workflow", steps=steps)
    engine = WorkflowEngine()

    # Show execution plan
    plan = engine.get_execution_plan(job)
    print(f"\n📋 Execution Order: {' → '.join(plan['execution_order'])}")

    # Execute
    start_time = time.time()
    job_run = engine.run(job)
    end_time = time.time()

    print(f"\n✅ Workflow Status: {job_run.status}")
    print(f"⏱️  Execution Time: {(end_time - start_time) * 1000:.0f}ms")

    # Get final result
    final_step = next((s for s in job_run.step_runs if s.step_name == "step3"), None)
    if final_step and final_step.output_data:
        print(f"📊 Final Result: {final_step.output_data['final_result']}")
        print(f"📈 Processing Summary: {final_step.output_data['summary']}")


def example_2_parallel_execution():
    """Example 2: Parallel task execution."""
    print("\n" + "=" * 60)
    print("🚀 Example 2: Parallel Task Execution")
    print("=" * 60)

    # Create workflow with parallel tasks
    steps = [
        # These three tasks can run in parallel (no dependencies)
        Step(name="task_a", step_type=StepType.FUNCTION, callable=parallel_task_a),
        Step(name="task_b", step_type=StepType.FUNCTION, callable=parallel_task_b),
        Step(name="task_c", step_type=StepType.FUNCTION, callable=parallel_task_c),
        # This task waits for all parallel tasks to complete
        Step(
            name="combine",
            step_type=StepType.FUNCTION,
            callable=combine_parallel_results,
            dependencies=["task_a", "task_b", "task_c"],
        ),
    ]

    job = Job(name="Parallel Execution Example", steps=steps)
    engine = WorkflowEngine()

    # Show execution plan
    plan = engine.get_execution_plan(job)
    print(f"\n📋 Execution Order: {' → '.join(plan['execution_order'])}")
    print(f"🔀 Parallel Groups: {len(plan['parallel_groups'])} groups found")

    # Execute
    start_time = time.time()
    job_run = engine.run(job)
    end_time = time.time()

    actual_time = (end_time - start_time) * 1000

    print(f"\n✅ Workflow Status: {job_run.status}")
    print(f"⏱️  Actual Execution Time: {actual_time:.0f}ms")

    # Get results
    combine_step = next(
        (s for s in job_run.step_runs if s.step_name == "combine"), None
    )
    if combine_step and combine_step.output_data:
        data = combine_step.output_data
        theoretical_time = data["total_sequential_time"] * 1000
        print(f"📊 Tasks Completed: {data['tasks_completed']}")
        print(
            f"⚡ Time Saved: ~{theoretical_time - actual_time:.0f}ms through parallel execution"
        )


def example_3_context_sharing():
    """Example 3: Demonstrating context data sharing."""
    print("\n" + "=" * 60)
    print("🚀 Example 3: Context Data Sharing")
    print("=" * 60)

    def setup_data(context: WorkflowContext) -> dict:
        # Set some shared data in context
        context.set(
            "shared_config", {"api_url": "https://api.example.com", "timeout": 30}
        )
        context.set("user_id", "user123")

        print("📋 Setup shared configuration in context")
        return {"setup": "complete"}

    def use_shared_data(context: WorkflowContext) -> dict:
        config = context.get("shared_config")
        user_id = context.get("user_id")

        print(f"🔗 Retrieved shared data - API: {config['api_url']}, User: {user_id}")
        return {"api_call": f"GET {config['api_url']}/users/{user_id}"}

    steps = [
        Step(name="setup", step_type=StepType.FUNCTION, callable=setup_data),
        Step(
            name="use_data",
            step_type=StepType.FUNCTION,
            callable=use_shared_data,
            dependencies=["setup"],
        ),
    ]

    job = Job(name="Context Sharing Example", steps=steps)
    engine = WorkflowEngine()

    # Execute with initial context
    initial_context = {"environment": "development", "debug": True}
    job_run = engine.run(job, initial_context=initial_context)

    print(f"\n✅ Workflow Status: {job_run.status}")

    # Show that context was shared between steps
    use_data_step = next(
        (s for s in job_run.step_runs if s.step_name == "use_data"), None
    )
    if use_data_step and use_data_step.output_data:
        print(f"🌐 API Call Made: {use_data_step.output_data['api_call']}")


def main():
    """Run all simple workflow examples."""
    print("🚀 IAS Workflow Engine - Simple Examples")
    print("Demonstrating core workflow features\n")

    # Run examples
    example_1_simple_linear()
    example_2_parallel_execution()
    example_3_context_sharing()

    print("\n" + "=" * 60)
    print("✅ All examples completed successfully!")
    print(
        "🎯 Try running the other examples: basic_etl.py, human_approval.py, parallel_processing.py"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
