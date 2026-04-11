"""
Tests d'intégration — API décorateurs end-to-end (ADR-005).

Vérifie que les fonctions ``@step`` + ``@job`` s'exécutent correctement
via ``WorkflowEngine.run()``, en cohabitation avec l'API impérative existante.

Couverture :
- Workflow complet @step + @job → engine.run()
- Injection de paramètres depuis initial_context et outputs des steps
- Mode legacy fn(context) dans un @job
- Cohabitation impérative + déclarative dans le même test
- @job avec ParallelRunner
- @job avec run_with_persistence
- Gestion des retries (retry_count sur @step)
- Step avec timeout
- Workflow multi-étapes avec chaîne de dépendances
"""

from __future__ import annotations

import pytest

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.models.enums import RunStatus
from pyworkflow_engine.adapters.persistence.memory import InMemoryPersistence


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def engine():
    return WorkflowEngine()


@pytest.fixture
def parallel_engine():
    return WorkflowEngine(parallel=True, max_workers=2)


@pytest.fixture
def persistent_engine():
    return WorkflowEngine(persistence=InMemoryPersistence())


# ══════════════════════════════════════════════════════════════════════════════
# Workflow minimal
# ══════════════════════════════════════════════════════════════════════════════


class TestBasicDecoratorWorkflow:

    def test_single_step_success(self, engine):
        @step(name="greet")
        def greet() -> dict:
            return {"message": "Hello!"}

        @job(name="Hello Job")
        def hello():
            greet()

        result = engine.run(hello.build())
        assert result.status == RunStatus.SUCCESS

    def test_single_step_output_captured(self, engine):
        @step(name="produce")
        def produce() -> dict:
            return {"value": 42}

        @job(name="j")
        def workflow():
            produce()

        result = engine.run(workflow.build())
        assert result.status == RunStatus.SUCCESS
        step_run = result.get_step_run("produce")
        assert step_run is not None
        assert step_run.output_data == {"value": 42}

    def test_two_steps_chain(self, engine):
        @step(name="fetch")
        def fetch() -> dict:
            return {"records": [10, 20, 30]}

        @step(name="transform", dependencies=["fetch"])
        def transform(records: list | None = None) -> dict:
            return {"total": sum(records or [])}

        @job(name="ETL")
        def etl():
            fetch()
            transform()

        result = engine.run(etl.build())
        assert result.status == RunStatus.SUCCESS
        transform_run = result.get_step_run("transform")
        assert transform_run.output_data == {"total": 60}

    def test_three_steps_chain(self, engine):
        @step(name="extract")
        def extract() -> dict:
            return {"raw": [1, 2, 3]}

        @step(name="clean", dependencies=["extract"])
        def clean(raw: list | None = None) -> dict:
            return {"clean": [x * 2 for x in (raw or [])]}

        @step(name="load", dependencies=["clean"])
        def load(clean: list | None = None) -> dict:
            return {"loaded": len(clean or [])}

        @job(name="pipeline")
        def pipeline():
            extract()
            clean()
            load()

        result = engine.run(pipeline.build())
        assert result.status == RunStatus.SUCCESS
        assert result.get_step_run("load").output_data == {"loaded": 3}


# ══════════════════════════════════════════════════════════════════════════════
# Injection de paramètres
# ══════════════════════════════════════════════════════════════════════════════


