"""
Tests unitaires — ``@pipeline`` / ``@stage`` / ``PipelineBuilder`` (ADR-014).

Couverture :
  - ``@stage`` : métadonnées, appel direct, StageSpec frozen
  - ``@pipeline`` / ``PipelineBuilder.build()`` :
      - Mode implicite (bytecode introspection)
      - Mode explicite (``stages=[...]``)
      - Résolution job_name depuis JobBuilder / Job / fonction
      - Schedule → TriggerType.SCHEDULE
      - Validation (stage non décoré, pipeline vide)
  - ``StageSpec`` : valeurs par défaut, frozen, condition, metadata
  - ``PipelineBuilder`` : repr, __call__, build
  - Intégration avec ``Pipeline`` model
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pyworkflow_engine.decorators import (
    PipelineBuilder,
    StageSpec,
    job,
    pipeline,
    stage,
    step,
)
from pyworkflow_engine.models.enums import Priority, TriggerType
from pyworkflow_engine.models.workflow.job import Job
from pyworkflow_engine.models.pipeline.pipeline import Pipeline

# ======================================================================
# Fixtures — Jobs et stages réutilisables
# ======================================================================


@step(name="fetch")
def _fetch_data(source: str = "api") -> dict:
    return {"records": [1, 2, 3]}


@step(name="transform", dependencies=["fetch"])
def _transform_data(records: list | None = None) -> dict:
    return {"out": [r * 10 for r in (records or [])]}


@step(name="clean")
def _clean_data() -> dict:
    return {"cleaned": True}


@job(name="ingestion-job")
def _ingestion_job():
    _fetch_data()
    _transform_data()


@job(name="transform-job")
def _transform_job():
    _clean_data()


# ======================================================================
# @stage decorator
# ======================================================================


class TestStageDecorator:
    """Tests du décorateur ``@stage``."""

    def test_attaches_stage_spec(self):
        @stage()
        def my_stage():
            pass

        assert hasattr(my_stage, "__stage_spec__")
        assert isinstance(my_stage.__stage_spec__, StageSpec)

    def test_preserves_function_name(self):
        @stage()
        def quality_check():
            """Doc string."""

        assert quality_check.__name__ == "quality_check"
        assert quality_check.__doc__ == "Doc string."

    def test_callable(self):
        """La fonction décorée reste appelable normalement."""

        @stage()
        def compute():
            return 42

        assert compute() == 42

    def test_job_ref(self):
        """Le job_ref est stocké dans le StageSpec."""

        @stage(job=_ingestion_job)
        def ingest():
            pass

        assert ingest.__stage_spec__.job_ref is _ingestion_job

    def test_initial_context(self):
        @stage(initial_context={"key": "value"})
        def s():
            pass

        assert s.__stage_spec__.initial_context == {"key": "value"}

    def test_context_mapping(self):
        @stage(context_mapping={"job_key": "pipeline_key"})
        def s():
            pass

        assert s.__stage_spec__.context_mapping == {"job_key": "pipeline_key"}

    def test_continue_on_failure(self):
        @stage(continue_on_failure=True)
        def s():
            pass

        assert s.__stage_spec__.continue_on_failure is True

    def test_condition(self):
        cond = lambda ctx: ctx.get("enabled", False)  # noqa: E731

        @stage(condition=cond)
        def s():
            pass

        assert s.__stage_spec__.condition is cond

    def test_enabled_default_true(self):
        @stage()
        def s():
            pass

        assert s.__stage_spec__.enabled is True

    def test_enabled_false(self):
        @stage(enabled=False)
        def s():
            pass

        assert s.__stage_spec__.enabled is False

    def test_metadata(self):
        @stage(metadata={"severity": "warning"})
        def s():
            pass

        assert s.__stage_spec__.metadata == {"severity": "warning"}

    def test_wrapped_fn_attribute(self):
        @stage()
        def s():
            pass

        assert hasattr(s, "__wrapped_fn__")

    def test_defaults(self):
        """Toutes les valeurs par défaut du StageSpec."""

        @stage()
        def s():
            pass

        spec = s.__stage_spec__
        assert spec.job_ref is None
        assert spec.initial_context == {}
        assert spec.context_mapping == {}
        assert spec.continue_on_failure is False
        assert spec.condition is None
        assert spec.enabled is True
        assert spec.metadata == {}


# ======================================================================
# StageSpec frozen
# ======================================================================


class TestStageSpec:
    """Tests du dataclass StageSpec."""

    def test_frozen(self):
        spec = StageSpec()
        with pytest.raises(FrozenInstanceError):
            spec.enabled = False  # type: ignore[misc]

    def test_equality(self):
        s1 = StageSpec(continue_on_failure=True)
        s2 = StageSpec(continue_on_failure=True)
        assert s1 == s2

    def test_condition_excluded_from_compare(self):
        """condition est exclude_from_compare=True."""
        fn1 = lambda ctx: True  # noqa: E731
        fn2 = lambda ctx: False  # noqa: E731
        s1 = StageSpec(condition=fn1)
        s2 = StageSpec(condition=fn2)
        assert s1 == s2  # conditions ignorées dans __eq__


# ======================================================================
# @pipeline — mode implicite (bytecode)
# ======================================================================


# Module-level stages for bytecode introspection
@stage(job=_ingestion_job)
def ingestion_stage():
    """Ingestion."""


@stage(job=_transform_job, continue_on_failure=True)
def transform_stage():
    """Transform."""


class TestPipelineImplicitMode:
    """Tests du mode implicite (introspection bytecode) de ``@pipeline``."""

    def test_build_basic(self):
        @pipeline(name="test-pipeline")
        def my_pipeline():
            ingestion_stage()
            transform_stage()

        p = my_pipeline.build()
        assert isinstance(p, Pipeline)
        assert p.name == "test-pipeline"
        assert p.stage_count == 2

    def test_stage_order_preserved(self):
        @pipeline(name="ordered")
        def my_pipeline():
            ingestion_stage()
            transform_stage()

        p = my_pipeline.build()
        assert p.job_names == ["ingestion-job", "transform-job"]

    def test_job_name_resolved_from_job_builder(self):
        """Le job_name est résolu depuis le JobBuilder.job_name."""

        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.stages[0].job_name == "ingestion-job"

    def test_continue_on_failure_propagated(self):
        @pipeline(name="test")
        def my_pipeline():
            transform_stage()

        p = my_pipeline.build()
        assert p.stages[0].continue_on_failure is True

    def test_job_resolved_via_build(self):
        """Le Job est résolu via JobBuilder.build()."""

        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.stages[0].job is not None
        assert isinstance(p.stages[0].job, Job)
        assert p.stages[0].job.name == "ingestion-job"

    def test_pipeline_version(self):
        @pipeline(name="test", version="2.0.0")
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.version == "2.0.0"

    def test_pipeline_description_from_docstring(self):
        @pipeline(name="test")
        def my_pipeline():
            """My pipeline description."""
            ingestion_stage()

        p = my_pipeline.build()
        assert p.description == "My pipeline description."

    def test_pipeline_description_explicit(self):
        @pipeline(name="test", description="Explicit desc")
        def my_pipeline():
            """Docstring ignored."""
            ingestion_stage()

        p = my_pipeline.build()
        assert p.description == "Explicit desc"

    def test_pipeline_schedule(self):
        @pipeline(name="test", schedule="0 1 * * 0")
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.schedule == "0 1 * * 0"
        assert TriggerType.SCHEDULE in p.triggers
        assert TriggerType.MANUAL in p.triggers

    def test_pipeline_no_schedule(self):
        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.schedule is None
        assert p.triggers == [TriggerType.MANUAL]

    def test_pipeline_owner(self):
        @pipeline(name="test", owner="data-team@co.com")
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.owner == "data-team@co.com"

    def test_pipeline_tags(self):
        @pipeline(name="test", tags=["weekly", "etl"])
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.tags == ["weekly", "etl"]

    def test_pipeline_priority(self):
        @pipeline(name="test", priority=Priority.HIGH)
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.priority == Priority.HIGH

    def test_pipeline_metadata(self):
        @pipeline(name="test", metadata={"team": "data"})
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.metadata == {"team": "data"}

    def test_pipeline_name_defaults_to_function_name(self):
        @pipeline()
        def my_etl():
            ingestion_stage()

        p = my_etl.build()
        assert p.name == "my_etl"


# ======================================================================
# @pipeline — mode explicite (stages=[...])
# ======================================================================


class TestPipelineExplicitMode:
    """Tests du mode explicite (``stages=[...]``) de ``@pipeline``."""

    def test_build_explicit(self):
        @pipeline(name="explicit", stages=[ingestion_stage, transform_stage])
        def my_pipeline():
            pass

        p = my_pipeline.build()
        assert p.stage_count == 2
        assert p.job_names == ["ingestion-job", "transform-job"]

    def test_explicit_overrides_bytecode(self):
        """En mode explicite, le bytecode est ignoré."""

        @pipeline(name="only-ingest", stages=[ingestion_stage])
        def my_pipeline():
            # Le corps référence transform_stage, mais stages=[] prend le dessus
            ingestion_stage()
            transform_stage()

        p = my_pipeline.build()
        assert p.stage_count == 1
        assert p.job_names == ["ingestion-job"]

    def test_non_decorated_function_raises(self):
        """Si une fonction dans stages=[] n'est pas décorée par @stage."""

        def not_a_stage():
            pass

        @pipeline(name="bad", stages=[not_a_stage])
        def my_pipeline():
            pass

        with pytest.raises(ValueError, match="n'est pas décorée par @stage"):
            my_pipeline.build()


