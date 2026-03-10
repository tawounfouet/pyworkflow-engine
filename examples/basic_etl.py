"""
Basic Example: Simple ETL Workflow

This example demonstrates a basic ETL (Extract, Transform, Load) workflow
using the IAS Workflow Engine.
"""

from ias_workflow_engine import WorkflowEngine, Job, Step, StepType, WorkflowContext
import json


def extract_data(context: WorkflowContext) -> dict:
    """Extract data from source."""
    data = {
        "users": [
            {"id": 1, "name": "Alice", "email": "alice@example.com", "age": 30},
            {"id": 2, "name": "Bob", "email": "bob@example.com", "age": 25},
            {"id": 3, "name": "Charlie", "email": "charlie@example.com", "age": 35},
        ]
    }
    print(f"📥 Extracted {len(data['users'])} user records")
    return data


def transform_data(context: WorkflowContext) -> dict:
    """Transform the extracted data."""
    source_data = context.get_step_output("extract")

    # Add derived fields and filter data
    transformed_users = []
    for user in source_data["users"]:
        if user["age"] >= 25:  # Only adult users
            user["full_email"] = f"{user['name']} <{user['email']}>"
            user["category"] = "adult" if user["age"] >= 30 else "young_adult"
            transformed_users.append(user)

    result = {
        "processed_users": transformed_users,
        "total_count": len(transformed_users),
        "processing_timestamp": "2024-01-01T00:00:00Z",
    }

    print(f"🔄 Transformed data: {result['total_count']} users processed")
    return result


def load_to_database(context: WorkflowContext) -> dict:
    """Load transformed data to database (simulated)."""
    transformed_data = context.get_step_output("transform")

    # Simulate database insertion
    for user in transformed_data["processed_users"]:
        print(f"💾 Inserting user: {user['name']} ({user['category']})")

    return {
        "loaded_count": transformed_data["total_count"],
        "status": "success",
        "database": "users_db",
    }


def generate_report(context: WorkflowContext) -> dict:
    """Generate a processing report."""
    extract_data = context.get_step_output("extract")
    transform_data = context.get_step_output("transform")
    load_data = context.get_step_output("load")

    report = {
        "pipeline_summary": {
            "extracted_records": len(extract_data["users"]),
            "transformed_records": transform_data["total_count"],
            "loaded_records": load_data["loaded_count"],
            "success_rate": (load_data["loaded_count"] / len(extract_data["users"]))
            * 100,
        },
        "report_generated_at": "2024-01-01T00:00:00Z",
    }

    print(
        f"📊 Generated report: {report['pipeline_summary']['success_rate']:.1f}% success rate"
    )
    return report


def main():
    """Run the basic ETL workflow."""
    print("🚀 Starting Basic ETL Workflow Example\n")

    # Create the workflow steps
    steps = [
        Step(
            name="extract",
            step_type=StepType.FUNCTION,
            callable=extract_data,
        ),
        Step(
            name="transform",
            step_type=StepType.FUNCTION,
            callable=transform_data,
            dependencies=["extract"],
        ),
        Step(
            name="load",
            step_type=StepType.FUNCTION,
            callable=load_to_database,
            dependencies=["transform"],
        ),
        Step(
            name="report",
            step_type=StepType.FUNCTION,
            callable=generate_report,
            dependencies=["extract", "transform", "load"],
        ),
    ]

    # Create the job
    job = Job(
        name="Basic ETL Pipeline",
        steps=steps,
    )

    # Create and run the workflow
    engine = WorkflowEngine()

    print("📋 Workflow Execution Plan:")
    execution_plan = engine.get_execution_plan(job)
    execution_order = execution_plan["execution_order"]
    for phase_num, step_name in enumerate(execution_order, 1):
        print(f"   Step {phase_num}: {step_name}")

    print(f"\n🎯 Critical Path: {' → '.join(execution_plan['critical_path'][0])}")
    print(f"⏱️  Path Length: {execution_plan['critical_path'][1]} steps")

    if execution_plan["parallel_groups"]:
        print(f"🔀 Parallel Groups: {len(execution_plan['parallel_groups'])}")
        for i, group in enumerate(execution_plan["parallel_groups"], 1):
            print(
                f"   Group {i}: {', '.join(group)}"
            )  # group is already a list of step names
    print()

    # Execute the workflow
    job_run = engine.run(job)

    print(f"\n✅ Workflow completed with status: {job_run.status}")
    print(f"🆔 Job Run ID: {job_run.job_run_id}")
    print(
        f"⏱️  Duration: {job_run.duration_ms / 1000:.2f} seconds"
        if job_run.duration_ms
        else "⏱️  Duration: N/A"
    )

    # Show final report
    if job_run.status.value == "SUCCESS":
        # Get the report step's output
        report_step = next(
            (step for step in job_run.step_runs if step.step_name == "report"), None
        )
        if report_step and report_step.output_data:
            print(f"\n📈 Final Report:")
            print(json.dumps(report_step.output_data, indent=2))


if __name__ == "__main__":
    main()
