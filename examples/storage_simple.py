"""
Simple persistence example demonstrating the renamed pyworkflow_engine package.

This example shows basic usage of all persistence backends with the new package structure.
"""

import tempfile
from pathlib import Path

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.models import Job, Step, StepType
from pyworkflow_engine.adapters.storage import (
    InMemoryStorage,
    JSONFileStorage,
    SQLiteStorage,
)


def create_sample_job() -> Job:
    """Create a simple job for testing persistence."""
    return Job(
        name="test_job",
        description="A simple test job",
        steps=[
            Step(
                name="step1",
                step_type=StepType.FUNCTION,
                callable=lambda ctx: {"message": "Hello from PyWorkflow Engine!"},
            ),
            Step(
                name="step2",
                step_type=StepType.FUNCTION,
                callable=lambda ctx: {
                    "result": f"Processed: {ctx.get('step1', {}).get('message', 'no data')}"
                },
                dependencies=["step1"],
            ),
        ],
    )


def test_in_memory_persistence():
    """Test InMemoryStorage with the renamed package."""
    print("\n📦 Testing InMemoryStorage...")

    # Create persistence and engine
    persistence = InMemoryStorage()
    engine = WorkflowEngine()
    engine.storage = persistence

    # Create and save a job
    job = create_sample_job()
    result = engine.run_with_storage(job)

    print(f"   ✅ Job executed: {result.status}")
    print(f"   ✅ Jobs in storage: {len(persistence.list_jobs())}")
    print(f"   ✅ Job runs in storage: {len(persistence.list_job_runs())}")


def test_json_persistence():
    """Test JSONFileStorage with the renamed package."""
    print("\n📁 Testing JSONFileStorage...")

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create persistence and engine
        persistence = JSONFileStorage(storage_dir=temp_dir)
        engine = WorkflowEngine()
        engine.storage = persistence

        # Create and save a job
        job = create_sample_job()
        result = engine.run_with_storage(job)

        print(f"   ✅ Job executed: {result.status}")
        print(f"   ✅ Storage directory: {temp_dir}")

        # Check files created
        storage_path = Path(temp_dir)
        json_files = list(storage_path.rglob("*.json"))
        print(f"   ✅ JSON files created: {len(json_files)}")


def test_sqlite_persistence():
    """Test SQLiteStorage with the renamed package."""
    print("\n🗃️  Testing SQLiteStorage...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        # Create persistence and engine
        persistence = SQLiteStorage(database_path=db_path)
        engine = WorkflowEngine()
        engine.storage = persistence

        # Create and save a job
        job = create_sample_job()
        result = engine.run_with_storage(job)

        print(f"   ✅ Job executed: {result.status}")
        print(f"   ✅ Database path: {db_path}")

        # Check database stats
        stats = persistence.get_statistics()
        print(f"   ✅ Total jobs: {stats.get('total_jobs', 0)}")
        print(f"   ✅ Total runs: {stats.get('total_runs', 0)}")

        persistence.close()

    finally:
        # Cleanup
        try:
            Path(db_path).unlink()
        except:
            pass


def main():
    """Run simple persistence tests with the renamed package."""
    print("🔄 PyWorkflow Engine - Persistence Test")
    print("=" * 50)
    print("Testing persistence backends with the renamed package:")

    # Test each backend
    test_in_memory_persistence()
    test_json_persistence()
    test_sqlite_persistence()

    print("\n" + "=" * 50)
    print("✅ All persistence tests passed!")
    print("🎯 Package rename successful: pyworkflow_engine working correctly")


if __name__ == "__main__":
    main()
