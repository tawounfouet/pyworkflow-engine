"""
Basic Example: Simple ETL Workflow

This example demonstrates a basic ETL (Extract, Transform, Load) workflow
using the PyWorkflow Engine, with integrated logging.
"""

from pyworkflow_engine import WorkflowEngine, Job, Step, StepType, WorkflowContext
from pyworkflow_engine.logging import (
    get_logger,
    configure_logging,
    LoggingConfig,
    logged_operation,
    shutdown_logging,
)
import json

logger = get_logger("examples.etl")


def extract_data(context: WorkflowContext) -> dict:
    """Extract data from source."""
    with logged_operation(logger, "data extraction"):
        data = {
            "users": [
                {"id": 1, "name": "Alice", "email": "alice@example.com", "age": 30},
                {"id": 2, "name": "Bob", "email": "bob@example.com", "age": 25},
                {"id": 3, "name": "Charlie", "email": "charlie@example.com", "age": 35},
            ]
        }
        logger.info("Extracted %d user records", len(data["users"]))
        return data


def transform_data(context: WorkflowContext) -> dict:
    """Transform the extracted data."""
    with logged_operation(logger, "data transformation"):
        source_data = context.get_step_output("extract")

        transformed_users = []
        for user in source_data["users"]:
            if user["age"] >= 25:
                user["full_email"] = f"{user['name']} <{user['email']}>"
                user["category"] = "adult" if user["age"] >= 30 else "young_adult"
                transformed_users.append(user)

        result = {
            "processed_users": transformed_users,
            "total_count": len(transformed_users),
            "processing_timestamp": "2024-01-01T00:00:00Z",
        }

        logger.info("Transformed data: %d users processed", result["total_count"])
        return result


def load_to_database(context: WorkflowContext) -> dict:
    """Load transformed data to database (simulated)."""
    with logged_operation(logger, "database loading"):
        transformed_data = context.get_step_output("transform")

        for user in transformed_data["processed_users"]:
            logger.debug("Inserting user: %s (%s)", user["name"], user["category"])

        return {
            "loaded_count": transformed_data["total_count"],
            "status": "success",
            "database": "users_db",
        }


def generate_report(context: WorkflowContext) -> dict:
    """Generate a processing report."""
    with logged_operation(logger, "report generation"):
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

        logger.info(
            "Report generated: %.1f%% success rate",
            report["pipeline_summary"]["success_rate"],
        )
        return report


def main():
    """Run the basic ETL workflow."""
    configure_logging(LoggingConfig(level="DEBUG"))
    logger.info("Starting Basic ETL Workflow Example")

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

    execution_plan = engine.get_execution_plan(job)
    execution_order = execution_plan["execution_order"]
    logger.info("Execution plan: %s", " → ".join(execution_order))
    logger.info(
        "Critical path: %s (%d steps)",
        " → ".join(execution_plan["critical_path"][0]),
        execution_plan["critical_path"][1],
    )

    if execution_plan["parallel_groups"]:
        for i, group in enumerate(execution_plan["parallel_groups"], 1):
            logger.debug("Parallel group %d: %s", i, ", ".join(group))

    # Execute the workflow
    with logged_operation(logger, "ETL pipeline execution"):
        job_run = engine.run(job)

    logger.info(
        "Workflow completed: status=%s, job_run_id=%s",
        job_run.status.value,
        job_run.job_run_id[:8],
    )
    if job_run.duration_ms:
        logger.info("Total duration: %.2fs", job_run.duration_ms / 1000)

    # Show final report
    if job_run.status.value == "SUCCESS":
        report_step = next(
            (step for step in job_run.step_runs if step.step_name == "report"), None
        )
        if report_step and report_step.output_data:
            logger.info("Final report:\n%s", json.dumps(report_step.output_data, indent=2))

    shutdown_logging()


if __name__ == "__main__":
    main()
