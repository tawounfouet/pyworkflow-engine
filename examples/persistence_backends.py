"""
Comprehensive examples of using different persistence backends.

This example demonstrates how to use each persistence backend
and shows their specific features and use cases.
"""

import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.core.models import Job, Step
from pyworkflow_engine.persistence import (
    InMemoryPersistence,
    JSONFilePersistence,
    SQLitePersistence,
)

# Try to import SQLAlchemy persistence (optional)
try:
    from pyworkflow_engine.persistence import SQLAlchemyPersistence
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False
    print("SQLAlchemy not available. Install with: pip install ias-workflow-engine[sqlalchemy]")


def create_sample_job() -> Job:
    """Create a sample job for demonstration."""
    return Job(
        name="data_processing_job",
        description="A sample data processing workflow",
        parameters={"batch_size": 1000, "timeout": 300},
        steps=[
            Step(
                name="extract_data",
                type="function",
                function="extract_from_source",
                parameters={"source": "database", "query": "SELECT * FROM raw_data"},
                depends_on=set(),
                timeout=120,
            ),
            Step(
                name="transform_data",
                type="function",
                function="apply_transformations",
                parameters={"rules": ["normalize", "validate", "enrich"]},
                depends_on={"extract_data"},
                timeout=180,
            ),
            Step(
                name="load_data",
                type="function",
                function="load_to_target",
                parameters={"target": "warehouse", "table": "processed_data"},
                depends_on={"transform_data"},
                timeout=60,
            ),
        ],
        metadata={
            "version": "1.0",
            "author": "data-team",
            "tags": ["etl", "daily"],
        },
    )


def demo_in_memory_persistence():
    """Demonstrate InMemoryPersistence usage."""
    print("\n" + "="*60)
    print("IN-MEMORY PERSISTENCE DEMO")
    print("="*60)
    
    # Create persistence backend
    persistence = InMemoryPersistence()
    engine = WorkflowEngine(persistence=persistence)
    
    print(f"✓ Created InMemoryPersistence backend")
    
    # Save a job
    job = create_sample_job()
    persistence.save_job(job)
    print(f"✓ Saved job: {job.name}")
    
    # List jobs
    jobs = persistence.list_jobs()
    print(f"✓ Jobs in storage: {len(jobs)}")
    
    # Test transaction support
    print("\nTesting transaction support...")
    try:
        with persistence.transaction():
            # Create a temporary job
            temp_job = Job(
                name="temp_job",
                description="Temporary job for testing",
                parameters={},
                steps=[
                    Step(
                        name="temp_step",
                        type="function",
                        function="temp_function",
                        parameters={},
                        depends_on=set(),
                    )
                ],
                metadata={},
            )
            persistence.save_job(temp_job)
            print(f"  - Saved temporary job: {temp_job.name}")
            
            # Simulate an error to trigger rollback
            raise ValueError("Simulated error for rollback test")
            
    except ValueError:
        print(f"  - Transaction rolled back due to error")
    
    # Verify rollback worked
    jobs_after = persistence.list_jobs()
    print(f"✓ Jobs after rollback: {len(jobs_after)} (should be same as before)")
    
    # Check health and statistics
    health = persistence.health_check()
    stats = persistence.get_statistics()
    
    print(f"✓ Backend health: {health['status']}")
    print(f"✓ Memory usage: {stats.get('estimated_memory_bytes', 0)} bytes")
    
    print(f"\nInMemoryPersistence is perfect for:")
    print(f"  - Development and testing")
    print(f"  - Temporary workflows")
    print(f"  - High-performance scenarios where data loss is acceptable")


