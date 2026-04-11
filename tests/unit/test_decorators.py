"""
Tests unitaires — module ``decorators/`` (ADR-005).

Couverture :
- ``@step`` : métadonnées, signature préservée, appel direct, sans parenthèses
- ``StepSpec`` : valeurs par défaut, frozen (immutable)
- ``@job`` / ``JobBuilder.build()`` : construction Job, modes implicite et explicite
- Context adapter : injection deps, injection contexte global, defaults, mode legacy
- Edge cases : step sans dépendances, dépendances multiples, paramètre manquant
"""

from __future__ import annotations

import inspect
from datetime import timedelta

import pytest

from pyworkflow_engine.decorators import JobBuilder, StepSpec, job, step
from pyworkflow_engine.decorators.job_decorator import _make_context_adapter
from pyworkflow_engine.models.enums import StepType
from pyworkflow_engine.models.job import Job
from pyworkflow_engine.models.step import Step


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════


class FakeContext:
    """Stub minimal de WorkflowContext pour les tests du context-adapter."""

    def __init__(
        self,
        data: dict | None = None,
        step_outputs: dict | None = None,
    ) -> None:
        self._data = data or {}
        self._step_outputs = step_outputs or {}

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def get_step_output(self, step_name: str, default=None):
        return self._step_outputs.get(step_name, default)


# ══════════════════════════════════════════════════════════════════════════════
# @step — décorateur de base
# ══════════════════════════════════════════════════════════════════════════════


class TestStepDecorator:

    def test_attaches_step_spec(self):
        @step(name="my_step")
        def fn(): ...

        assert hasattr(fn, "__step_spec__")
        assert isinstance(fn.__step_spec__, StepSpec)

    def test_name_explicit(self):
        @step(name="custom_name")
        def fn(): ...

        assert fn.__step_spec__.name == "custom_name"

    def test_name_defaults_to_function_name(self):
        @step(name="fetch")
        def fetch_data(): ...

        assert fetch_data.__step_spec__.name == "fetch"

    def test_name_no_args_defaults_to_function_name(self):
        """@step sans parenthèses — nom = nom de la fonction."""

        @step
        def process_data(): ...

        assert process_data.__step_spec__.name == "process_data"

    def test_preserves_function_name(self):
        @step(name="s")
        def my_function(): ...

        assert my_function.__name__ == "my_function"

    def test_preserves_docstring(self):
        @step(name="s")
        def my_function():
            """Docstring originale."""

        assert my_function.__doc__ == "Docstring originale."

    def test_preserves_signature(self):
        @step(name="s")
        def my_function(a: int, b: str = "x") -> dict: ...

        sig = inspect.signature(my_function)
        assert list(sig.parameters.keys()) == ["a", "b"]

    def test_callable_directly(self):
        @step(name="s")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_attaches_wrapped_fn(self):
        def original(): ...

        decorated = step(name="s")(original)
        assert decorated.__wrapped_fn__ is original

    def test_default_step_type_is_function(self):
        @step(name="s")
        def fn(): ...

        assert fn.__step_spec__.step_type == StepType.FUNCTION

    def test_custom_step_type(self):
        @step(name="s", step_type=StepType.HUMAN_TASK)
        def fn(): ...

        assert fn.__step_spec__.step_type == StepType.HUMAN_TASK

    def test_dependencies(self):
        @step(name="s", dependencies=["a", "b"])
        def fn(): ...

        assert fn.__step_spec__.dependencies == ["a", "b"]

    def test_empty_dependencies_by_default(self):
        @step(name="s")
        def fn(): ...

        assert fn.__step_spec__.dependencies == []

    def test_retry_count(self):
        @step(name="s", retry_count=3)
        def fn(): ...

        assert fn.__step_spec__.retry_count == 3

    def test_retry_delay(self):
        @step(name="s", retry_delay=2.5)
        def fn(): ...

        assert fn.__step_spec__.retry_delay == 2.5

    def test_timeout(self):
        @step(name="s", timeout=30.0)
        def fn(): ...

        assert fn.__step_spec__.timeout == 30.0

    def test_timeout_none_by_default(self):
        @step(name="s")
        def fn(): ...

        assert fn.__step_spec__.timeout is None

    def test_tags(self):
        @step(name="s", tags={"team": "data", "env": "prod"})
        def fn(): ...

        assert fn.__step_spec__.tags == {"team": "data", "env": "prod"}

    def test_spec_is_frozen(self):
        @step(name="s")
        def fn(): ...

        with pytest.raises((TypeError, AttributeError)):
            fn.__step_spec__.name = "other"  # type: ignore[misc]

    def test_executor_type(self):
        @step(name="s", executor_type="custom_exec")
        def fn(): ...

        assert fn.__step_spec__.executor_type == "custom_exec"