# ======================================================================
# @pipeline — résolution du job_name
# ======================================================================


class TestJobNameResolution:
    """Tests de la résolution du job_name depuis différentes sources."""

    def test_from_job_builder(self):
        """JobBuilder → job_name attribute."""

        @stage(job=_ingestion_job)
        def s():
            pass

        @pipeline(name="test", stages=[s])
        def p():
            pass

        built = p.build()
        assert built.stages[0].job_name == "ingestion-job"

    def test_from_job_model(self):
        """Job model → name attribute."""
        job_model = Job(name="direct-job", steps=[])

        @stage(job=job_model)
        def s():
            pass

        @pipeline(name="test", stages=[s])
        def p():
            pass

        built = p.build()
        assert built.stages[0].job_name == "direct-job"
        assert built.stages[0].job is job_model

    def test_from_function_name(self):
        """Ni JobBuilder ni Job → nom de la fonction."""

        @stage()
        def quality_check():
            pass

        @pipeline(name="test", stages=[quality_check])
        def p():
            pass

        built = p.build()
        assert built.stages[0].job_name == "quality_check"
        assert built.stages[0].job is None


# ======================================================================
# PipelineBuilder
# ======================================================================


class TestPipelineBuilder:
    """Tests de ``PipelineBuilder``."""

    def test_is_callable(self):
        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()

        assert callable(my_pipeline)

    def test_call_returns_function_result(self):
        @pipeline(name="test")
        def my_pipeline():
            return "result"

        assert my_pipeline() == "result"

    def test_repr(self):
        @pipeline(name="etl-v2", version="2.0.0")
        def my_pipeline():
            ingestion_stage()

        assert "etl-v2" in repr(my_pipeline)
        assert "2.0.0" in repr(my_pipeline)

    def test_isinstance_pipeline_builder(self):
        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()

        assert isinstance(my_pipeline, PipelineBuilder)

    def test_pipeline_name_attribute(self):
        @pipeline(name="my-name")
        def my_pipeline():
            ingestion_stage()

        assert my_pipeline.pipeline_name == "my-name"

    def test_version_attribute(self):
        @pipeline(name="test", version="3.0.0")
        def my_pipeline():
            ingestion_stage()

        assert my_pipeline.version == "3.0.0"

    def test_description_attribute(self):
        @pipeline(name="test", description="A desc")
        def my_pipeline():
            ingestion_stage()

        assert my_pipeline.description == "A desc"

    def test_build_produces_pipeline(self):
        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()

        result = my_pipeline.build()
        assert isinstance(result, Pipeline)

    def test_build_pipeline_enabled(self):
        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()

        p = my_pipeline.build()
        assert p.enabled is True