def demo_json_file_persistence():
    """Demonstrate JSONFilePersistence usage."""
    print("\n" + "="*60)
    print("JSON FILE PERSISTENCE DEMO")
    print("="*60)
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")
        
        # Create persistence backend
        persistence = JSONFilePersistence(storage_dir=temp_dir)
        engine = WorkflowEngine(persistence=persistence)
        
        print(f"✓ Created JSONFilePersistence backend")
        
        # Save jobs
        job = create_sample_job()
        persistence.save_job(job)
        print(f"✓ Saved job: {job.name}")
        
        # Show file structure
        storage_path = Path(temp_dir)
        print(f"\nFile structure created:")
        for path in storage_path.rglob("*"):
            if path.is_file():
                relative_path = path.relative_to(storage_path)
                size = path.stat().st_size
                print(f"  {relative_path} ({size} bytes)")
        
        # Test atomic operations
        print(f"\nTesting atomic file operations...")
        start_time = time.time()
        for i in range(10):
            test_job = Job(
                name=f"test_job_{i}",
                description=f"Test job {i}",
                parameters={"index": i},
                steps=[
                    Step(
                        name="test_step",
                        type="function",
                        function="test_function",
                        parameters={"value": i},
                        depends_on=set(),
                    )
                ],
                metadata={"batch": "test"},
            )
            persistence.save_job(test_job)
        
        elapsed = time.time() - start_time
        print(f"✓ Saved 10 jobs in {elapsed:.3f} seconds")
        
        # Verify no temporary files left behind
        temp_files = list(storage_path.rglob("*.tmp"))
        print(f"✓ No temporary files left behind: {len(temp_files) == 0}")
        
        # Test file-based transaction (limited support)
        print(f"\nTesting file-based transactions...")
        initial_count = len(persistence.list_jobs())
        
        persistence.begin_transaction()
        for i in range(3):
            tx_job = Job(
                name=f"tx_job_{i}",
                description="Transaction test job",
                parameters={},
                steps=[
                    Step(
                        name="tx_step",
                        type="function", 
                        function="tx_function",
                        parameters={},
                        depends_on=set(),
                    )
                ],
                metadata={},
            )
            persistence.save_job(tx_job)
        
        persistence.commit_transaction()
        final_count = len(persistence.list_jobs())
        print(f"✓ Jobs before transaction: {initial_count}")
        print(f"✓ Jobs after transaction: {final_count}")
        
        # Health check
        health = persistence.health_check()
        stats = persistence.get_statistics()
        
        print(f"✓ Backend health: {health['status']}")
        print(f"✓ Storage directory: {health['storage_directory']}")
        print(f"✓ Total jobs: {stats['total_jobs']}")
        print(f"✓ Storage size: {stats['storage_size_bytes']} bytes")
        
        print(f"\nJSONFilePersistence is perfect for:")
        print(f"  - Small to medium deployments")
        print(f"  - Human-readable storage format")
        print(f"  - Simple backup and version control")
        print(f"  - Cross-platform compatibility")