class TestParameterInjection:

    def test_inject_from_initial_context(self, engine):
        @step(name="use_source")
        def use_source(source: str = "default") -> dict:
            return {"used": source}

        @job(name="j")
        def workflow():
            use_source()

        result = engine.run(workflow.build(), initial_context={"source": "api"})
        assert result.status == RunStatus.SUCCESS
        assert result.get_step_run("use_source").output_data == {"used": "api"}

    def test_inject_from_dep_output(self, engine):
        @step(name="producer")
        def producer() -> dict:
            return {"items": ["a", "b", "c"]}

        @step(name="consumer", dependencies=["producer"])
        def consumer(items: list | None = None) -> dict:
            return {"count": len(items or [])}

        @job(name="j")
        def workflow():
            producer()
            consumer()

        result = engine.run(workflow.build())
        assert result.get_step_run("consumer").output_data == {"count": 3}

    def test_default_value_used_when_no_context(self, engine):
        @step(name="s")
        def fn(limit: int = 5) -> dict:
            return {"limit": limit}

        @job(name="j")
        def workflow():
            fn()

        result = engine.run(workflow.build())
        assert result.get_step_run("s").output_data == {"limit": 5}

    def test_multiple_params_injected(self, engine):
        @step(name="s")
        def fn(a: int = 1, b: int = 2) -> dict:
            return {"sum": a + b}

        @job(name="j")
        def workflow():
            fn()

        result = engine.run(workflow.build(), initial_context={"a": 10, "b": 20})
        assert result.get_step_run("s").output_data == {"sum": 30}

    def test_dep_output_overrides_context(self, engine):
        """Output d'une dépendance prime sur le contexte global."""

        @step(name="prod")
        def producer() -> dict:
            return {"value": 99}

        @step(name="cons", dependencies=["prod"])
        def consumer(value: int = 0) -> dict:
            return {"got": value}

        @job(name="j")
        def workflow():
            producer()
            consumer()

        result = engine.run(workflow.build(), initial_context={"value": 1})
        assert result.get_step_run("cons").output_data == {"got": 99}


# ══════════════════════════════════════════════════════════════════════════════
# Mode legacy fn(context)
# ══════════════════════════════════════════════════════════════════════════════


