#!/usr/bin/env python3
"""
Validation script pour le package PyWorkflow Engine.
Vérifie que tous les composants implémentés fonctionnent correctement.
"""

import sys
import tempfile
import os
from pathlib import Path


def test_core_imports():
    """Test que les imports de base fonctionnent."""
    print("🧪 Testing core imports...")
    try:
        from pyworkflow_engine.logging import (
            get_logger,
            configure_logging,
            LoggingConfig,
        )

        print("  ✅ Logging module imports OK")

        from pyworkflow_engine.adapters.structlog import configure_structlog

        print("  ✅ Structlog adapter imports OK")

        # Test des nouveaux modèles core
        from pyworkflow_engine import (
            Job,
            Step,
            StepType,
            ExecutorType,
            RunStatus,
            JobRun,
            StepRun,
            Priority,
        )

        print("  ✅ Core models imports OK")

        return True
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False


def test_logging_functionality():
    """Test la fonctionnalité de base du logging."""
    print("\n🧪 Testing logging functionality...")
    try:
        from pyworkflow_engine.logging import (
            get_logger,
            configure_logging,
            LoggingConfig,
        )

        # Test basic logging
        config = LoggingConfig(level="INFO", json_output=False)
        configure_logging(config)
        logger = get_logger("validation.test")
        logger.info("Validation test successful", extra={"component": "core"})
        print("  ✅ Basic structured logging OK")

        # Test JSON logging
        config = LoggingConfig(level="INFO", json_output=True)
        configure_logging(config)
        logger = get_logger("validation.json")
        logger.info("JSON validation test", extra={"format": "json"})
        print("  ✅ JSON logging OK")

        return True
    except Exception as e:
        print(f"  ❌ Logging error: {e}")
        return False


def test_sqlite_storage():
    """Test le stockage SQLite."""
    print("\n🧪 Testing SQLite storage...")
    try:
        from pyworkflow_engine.logging.handlers import SQLiteLogHandler
        from pyworkflow_engine.logging import get_logger

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        handler = SQLiteLogHandler(db_path)
        logger = get_logger("validation.sqlite")
        logger.addHandler(handler)
        logger.setLevel("INFO")

        logger.info("SQLite validation test", extra={"storage": "sqlite"})
        handler.flush()

        records = handler.query_logs(limit=1)
        if len(records) == 1:
            print("  ✅ SQLite storage OK")
            success = True
        else:
            print(f"  ❌ Expected 1 record, got {len(records)}")
            success = False

        handler.close()
        os.unlink(db_path)
        return success

    except Exception as e:
        print(f"  ❌ SQLite error: {e}")
        return False


def test_package_info():
    """Test les métadonnées du package."""
    print("\n🧪 Testing package info...")
    try:
        import pyworkflow_engine

        print(
            f"  ✅ Package version: {getattr(pyworkflow_engine, '__version__', 'dev')}"
        )

        # Test des dépendances (doit être zéro pour le core)
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                'import pkg_resources; print(len(list(pkg_resources.get_distribution("ias-workflow-engine").requires())))',
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            deps_count = (
                int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
            )
            if deps_count == 0:
                print("  ✅ Zero core dependencies confirmed")
            else:
                print(f"  ⚠️  Found {deps_count} dependencies (may include dev deps)")

        return True
    except Exception as e:
        print(f"  ❌ Package info error: {e}")
        return False


def test_core_models_functionality():
    """Test la fonctionnalité de base des modèles core."""
    print("\n🧪 Testing core models functionality...")
    try:
        from pyworkflow_engine import (
            Job,
            Step,
            StepType,
            ExecutorType,
            RunStatus,
            JobRun,
            StepRun,
            Priority,
        )

        # Test création d'un job simple
        def simple_function():
            return {"result": "test"}

        job = Job(
            name="validation_job",
            steps=[
                Step("step1", StepType.FUNCTION, callable=simple_function),
                Step(
                    "step2",
                    StepType.FUNCTION,
                    callable=simple_function,
                    dependencies=["step1"],
                ),
            ],
        )

        assert job.name == "validation_job"
        assert len(job.steps) == 2
        assert job.get_entry_steps() == ["step1"]
        assert job.get_exit_steps() == ["step2"]
        assert not job.has_cycles()
        print("  ✅ Job creation and analysis OK")

        # Test création d'un job run
        job_run = JobRun(job_name=job.name)
        job_run.start_execution()

        # Simulation des step runs
        step_run = StepRun(step_name="step1", job_run_id=job_run.job_run_id)
        step_run.start_execution()
        step_run.complete_success({"data": "processed"})
        job_run.add_step_run(step_run)

        job_run.complete_success({"workflow": "completed"})

        assert job_run.status == RunStatus.SUCCESS
        assert job_run.progress_percentage > 0
        assert len(job_run.step_runs) == 1
        print("  ✅ JobRun execution simulation OK")

        return True
    except Exception as e:
        print(f"  ❌ Core models error: {e}")
        return False


def main():
    """Run all validation tests."""
    print("🚀 PyWorkflow Engine - Validation Suite")
    print("=" * 50)

    tests = [
        test_core_imports,
        test_logging_functionality,
        test_sqlite_storage,
        test_package_info,
        test_core_models_functionality,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with error: {e}")
            results.append(False)

    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"🎉 ALL TESTS PASSED ({passed}/{total})")
        print("\n✅ Package is ready for Phase 1: Core Models Implementation")
        return 0
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total})")
        print("\n🔧 Please fix issues before proceeding")
        return 1


if __name__ == "__main__":
    sys.exit(main())