def demo_sqlite_persistence():
    """Demonstrate SQLitePersistence usage."""
    print("\n" + "="*60)
    print("SQLITE PERSISTENCE DEMO")
    print("="*60)
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        print(f"Using temporary database: {db_path}")
        
        # Create persistence backend
        persistence = SQLitePersistence(database_path=db_path)
        engine = WorkflowEngine(persistence=persistence)
        
        print(f"✓ Created SQLitePersistence backend")
        
        # Save job and job runs
        job = create_sample_job()
        persistence.save_job(job)
        print(f"✓ Saved job: {job.name}")
        
        # Create some job runs with different statuses
        from pyworkflow_engine.core.models import JobRun, JobRunStatus
        
        statuses = [JobRunStatus.COMPLETED, JobRunStatus.FAILED, JobRunStatus.RUNNING]
        now = datetime.utcnow()
        
        for i, status in enumerate(statuses * 3):  # 9 runs total
            job_run = JobRun(
                id=f"run_{i:03d}",
                job_name=job.name,
                status=status,
                created_at=now - timedelta(hours=i),
                started_at=now - timedelta(hours=i),
                completed_at=now - timedelta(hours=i) + timedelta(minutes=30) if status != JobRunStatus.RUNNING else None,
                parameters={"run_index": i, "batch_id": f"batch_{i // 3}"},
                metadata={"environment": "demo", "priority": i % 3},
                step_runs=[],
            )
            persistence.save_job_run(job_run)
        
        print(f"✓ Created 9 job runs with different statuses")
        
        # Test advanced querying
        print(f"\nTesting advanced querying...")
        
        # Query by status
        completed_runs = persistence.list_job_runs(status="completed")
        failed_runs = persistence.list_job_runs(status="failed")
        running_runs = persistence.list_job_runs(status="running")
        
        print(f"  - Completed runs: {len(completed_runs)}")
        print(f"  - Failed runs: {len(failed_runs)}")
        print(f"  - Running runs: {len(running_runs)}")
        
        # Query recent runs
        recent_cutoff = now - timedelta(hours=3)
        recent_runs = persistence.list_job_runs(since=recent_cutoff)
        print(f"  - Recent runs (last 3 hours): {len(recent_runs)}")
        
        # Test pagination
        page_1 = persistence.list_job_runs(limit=3, offset=0)
        page_2 = persistence.list_job_runs(limit=3, offset=3)
        print(f"  - Page 1 (3 runs): {[r.id for r in page_1]}")
        print(f"  - Page 2 (3 runs): {[r.id for r in page_2]}")
        
        # Test cleanup
        print(f"\nTesting cleanup operations...")
        old_cutoff = now - timedelta(hours=5)
        deleted_count = persistence.cleanup_old_runs(old_cutoff)
        print(f"✓ Cleaned up {deleted_count} old runs")
        
        remaining_count = persistence.get_job_run_count()
        print(f"✓ Remaining runs: {remaining_count}")
        
        # Test transactions
        print(f"\nTesting ACID transactions...")
        initial_job_count = len(persistence.list_jobs())
        
        try:
            persistence.begin_transaction()
            
            # Add multiple jobs in transaction
            for i in range(3):
                tx_job = Job(
                    name=f"tx_job_{i}",
                    description="Transaction test",
                    parameters={},
                    steps=[
                        Step(
                            name="tx_step",
                            type="function",
                            function="tx_function",
                            parameters={},
                            depends_on=set(),
                        )
                    ],
                    metadata={},
                )
                persistence.save_job(tx_job)
            
            # Simulate error to test rollback
            if False:  # Set to True to test rollback
                raise ValueError("Simulated transaction error")
            
            persistence.commit_transaction()
            print(f"✓ Transaction committed successfully")
            
        except Exception as e:
            persistence.rollback_transaction()
            print(f"✓ Transaction rolled back: {e}")
        
        final_job_count = len(persistence.list_jobs())
        print(f"  - Jobs before: {initial_job_count}")
        print(f"  - Jobs after: {final_job_count}")
        
        # Check database info
        health = persistence.health_check()
        stats = persistence.get_statistics()
        
        print(f"✓ Backend health: {health['status']}")
        print(f"✓ Database path: {health['database_path']}")
        print(f"✓ Database size: {health['database_size_bytes']} bytes")
        print(f"✓ Total jobs: {stats['total_jobs']}")
        print(f"✓ Total runs: {stats['total_runs']}")
        print(f"✓ Status distribution: {stats.get('status_counts', {})}")
        
        print(f"\nSQLitePersistence is perfect for:")
        print(f"  - Production deployments (single-node)")
        print(f"  - ACID compliance requirements")
        print(f"  - Complex querying and reporting")
        print(f"  - Reliable data persistence")
        
    finally:
        # Cleanup
        try:
            persistence.close()
            Path(db_path).unlink()
        except:
            pass