# ══════════════════════════════════════════════════════════════════════════════
# @job / JobBuilder
# ══════════════════════════════════════════════════════════════════════════════


class TestJobDecorator:

    def test_returns_job_builder(self):
        @job(name="my_job")
        def my_workflow(): ...

        assert isinstance(my_workflow, JobBuilder)

    def test_job_name(self):
        @job(name="ETL Pipeline")
        def etl(): ...

        assert etl.job_name == "ETL Pipeline"

    def test_job_name_defaults_to_function_name(self):
        @job
        def my_pipeline(): ...

        # @job sans parenthèses n'est pas supporté, mais avec nom implicite si
        # on passe name=None (via decorator(fn) retourne un JobBuilder)
        @job(name=None)
        def another_pipeline(): ...

        assert another_pipeline.job_name == "another_pipeline"

    def test_version(self):
        @job(name="j", version="2.0.0")
        def fn(): ...

        assert fn.version == "2.0.0"

    def test_version_default(self):
        @job(name="j")
        def fn(): ...

        assert fn.version == "1.0.0"

    def test_description_from_decorator(self):
        @job(name="j", description="Mon workflow ETL")
        def fn(): ...

        assert fn.description == "Mon workflow ETL"

    def test_description_from_docstring(self):
        @job(name="j")
        def fn():
            """Description depuis docstring."""

        assert fn.description == "Description depuis docstring."

    def test_callable_as_original_function(self):
        """JobBuilder.__call__ exécute la fonction originale."""
        results = []

        @job(name="j")
        def fn():
            results.append("called")

        fn()
        assert results == ["called"]

    def test_repr(self):
        @job(name="My Job", version="3.0.0")
        def fn(): ...

        assert "My Job" in repr(fn)
        assert "3.0.0" in repr(fn)

    # ── build() — mode implicite ───────────────────────────────────────────

    def test_build_returns_job(self):
        @step(name="s")
        def my_step(): ...

        @job(name="j")
        def my_job():
            my_step()

        result = my_job.build()
        assert isinstance(result, Job)

    def test_build_job_name(self):
        @step(name="fetch")
        def fetch_fn(): ...

        @job(name="Pipeline Alpha")
        def workflow():
            fetch_fn()

        assert workflow.build().name == "Pipeline Alpha"

    def test_build_collects_steps(self):
        @step(name="a")
        def step_a(): ...

        @step(name="b", dependencies=["a"])
        def step_b(): ...

        @job(name="j")
        def workflow():
            step_a()
            step_b()

        built = workflow.build()
        names = [s.name for s in built.steps]
        assert "a" in names
        assert "b" in names

    def test_build_step_dependencies(self):
        @step(name="extract")
        def extract(): ...

        @step(name="load", dependencies=["extract"])
        def load(): ...

        @job(name="j")
        def workflow():
            extract()
            load()

        built = workflow.build()
        load_step = next(s for s in built.steps if s.name == "load")
        assert load_step.dependencies == ["extract"]

    def test_build_step_retry_count(self):
        @step(name="flaky", retry_count=3)
        def flaky_step(): ...

        @job(name="j")
        def workflow():
            flaky_step()

        built = workflow.build()
        assert built.steps[0].retry_count == 3

    def test_build_step_timeout_converted_to_timedelta(self):
        @step(name="slow", timeout=60.0)
        def slow_step(): ...

        @job(name="j")
        def workflow():
            slow_step()

        built = workflow.build()
        assert built.steps[0].timeout == timedelta(seconds=60.0)

    def test_build_step_no_timeout(self):
        @step(name="s")
        def fn(): ...

        @job(name="j")
        def workflow():
            fn()

        built = workflow.build()
        assert built.steps[0].timeout is None

    def test_build_step_retry_delay_converted_to_timedelta(self):
        @step(name="s", retry_delay=2.5)
        def fn(): ...

        @job(name="j")
        def workflow():
            fn()

        built = workflow.build()
        assert built.steps[0].retry_delay == timedelta(seconds=2.5)

    # ── build() — mode explicite (steps=[...]) ─────────────────────────────

    def test_build_explicit_steps(self):
        @step(name="x")
        def step_x(): ...

        @step(name="y", dependencies=["x"])
        def step_y(): ...

        @job(name="j", steps=[step_x, step_y])
        def workflow(): ...

        built = workflow.build()
        assert [s.name for s in built.steps] == ["x", "y"]

    def test_build_explicit_steps_raises_if_not_decorated(self):
        def not_a_step(): ...

        @job(name="j", steps=[not_a_step])
        def workflow(): ...

        with pytest.raises(ValueError, match="@step"):
            workflow.build()

    def test_build_explicit_steps_preserves_dependencies(self):
        @step(name="p")
        def parent(): ...

        @step(name="c", dependencies=["p"])
        def child(): ...

        @job(name="j", steps=[parent, child])
        def workflow(): ...

        built = workflow.build()
        child_step = next(s for s in built.steps if s.name == "c")
        assert child_step.dependencies == ["p"]

    def test_build_tags(self):
        @step(name="s")
        def fn(): ...

        @job(name="j", tags={"owner": "team-data"})
        def workflow():
            fn()

        built = workflow.build()
        assert built.tags == {"owner": "team-data"}


