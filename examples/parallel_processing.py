"""
Parallel Processing Example: Data Processing Pipeline

This example demonstrates parallel execution capabilities with multiple
concurrent data processing steps.
"""

from ias_workflow_engine import WorkflowEngine, Job, Step, StepType, WorkflowContext
import time
import random


def load_dataset(context: WorkflowContext) -> dict:
    """Load initial dataset."""
    print("📊 Loading dataset...")
    time.sleep(0.2)  # Simulate I/O time

    dataset = {
        "sales_data": [
            {
                "id": i,
                "product": f"Product-{i%5}",
                "amount": random.uniform(10, 500),
                "region": random.choice(["North", "South", "East", "West"]),
            }
            for i in range(50)  # Small dataset for demo
        ],
        "total_records": 50,
    }

    print(f"📊 Loaded {dataset['total_records']} records")
    return dataset


def analyze_regions(context: WorkflowContext) -> dict:
    """Analyze data by region (parallel task)."""
    print("🌍 Analyzing regions...")
    time.sleep(0.3)

    dataset = context.get_step_output("load_data")
    regional_stats = {}

    for record in dataset["sales_data"]:
        region = record["region"]
        if region not in regional_stats:
            regional_stats[region] = {"count": 0, "total": 0}
        regional_stats[region]["count"] += 1
        regional_stats[region]["total"] += record["amount"]

    print(f"🌍 Processed {len(regional_stats)} regions")
    return {"regional_stats": regional_stats}


def analyze_products(context: WorkflowContext) -> dict:
    """Analyze data by product (parallel task)."""
    print("📦 Analyzing products...")
    time.sleep(0.4)

    dataset = context.get_step_output("load_data")
    product_stats = {}

    for record in dataset["sales_data"]:
        product = record["product"]
        if product not in product_stats:
            product_stats[product] = {"count": 0, "total": 0}
        product_stats[product]["count"] += 1
        product_stats[product]["total"] += record["amount"]

    print(f"📦 Processed {len(product_stats)} products")
    return {"product_stats": product_stats}


def generate_report(context: WorkflowContext) -> dict:
    """Generate final report combining all analyses."""
    print("📋 Generating final report...")

    regional_data = context.get_step_output("regional_analysis")
    product_data = context.get_step_output("product_analysis")

    # Find top performers
    top_region = max(
        regional_data["regional_stats"].items(), key=lambda x: x[1]["total"]
    )
    top_product = max(
        product_data["product_stats"].items(), key=lambda x: x[1]["total"]
    )

    report = {
        "top_region": {"name": top_region[0], "sales": top_region[1]["total"]},
        "top_product": {"name": top_product[0], "sales": top_product[1]["total"]},
        "total_regions": len(regional_data["regional_stats"]),
        "total_products": len(product_data["product_stats"]),
    }

    print(
        f"📋 Report generated - Top region: {top_region[0]}, Top product: {top_product[0]}"
    )
    return report


def main():
    """Run the parallel processing workflow example."""
    print("🚀 Parallel Processing Workflow Example\n")

    # Create workflow with parallel steps
    steps = [
        Step(name="load_data", step_type=StepType.FUNCTION, callable=load_dataset),
        Step(
            name="regional_analysis",
            step_type=StepType.FUNCTION,
            callable=analyze_regions,
            dependencies=["load_data"],
        ),
        Step(
            name="product_analysis",
            step_type=StepType.FUNCTION,
            callable=analyze_products,
            dependencies=["load_data"],
        ),
        Step(
            name="final_report",
            step_type=StepType.FUNCTION,
            callable=generate_report,
            dependencies=["regional_analysis", "product_analysis"],
        ),
    ]

    job = Job(name="Parallel Analytics Pipeline", steps=steps)
    engine = WorkflowEngine()

    # Show execution plan
    plan = engine.get_execution_plan(job)
    print(f"📋 Execution Order: {' → '.join(plan['execution_order'])}")
    print(f"🎯 Critical Path: {' → '.join(plan['critical_path'][0])}")

    if plan["parallel_groups"]:
        print(f"🔀 Parallel Groups: {len(plan['parallel_groups'])}")
        for i, group in enumerate(plan["parallel_groups"], 1):
            print(f"   Group {i}: {', '.join(group)}")

    # Execute workflow
    print(f"\n▶️  Starting execution...")
    start_time = time.time()

    job_run = engine.run(job)

    duration = time.time() - start_time

    print(f"\n✅ Status: {job_run.status}")
    print(f"⏱️  Duration: {duration:.2f} seconds")

    # Show results
    if job_run.status.value == "success":
        report_step = next(
            (s for s in job_run.step_runs if s.step_name == "final_report"), None
        )
        if report_step and report_step.output_data:
            report = report_step.output_data
            print(f"\n📊 Results:")
            print(
                f"   🏆 Top Region: {report['top_region']['name']} (${report['top_region']['sales']:.0f})"
            )
            print(
                f"   🏆 Top Product: {report['top_product']['name']} (${report['top_product']['sales']:.0f})"
            )
            print(
                f"   📈 Analysis completed in {duration:.1f}s with parallel processing"
            )


if __name__ == "__main__":
    main()