# ======================================================================
# Closure mode — stages defined in enclosing scope
# ======================================================================


class TestPipelineClosureMode:
    """Tests du mode closure (stages définis dans un scope englobant)."""

    def test_closure_stage_detected(self):
        """Les stages définis en scope local (closure) sont détectés."""

        @stage(job=_ingestion_job)
        def local_ingest():
            pass

        @pipeline(name="closure-test")
        def my_pipeline():
            local_ingest()

        p = my_pipeline.build()
        assert p.stage_count == 1
        assert p.job_names == ["ingestion-job"]


# ======================================================================
# Integration — Pipeline model properties
# ======================================================================


class TestPipelineIntegration:
    """Vérification que le Pipeline produit est fonctionnel."""

    def test_serialization_roundtrip(self):
        @pipeline(
            name="integration-test",
            version="1.2.0",
            schedule="0 2 * * *",
            owner="team@co.com",
            tags=["integration"],
        )
        def my_pipeline():
            ingestion_stage()
            transform_stage()

        p = my_pipeline.build()
        d = p.to_dict()
        restored = Pipeline.from_dict(d)

        assert restored.name == "integration-test"
        assert restored.version == "1.2.0"
        assert restored.schedule == "0 2 * * *"
        assert restored.owner == "team@co.com"
        assert restored.tags == ["integration"]
        assert restored.stage_count == 2
        assert restored.job_names == ["ingestion-job", "transform-job"]

    def test_get_stage(self):
        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()
            transform_stage()

        p = my_pipeline.build()
        found = p.get_stage("ingestion-job")
        assert found is not None
        assert found.job_name == "ingestion-job"

    def test_get_stage_index(self):
        @pipeline(name="test")
        def my_pipeline():
            ingestion_stage()
            transform_stage()

        p = my_pipeline.build()
        assert p.get_stage_index("transform-job") == 1

    def test_context_mapping_propagated(self):
        @stage(
            job=_ingestion_job,
            context_mapping={"ingest_date": "target_date"},
        )
        def mapped_stage():
            pass

        @pipeline(name="test", stages=[mapped_stage])
        def my_pipeline():
            pass

        p = my_pipeline.build()
        assert p.stages[0].context_mapping == {"ingest_date": "target_date"}

    def test_initial_context_propagated(self):
        @stage(
            job=_ingestion_job,
            initial_context={"source": "api"},
        )
        def ctx_stage():
            pass

        @pipeline(name="test", stages=[ctx_stage])
        def my_pipeline():
            pass

        p = my_pipeline.build()
        assert p.stages[0].initial_context == {"source": "api"}


# ======================================================================
# Exports from decorators/__init__.py
# ======================================================================


class TestDecoratorExports:
    """Vérifie les exports de ``decorators/__init__.py``."""

    def test_pipeline_exported(self):
        from pyworkflow_engine.decorators import pipeline as p  # noqa: F811

        assert callable(p)

    def test_stage_exported(self):
        from pyworkflow_engine.decorators import stage as s  # noqa: F811

        assert callable(s)

    def test_pipeline_builder_exported(self):
        from pyworkflow_engine.decorators import PipelineBuilder as PB

        assert PB is not None

    def test_stage_spec_exported(self):
        from pyworkflow_engine.decorators import StageSpec as SS

        assert SS is not None
