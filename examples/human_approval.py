"""
Advanced Example: Human Approval Workflow with Suspension

This example demonstrates a workflow that requires human approval,
showcasing the suspension and resumption capabilities.
"""

from ias_workflow_engine import (
    WorkflowEngine,
    Job,
    Step,
    StepType,
    WorkflowSuspended,
    WorkflowContext,
)
import json
import time


def prepare_approval_request(context: WorkflowContext) -> dict:
    """Prepare data for approval request."""
    # Get initial context data
    expense_data = context.get("expense_request", {})

    approval_request = {
        "request_id": f"REQ-{int(time.time())}",
        "amount": expense_data.get("amount", 1500.00),
        "category": expense_data.get("category", "Travel"),
        "description": expense_data.get(
            "description", "Business conference attendance"
        ),
        "requested_by": expense_data.get("requested_by", "John Doe"),
        "approval_level": (
            "manager" if expense_data.get("amount", 0) < 5000 else "director"
        ),
        "prepared_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    print(f"📝 Prepared approval request: {approval_request['request_id']}")
    print(f"💰 Amount: ${approval_request['amount']:.2f}")
    print(f"👤 Requested by: {approval_request['requested_by']}")

    return approval_request


def request_human_approval(context: WorkflowContext) -> dict:
    """Request human approval - this step will suspend the workflow."""
    approval_request = context.get_step_output("prepare_request")

    print(f"⏸️  Suspending workflow for human approval...")
    print(f"📋 Approval needed for request: {approval_request['request_id']}")
    print(f"🎯 Amount: ${approval_request['amount']:.2f}")

    # This suspends the workflow - it will need to be resumed externally
    raise WorkflowSuspended(
        message=f"Human approval required for expense request {approval_request['request_id']}",
        reason=f"Human approval required for expense request {approval_request['request_id']}",
    )


def process_approval(context: WorkflowContext) -> dict:
    """Process the approval decision (called after resume)."""
    approval_request = context.get_step_output("prepare_request")

    # In a real system, approval_decision would come from external input
    # For this example, we'll check if it was provided in context during resume
    approval_decision = context.get("approval_decision", {})

    if not approval_decision:
        # Default to approved for demo purposes
        approval_decision = {
            "approved": True,
            "approved_by": "Manager Jane Smith",
            "approved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "comments": "Approved - valid business expense",
        }

    result = {
        "request_id": approval_request["request_id"],
        "decision": approval_decision,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    status = "APPROVED" if approval_decision.get("approved") else "REJECTED"
    print(f"✅ Approval processed: {status}")
    print(f"👔 Approved by: {approval_decision.get('approved_by', 'Unknown')}")

    return result


def finalize_request(context: WorkflowContext) -> dict:
    """Finalize the expense request based on approval."""
    approval_request = context.get_step_output("prepare_request")
    approval_result = context.get_step_output("process_approval")

    if approval_result["decision"].get("approved"):
        # Process approved expense
        final_result = {
            "status": "PROCESSED",
            "request_id": approval_request["request_id"],
            "amount_disbursed": approval_request["amount"],
            "payment_method": "Direct Deposit",
            "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reference_number": f"PAY-{int(time.time())}",
        }
        print(f"💸 Payment processed: ${final_result['amount_disbursed']:.2f}")
        print(f"🆔 Reference: {final_result['reference_number']}")
    else:
        # Handle rejection
        final_result = {
            "status": "REJECTED",
            "request_id": approval_request["request_id"],
            "rejection_reason": approval_result["decision"].get(
                "comments", "Not approved"
            ),
            "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        print(f"❌ Request rejected: {final_result['rejection_reason']}")

    return final_result


def main():
    """Run the human approval workflow example."""
    print("🚀 Starting Human Approval Workflow Example\n")

    # Create workflow steps
    steps = [
        Step(
            name="prepare_request",
            step_type=StepType.FUNCTION,
            callable=prepare_approval_request,
        ),
        Step(
            name="request_approval",
            step_type=StepType.FUNCTION,
            callable=request_human_approval,
            dependencies=["prepare_request"],
        ),
        Step(
            name="process_approval",
            step_type=StepType.FUNCTION,
            callable=process_approval,
            dependencies=["request_approval"],
        ),
        Step(
            name="finalize",
            step_type=StepType.FUNCTION,
            callable=finalize_request,
            dependencies=["process_approval"],
        ),
    ]

    # Create the job
    job = Job(
        name="Expense Approval Workflow",
        steps=steps,
    )

    # Create engine and initial context
    engine = WorkflowEngine()

    initial_context = {
        "expense_request": {
            "amount": 2500.00,
            "category": "Travel",
            "description": "Annual tech conference - accommodation and travel",
            "requested_by": "Alice Johnson",
        }
    }

    print("📋 Initial Context:")
    print(json.dumps(initial_context, indent=2))
    print()

    # Execute workflow (may suspend)
    job_run = engine.run(job, initial_context=initial_context)

    print(
        f"🔍 DEBUG: Workflow status is '{job_run.status.value}' (checking for 'suspended')"
    )

    if job_run.status.value == "suspended":
        print(
            f"⏸️  Workflow suspended: {job_run.metadata.get('suspend_reason', 'Unknown reason')}"
        )
        print(f"🆔 Suspended Job Run ID: {job_run.job_run_id}")

        # Simulate human approval process
        print("\n🤔 Simulating human approval process...")
        time.sleep(1)

        # Resume with approval decision
        resume_context = {
            "approval_decision": {
                "approved": True,
                "approved_by": "Manager Sarah Wilson",
                "approved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "comments": "Approved - legitimate business expense for conference",
            }
        }

        print("▶️  Resuming workflow with approval...")
        resumed_job_run = engine.resume(job_run.job_run_id, resume_context)

        print(f"\n✅ Workflow completed: {resumed_job_run.status}")
        print(
            f"⏱️  Total duration: {resumed_job_run.duration_ms / 1000:.2f} seconds"
            if resumed_job_run.duration_ms
            else "⏱️  Duration: N/A"
        )

        # Show final result - get from step_runs
        final_result_step = next(
            (
                step
                for step in resumed_job_run.step_runs
                if step.step_name == "finalize"
            ),
            None,
        )
        if final_result_step and final_result_step.output_data:
            print(f"\n📊 Final Result:")
            print(json.dumps(final_result_step.output_data, indent=2))
    else:
        print(f"✅ Workflow completed: {job_run.status}")
        print(
            f"⏱️  Duration: {job_run.duration_ms / 1000:.2f} seconds"
            if job_run.duration_ms
            else "⏱️  Duration: N/A"
        )


def demo_rejection_flow():
    """Demonstrate the rejection flow."""
    print("\n" + "=" * 60)
    print("🚀 Demo: Rejection Flow\n")

    # Create the same job
    steps = [
        Step(
            name="prepare_request",
            step_type=StepType.FUNCTION,
            callable=prepare_approval_request,
        ),
        Step(
            name="request_approval",
            step_type=StepType.FUNCTION,
            callable=request_human_approval,
            dependencies=["prepare_request"],
        ),
        Step(
            name="process_approval",
            step_type=StepType.FUNCTION,
            callable=process_approval,
            dependencies=["request_approval"],
        ),
        Step(
            name="finalize",
            step_type=StepType.FUNCTION,
            callable=finalize_request,
            dependencies=["process_approval"],
        ),
    ]

    job = Job(name="Expense Approval Workflow", steps=steps)
    engine = WorkflowEngine()

    # Higher amount expense
    initial_context = {
        "expense_request": {
            "amount": 8500.00,
            "category": "Equipment",
            "description": "High-end laptop for development work",
            "requested_by": "Bob Developer",
        }
    }

    try:
        job_run = engine.run(job, initial_context=initial_context)
    except:
        suspended_runs = [
            run for run in engine._job_runs.values() if run.status.value == "SUSPENDED"
        ]
        if suspended_runs:
            job_run = suspended_runs[0]

            # Reject this time
            resume_context = {
                "approval_decision": {
                    "approved": False,
                    "approved_by": "Director Mike Chen",
                    "approved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "comments": "Rejected - amount exceeds budget limits for current quarter",
                }
            }

            print("▶️  Resuming workflow with rejection...")
            resumed_job_run = engine.resume_workflow(job_run.job_run_id, resume_context)

            final_result = engine.get_step_output(
                resumed_job_run.job_run_id, "finalize"
            )
            print(f"\n📊 Final Result:")
            print(json.dumps(final_result, indent=2))


if __name__ == "__main__":
    main()
    demo_rejection_flow()