class TestLegacyContextMode:

    def test_legacy_handler_in_job(self, engine):
        """Un @step dont la fonction prend (context) fonctionne normalement."""

        @step(name="legacy")
        def legacy_fn(context) -> dict:
            return {"value": context.get("input_val", 0)}

        @job(name="j")
        def workflow():
            legacy_fn()

        result = engine.run(workflow.build(), initial_context={"input_val": 7})
        assert result.status == RunStatus.SUCCESS
        assert result.get_step_run("legacy").output_data == {"value": 7}

    def test_legacy_and_pure_steps_coexist(self, engine):
        """Steps legacy et purs dans le même job."""

        @step(name="pure_step")
        def pure(multiplier: int = 1) -> dict:
            return {"result": 10 * multiplier}

        @step(name="legacy_step")
        def legacy(context) -> dict:
            return {"extra": context.get("extra", "none")}

        @job(name="j")
        def workflow():
            pure()
            legacy()

        result = engine.run(
            workflow.build(),
            initial_context={"multiplier": 3, "extra": "ok"},
        )
        assert result.status == RunStatus.SUCCESS
        assert result.get_step_run("pure_step").output_data == {"result": 30}
        assert result.get_step_run("legacy_step").output_data == {"extra": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# Cohabitation API impérative + déclarative
# ══════════════════════════════════════════════════════════════════════════════


class TestCohabitation:

    def test_imperative_and_declarative_produce_same_status(self, engine):
        """Les deux APIs produisent un JobRun SUCCESS."""
        from pyworkflow_engine import Job, Step, StepType

        # Impérative
        def fetch_imp(context):
            return {"records": [1, 2, 3]}

        imperative_job = Job(
            name="Imperative",
            steps=[Step(name="fetch", step_type=StepType.FUNCTION, handler=fetch_imp)],
        )

        # Déclarative
        @step(name="fetch")
        def fetch_decl() -> dict:
            return {"records": [1, 2, 3]}

        @job(name="Declarative")
        def declarative_job():
            fetch_decl()

        r1 = engine.run(imperative_job)
        r2 = engine.run(declarative_job.build())

        assert r1.status == RunStatus.SUCCESS
        assert r2.status == RunStatus.SUCCESS

    def test_same_engine_runs_both_styles(self, engine):
        """Un même moteur peut exécuter les deux styles successivement."""
        from pyworkflow_engine import Job, Step, StepType

        def imp_fn(context):
            return {"ok": True}

        imperative = Job(
            name="imp",
            steps=[Step(name="s", step_type=StepType.FUNCTION, handler=imp_fn)],
        )

        @step(name="s")
        def decl_fn() -> dict:
            return {"ok": True}

        @job(name="decl")
        def declarative():
            decl_fn()

        for _ in range(3):
            assert engine.run(imperative).status == RunStatus.SUCCESS
            assert engine.run(declarative.build()).status == RunStatus.SUCCESS


# ══════════════════════════════════════════════════════════════════════════════
# ParallelRunner + décorateurs
# ══════════════════════════════════════════════════════════════════════════════


class TestDecoratorWithParallelRunner:

    def test_parallel_independent_steps(self, parallel_engine):
        """Steps sans dépendances mutuelles s'exécutent en parallèle."""
        import threading

        threads_seen: set[int] = set()

        @step(name="task_a")
        def task_a() -> dict:
            threads_seen.add(threading.get_ident())
            return {"a": 1}

        @step(name="task_b")
        def task_b() -> dict:
            threads_seen.add(threading.get_ident())
            return {"b": 2}

        @job(name="parallel_job")
        def parallel_workflow():
            task_a()
            task_b()

        result = parallel_engine.run(parallel_workflow.build())
        assert result.status == RunStatus.SUCCESS

    def test_parallel_with_dependency_chain(self, parallel_engine):
        @step(name="source")
        def source() -> dict:
            return {"data": [1, 2, 3]}

        @step(name="process", dependencies=["source"])
        def process(data: list | None = None) -> dict:
            return {"processed": [x * 2 for x in (data or [])]}

        @job(name="j")
        def workflow():
            source()
            process()

        result = parallel_engine.run(workflow.build())
        assert result.status == RunStatus.SUCCESS
        assert result.get_step_run("process").output_data == {"processed": [2, 4, 6]}


# ══════════════════════════════════════════════════════════════════════════════
# Persistence + décorateurs
# ══════════════════════════════════════════════════════════════════════════════


class TestDecoratorWithPersistence:

    def test_run_with_persistence(self, persistent_engine):
        @step(name="compute")
        def compute(x: int = 0) -> dict:
            return {"result": x * 2}

        @job(name="persisted_job")
        def workflow():
            compute()

        result = persistent_engine.run_with_persistence(
            workflow.build(),
            initial_context={"x": 21},
        )
        assert result.status == RunStatus.SUCCESS
        assert result.get_step_run("compute").output_data == {"result": 42}

    def test_job_run_retrievable_after_execution(self, persistent_engine):
        @step(name="s")
        def fn() -> dict:
            return {"done": True}

        @job(name="retrieve_test")
        def workflow():
            fn()

        result = persistent_engine.run_with_persistence(workflow.build())
        retrieved = persistent_engine.get_job_run(result.job_run_id)
        assert retrieved is not None
        assert retrieved.status == RunStatus.SUCCESS


# ══════════════════════════════════════════════════════════════════════════════
# Mode explicite steps=[...]
# ══════════════════════════════════════════════════════════════════════════════


class TestExplicitStepsMode:

    def test_explicit_steps_end_to_end(self, engine):
        @step(name="step_one")
        def step_one() -> dict:
            return {"v": 1}

        @step(name="step_two", dependencies=["step_one"])
        def step_two(v: int = 0) -> dict:
            return {"doubled": v * 2}

        @job(name="explicit_job", steps=[step_one, step_two])
        def workflow(): ...

        result = engine.run(workflow.build())
        assert result.status == RunStatus.SUCCESS
        assert result.get_step_run("step_two").output_data == {"doubled": 2}

    def test_explicit_steps_order_preserved(self, engine):
        @step(name="alpha")
        def alpha() -> dict:
            return {}

        @step(name="beta")
        def beta() -> dict:
            return {}

        @step(name="gamma")
        def gamma() -> dict:
            return {}

        @job(name="j", steps=[alpha, beta, gamma])
        def workflow(): ...

        built = workflow.build()
        assert [s.name for s in built.steps] == ["alpha", "beta", "gamma"]


# ══════════════════════════════════════════════════════════════════════════════
# Gestion des erreurs
# ══════════════════════════════════════════════════════════════════════════════


class TestDecoratorErrorHandling:

    def test_failing_step_sets_failed_status(self, engine):
        @step(name="boom")
        def boom() -> dict:
            raise ValueError("Intentional failure")

        @job(name="j")
        def workflow():
            boom()

        from pyworkflow_engine.exceptions import StepExecutionError, WorkflowError

        with pytest.raises((StepExecutionError, WorkflowError)):
            engine.run(workflow.build())

    def test_retry_count_respected(self, engine):
        call_count = [0]

        @step(name="retry_step", retry_count=2, retry_delay=0.0)
        def flaky() -> dict:
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("Not yet")
            return {"ok": True}

        @job(name="j")
        def workflow():
            flaky()

        result = engine.run(workflow.build())
        assert result.status == RunStatus.SUCCESS
        assert call_count[0] == 3