def demo_sqlalchemy_persistence():
    """Demonstrate SQLAlchemyPersistence usage."""
    if not HAS_SQLALCHEMY:
        print("\n" + "="*60)
        print("SQLALCHEMY PERSISTENCE - NOT AVAILABLE")
        print("="*60)
        print("Install with: pip install ias-workflow-engine[sqlalchemy]")
        return
    
    print("\n" + "="*60)
    print("SQLALCHEMY PERSISTENCE DEMO")
    print("="*60)
    
    # Use in-memory SQLite for demo
    database_url = "sqlite:///:memory:"
    print(f"Using database: {database_url}")
    
    # Create persistence backend
    persistence = SQLAlchemyPersistence(
        database_url=database_url,
        engine_options={"echo": False},  # Set to True to see SQL queries
    )
    engine = WorkflowEngine(persistence=persistence)
    
    print(f"✓ Created SQLAlchemyPersistence backend")
    
    # Test bulk operations
    print(f"\nTesting bulk operations...")
    job = create_sample_job()
    persistence.save_job(job)
    
    # Create many job runs to test performance
    from pyworkflow_engine.core.models import JobRun, JobRunStatus
    
    start_time = time.time()
    job_runs = []
    
    for i in range(50):
        job_run = JobRun(
            id=f"bulk_run_{i:03d}",
            job_name=job.name,
            status=JobRunStatus.COMPLETED,
            created_at=datetime.utcnow() - timedelta(minutes=i),
            started_at=datetime.utcnow() - timedelta(minutes=i),
            completed_at=datetime.utcnow() - timedelta(minutes=i) + timedelta(seconds=30),
            parameters={"batch": i // 10, "index": i},
            metadata={"performance_test": True},
            step_runs=[],
        )
        persistence.save_job_run(job_run)
        job_runs.append(job_run)
    
    bulk_time = time.time() - start_time
    print(f"✓ Saved 50 job runs in {bulk_time:.3f} seconds")
    
    # Test advanced querying
    print(f"\nTesting advanced querying...")
    
    # Complex filters
    recent_runs = persistence.list_job_runs(
        job_name=job.name,
        status="completed",
        limit=10,
        since=datetime.utcnow() - timedelta(minutes=25)
    )
    print(f"  - Recent completed runs: {len(recent_runs)}")
    
    # Count operations
    total_count = persistence.get_job_run_count()
    job_count = persistence.get_job_run_count(job_name=job.name)
    print(f"  - Total runs: {total_count}")
    print(f"  - Runs for job '{job.name}': {job_count}")
    
    # Test connection pooling
    print(f"\nTesting connection pooling...")
    concurrent_health_checks = []
    for i in range(10):
        health = persistence.health_check()
        concurrent_health_checks.append(health["status"])
    
    all_healthy = all(status == "healthy" for status in concurrent_health_checks)
    print(f"✓ Concurrent operations: {all_healthy}")
    
    # Engine information
    health = persistence.health_check()
    stats = persistence.get_statistics()
    
    print(f"✓ Backend health: {health['status']}")
    print(f"✓ Database dialect: {health['engine_info']['dialect']}")
    print(f"✓ Database driver: {health['engine_info']['driver']}")
    print(f"✓ Total jobs: {stats['total_jobs']}")
    print(f"✓ Total runs: {stats['total_runs']}")
    
    # Cleanup
    persistence.close()
    
    print(f"\nSQLAlchemyPersistence is perfect for:")
    print(f"  - Enterprise production deployments")
    print(f"  - Multiple database backend support")
    print(f"  - High-performance bulk operations")
    print(f"  - Advanced querying and analytics")
    print(f"  - Connection pooling and scaling")


def demo_persistence_comparison():
    """Compare different persistence backends."""
    print("\n" + "="*60)
    print("PERSISTENCE BACKENDS COMPARISON")
    print("="*60)
    
    print(f"""
Backend Comparison Summary:

┌─────────────────┬────────────┬───────────────┬──────────────┬─────────────────┐
│ Backend         │ Setup      │ Performance   │ Features     │ Best For        │
├─────────────────┼────────────┼───────────────┼──────────────┼─────────────────┤
│ InMemory        │ Zero       │ Fastest       │ Transactions │ Dev/Testing     │
│ JSONFile        │ Minimal    │ Good          │ Human-read   │ Small Deploy    │
│ SQLite          │ Easy       │ Very Good     │ ACID/Query   │ Production      │
│ SQLAlchemy      │ Medium     │ Excellent     │ Enterprise   │ Large Scale     │
└─────────────────┴────────────┴───────────────┴──────────────┴─────────────────┘

Dependencies:
  • InMemoryPersistence: None (stdlib only)
  • JSONFilePersistence: None (stdlib only)
  • SQLitePersistence: None (stdlib only)
  • SQLAlchemyPersistence: pip install ias-workflow-engine[sqlalchemy]

Storage:
  • InMemoryPersistence: RAM only (lost on restart)
  • JSONFilePersistence: JSON files on disk
  • SQLitePersistence: SQLite database file
  • SQLAlchemyPersistence: Any SQL database (PostgreSQL, MySQL, etc.)

Transactions:
  • InMemoryPersistence: Full rollback support via snapshots
  • JSONFilePersistence: Limited (queued operations)
  • SQLitePersistence: Full ACID transactions
  • SQLAlchemyPersistence: Full ACID transactions + connection pooling

Use Cases:
  • Development: InMemoryPersistence
  • CI/CD Testing: InMemoryPersistence or SQLite
  • Small Production: JSONFilePersistence or SQLitePersistence
  • Enterprise: SQLAlchemyPersistence with PostgreSQL
  • Analytics: SQLAlchemyPersistence for complex queries
    """)


def main():
    """Run all persistence backend demonstrations."""
    print("IAS Workflow Engine - Persistence Backends Demo")
    print("=" * 80)
    
    # Run demonstrations
    demo_in_memory_persistence()
    demo_json_file_persistence()
    demo_sqlite_persistence()
    demo_sqlalchemy_persistence()
    demo_persistence_comparison()
    
    print("\n" + "="*80)
    print("All persistence backend demonstrations completed!")
    print("Choose the backend that best fits your use case.")
    print("="*80)


if __name__ == "__main__":
    main()