# ══════════════════════════════════════════════════════════════════════════════
# Context adapter — injection de paramètres
# ══════════════════════════════════════════════════════════════════════════════


class TestContextAdapter:

    # ── Mode legacy ────────────────────────────────────────────────────────

    def test_legacy_fn_context_passthrough(self):
        """fn(context) → handler renvoyé tel quel."""

        def legacy(context):
            return context.get("value")

        spec = StepSpec(name="s")
        adapter = _make_context_adapter(legacy, spec)
        # Mode legacy : la fonction est renvoyée telle quelle
        assert adapter is legacy

    # ── Injection depuis le contexte global ────────────────────────────────

    def test_inject_from_global_context(self):
        spec = StepSpec(name="s")

        def fn(source: str) -> dict:
            return {"source": source}

        adapter = _make_context_adapter(fn, spec)
        ctx = FakeContext(data={"source": "db"})
        result = adapter(ctx)
        assert result == {"source": "db"}

    # ── Injection depuis les outputs des dépendances ───────────────────────

    def test_inject_from_dep_output(self):
        spec = StepSpec(name="transform", dependencies=["fetch"])

        def fn(records: list) -> dict:
            return {"count": len(records)}

        adapter = _make_context_adapter(fn, spec)
        ctx = FakeContext(step_outputs={"fetch": {"records": [1, 2, 3]}})
        result = adapter(ctx)
        assert result == {"count": 3}

    def test_dep_output_priority_over_context(self):
        """Le dict de sortie d'une dépendance prime sur le contexte global."""
        spec = StepSpec(name="t", dependencies=["prev"])

        def fn(value: int) -> dict:
            return {"v": value}

        adapter = _make_context_adapter(fn, spec)
        ctx = FakeContext(
            data={"value": 1},
            step_outputs={"prev": {"value": 99}},
        )
        result = adapter(ctx)
        assert result["v"] == 99  # dep output gagne

    def test_inject_multiple_deps(self):
        """Plusieurs dépendances — le premier qui fournit la clé gagne."""
        spec = StepSpec(name="t", dependencies=["a", "b"])

        def fn(x: int) -> int:
            return x * 2

        adapter = _make_context_adapter(fn, spec)
        ctx = FakeContext(
            step_outputs={"a": {}, "b": {"x": 5}},
        )
        result = adapter(ctx)
        assert result == 10

    # ── Valeur par défaut ──────────────────────────────────────────────────

    def test_uses_default_when_nothing_found(self):
        spec = StepSpec(name="s")

        def fn(limit: int = 100) -> dict:
            return {"limit": limit}

        adapter = _make_context_adapter(fn, spec)
        ctx = FakeContext()
        result = adapter(ctx)
        assert result == {"limit": 100}

    def test_none_when_no_source_and_no_default(self):
        spec = StepSpec(name="s")

        def fn(required_param) -> dict:
            return {"v": required_param}

        adapter = _make_context_adapter(fn, spec)
        ctx = FakeContext()
        result = adapter(ctx)
        assert result == {"v": None}

    # ── Preservation du nom ────────────────────────────────────────────────

    def test_adapter_preserves_function_name(self):
        spec = StepSpec(name="s")

        def my_handler(x: int) -> int:
            return x

        adapter = _make_context_adapter(my_handler, spec)
        assert adapter.__name__ == "my_handler"


# ══════════════════════════════════════════════════════════════════════════════
# Import depuis le package principal
# ══════════════════════════════════════════════════════════════════════════════


class TestPublicImports:

    def test_import_step_from_decorators(self):
        from pyworkflow_engine.decorators import step as s

        assert callable(s)

    def test_import_job_from_decorators(self):
        from pyworkflow_engine.decorators import job as j

        assert callable(j)

    def test_import_step_from_package(self):
        from pyworkflow_engine import step as s

        assert callable(s)

    def test_import_job_from_package(self):
        from pyworkflow_engine import job as j

        assert callable(j)

    def test_import_stepspec_from_decorators(self):
        from pyworkflow_engine.decorators import StepSpec as SS

        assert SS is StepSpec

    def test_import_jobbuilder_from_decorators(self):
        from pyworkflow_engine.decorators import JobBuilder as JB

        assert JB is JobBuilder
