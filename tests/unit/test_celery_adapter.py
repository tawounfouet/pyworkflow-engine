"""Tests unitaires pour l'adapter Celery (ADR-007).

Tous les tests mockent l'infrastructure Celery (broker, workers) pour
fonctionner sans Redis ni worker réel. Les tests d'intégration avec
une infrastructure réelle seront dans tests/integration/.

Stratégie de mock :
    - ``celery`` est importé et mocké via unittest.mock
    - ``CeleryExecutor._get_app()`` est mocké pour retourner un MagicMock
    - ``app.send_task()`` est mocké pour retourner un AsyncResult simulé
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from pyworkflow_engine import Job, JobRun, RunStatus, Step, StepType
from pyworkflow_engine.engine.context import WorkflowContext
from pyworkflow_engine.exceptions import StepExecutionError


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_context(job_name: str = "test_job") -> WorkflowContext:
    job_run = JobRun(job_name=job_name)
    return WorkflowContext(job_run)


# Fonctions top-level importables (nécessaires pour la sérialisation)
def sample_step_handler() -> dict:
    return {"result": "ok"}


def sample_step_with_context(ctx: dict) -> dict:
    return {"result": "with_context", "job": ctx.get("job_name", "")}


# ── CeleryConfig ─────────────────────────────────────────────────────────────


class TestCeleryConfig:
    """Tests de la dataclass CeleryConfig."""

    def test_defaults(self):
        from pyworkflow_engine.adapters.celery.config import CeleryConfig

        config = CeleryConfig()
        assert config.broker_url == "redis://localhost:6379/0"
        assert config.result_backend is None
        assert config.task_serializer == "json"
        assert config.task_default_queue == "pyworkflow"
        assert config.enable_utc is True
        assert config.task_track_started is True

    def test_custom_values(self):
        from pyworkflow_engine.adapters.celery.config import CeleryConfig

        config = CeleryConfig(
            broker_url="amqp://guest:guest@localhost:5672//",
            result_backend="redis://localhost:6379/1",
            task_timeout=120.0,
            task_default_queue="high_priority",
            worker_concurrency=4,
        )
        assert config.broker_url == "amqp://guest:guest@localhost:5672//"
        assert config.result_backend == "redis://localhost:6379/1"
        assert config.task_timeout == 120.0
        assert config.task_default_queue == "high_priority"
        assert config.worker_concurrency == 4

    def test_frozen_immutable(self):
        from pyworkflow_engine.adapters.celery.config import CeleryConfig

        config = CeleryConfig()
        with pytest.raises(Exception):  # FrozenInstanceError (dataclasses)
            config.broker_url = "other"  # type: ignore[misc]

    def test_accept_content_is_tuple(self):
        from pyworkflow_engine.adapters.celery.config import CeleryConfig

        config = CeleryConfig()
        assert isinstance(config.accept_content, tuple)
        assert "json" in config.accept_content


# ── get_celery_app factory ───────────────────────────────────────────────────


class TestGetCeleryApp:
    """Tests de la factory get_celery_app."""

    def test_returns_celery_instance_when_installed(self):
        """Vérifie que get_celery_app crée une instance Celery configurée."""
        celery_mock = MagicMock()
        app_mock = MagicMock()
        celery_mock.return_value = app_mock

        with patch.dict("sys.modules", {"celery": MagicMock(Celery=celery_mock)}):
            from importlib import reload

            import pyworkflow_engine.adapters.celery.app as app_module

            reload(app_module)
            result = app_module.get_celery_app(
                broker_url="redis://localhost:6379/0",
                result_backend="redis://localhost:6379/1",
            )
            assert result is app_mock

    def test_raises_import_error_when_celery_not_installed(self):
        """Lève ImportError si celery n'est pas installé."""
        with patch.dict("sys.modules", {"celery": None}):
            from importlib import reload

            import pyworkflow_engine.adapters.celery.app as app_module

            reload(app_module)
            with pytest.raises(
                ImportError, match="pip install pyworkflow-engine\\[celery\\]"
            ):
                app_module.get_celery_app()


# ── Tasks — _resolve_handler ─────────────────────────────────────────────────


class TestResolveHandler:
    """Tests du resolver de handlers dans tasks.py."""

    def test_resolves_top_level_function(self):
        from pyworkflow_engine.adapters.celery.tasks import _resolve_handler

        handler = _resolve_handler("tests.unit.test_celery_adapter.sample_step_handler")
        # Use qualified name comparison instead of identity (`is`) because
        # pytest may import this module under a different sys.modules key
        # (e.g. "unit.test_celery_adapter" vs "tests.unit.test_celery_adapter"),
        # resulting in distinct function objects.
        assert handler.__qualname__ == sample_step_handler.__qualname__
        assert handler.__module__ == "tests.unit.test_celery_adapter"

    def test_raises_on_missing_dot(self):
        from pyworkflow_engine.adapters.celery.tasks import _resolve_handler

        with pytest.raises(ValueError, match="invalide"):
            _resolve_handler("no_module_path")

    def test_raises_on_missing_module(self):
        from pyworkflow_engine.adapters.celery.tasks import _resolve_handler

        with pytest.raises(ImportError):
            _resolve_handler("nonexistent.module.func")

    def test_raises_on_missing_attr(self):
        from pyworkflow_engine.adapters.celery.tasks import _resolve_handler

        with pytest.raises(AttributeError):
            _resolve_handler("tests.unit.test_celery_adapter.nonexistent_func")


# ── Tasks — execute_step_task ─────────────────────────────────────────────────


class TestExecuteStepTask:
    """Tests de la task execute_step_task."""

    def test_executes_no_arg_handler(self):
        from pyworkflow_engine.adapters.celery.tasks import execute_step_task

        result = execute_step_task(
            "tests.unit.test_celery_adapter.sample_step_handler",
            {},
            step_name="test",
        )
        assert result == {"result": "ok"}

    def test_executes_handler_with_context(self):
        from pyworkflow_engine.adapters.celery.tasks import execute_step_task

        context_dict = {"job_name": "my_job", "data": {}, "step_outputs": {}}
        result = execute_step_task(
            "tests.unit.test_celery_adapter.sample_step_with_context",
            context_dict,
            step_name="ctx_test",
        )
        assert result["result"] == "with_context"
        assert result["job"] == "my_job"

    def test_wraps_non_dict_result(self):
        from pyworkflow_engine.adapters.celery.tasks import execute_step_task

        # Patcher un handler qui retourne une string
        with patch(
            "tests.unit.test_celery_adapter.sample_step_handler",
            return_value="plain_string",
        ):
            result = execute_step_task(
                "tests.unit.test_celery_adapter.sample_step_handler",
                {},
            )
            assert result == {"result": "plain_string"}

    def test_none_result_returns_empty_dict(self):
        from pyworkflow_engine.adapters.celery.tasks import execute_step_task

        with patch(
            "tests.unit.test_celery_adapter.sample_step_handler",
            return_value=None,
        ):
            result = execute_step_task(
                "tests.unit.test_celery_adapter.sample_step_handler",
                {},
            )
            assert result == {}

    def test_propagates_handler_exception(self):
        from pyworkflow_engine.adapters.celery.tasks import execute_step_task

        with patch(
            "tests.unit.test_celery_adapter.sample_step_handler",
            side_effect=RuntimeError("handler boom"),
        ):
            with pytest.raises(RuntimeError, match="handler boom"):
                execute_step_task(
                    "tests.unit.test_celery_adapter.sample_step_handler",
                    {},
                )


# ── CeleryExecutor — sérialisation ───────────────────────────────────────────


class TestCeleryExecutorSerialization:
    """Tests de la sérialisation des handlers dans CeleryExecutor."""

    def _make_executor(self):
        from pyworkflow_engine.adapters.celery.config import CeleryConfig
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        return CeleryExecutor(
            config=CeleryConfig(
                broker_url="redis://localhost:6379/0",
                result_backend="redis://localhost:6379/1",
            )
        )

    def test_serialize_top_level_function(self):
        executor = self._make_executor()
        ref = executor._serialize_handler(sample_step_handler)
        assert ref == "tests.unit.test_celery_adapter.sample_step_handler"

    def test_serialize_lambda_raises(self):
        from pyworkflow_engine.adapters.celery.executor import SerializationError

        executor = self._make_executor()
        with pytest.raises(SerializationError, match="lambda"):
            executor._serialize_handler(lambda: None)

    def test_serialize_closure_raises(self):
        from pyworkflow_engine.adapters.celery.executor import SerializationError

        def outer():
            def inner():
                return {}

            return inner

        executor = self._make_executor()
        with pytest.raises(SerializationError, match="closure"):
            executor._serialize_handler(outer())

    def test_serialize_function_without_module_raises(self):
        from pyworkflow_engine.adapters.celery.executor import SerializationError

        broken_fn = Mock()
        broken_fn.__module__ = None
        broken_fn.__qualname__ = "broken"
        executor = self._make_executor()
        with pytest.raises(SerializationError):
            executor._serialize_handler(broken_fn)


# ── CeleryExecutor — execute() ───────────────────────────────────────────────


class TestCeleryExecutorExecute:
    """Tests de CeleryExecutor.execute() avec mock Celery."""

    def _make_executor_and_mock_app(self):
        """Retourne (executor, mock_app) avec l'app Celery mockée."""
        from pyworkflow_engine.adapters.celery.config import CeleryConfig
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        executor = CeleryExecutor(
            config=CeleryConfig(
                broker_url="redis://localhost:6379/0",
                result_backend="redis://localhost:6379/1",
                task_timeout=10.0,
            )
        )

        mock_app = MagicMock()
        mock_async_result = MagicMock()
        mock_async_result.get.return_value = {"dispatched": True}
        mock_app.send_task.return_value = mock_async_result

        executor._celery_app = mock_app
        executor._celery_task = MagicMock()
        return executor, mock_app, mock_async_result

    def _make_step(self, handler=None, timeout=None):
        return Step(
            name="test_step",
            step_type=StepType.FUNCTION,
            handler=handler or sample_step_handler,
            timeout=timeout,
        )

    def test_dispatches_task_and_returns_result(self):
        executor, mock_app, mock_result = self._make_executor_and_mock_app()
        step = self._make_step()
        ctx = make_context()

        result = executor.execute(step, ctx)

        assert result == {"dispatched": True}
        mock_app.send_task.assert_called_once()
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs[0][0] == "pyworkflow_engine.execute_step"

    def test_passes_handler_ref_and_context_to_task(self):
        executor, mock_app, _ = self._make_executor_and_mock_app()
        step = self._make_step()
        ctx = make_context("my_workflow")

        executor.execute(step, ctx)

        args = mock_app.send_task.call_args[1]["args"]
        handler_ref, context_dict, step_name = args
        assert handler_ref == "tests.unit.test_celery_adapter.sample_step_handler"
        assert context_dict["job_name"] == "my_workflow"
        assert step_name == "test_step"

    def test_uses_step_timeout_over_config_timeout(self):
        executor, mock_app, mock_result = self._make_executor_and_mock_app()
        step = self._make_step(timeout=timedelta(seconds=42))
        ctx = make_context()

        executor.execute(step, ctx)

        mock_result.get.assert_called_once_with(timeout=42.0, propagate=True)

    def test_raises_when_no_result_backend(self):
        from pyworkflow_engine.adapters.celery.config import CeleryConfig
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        executor = CeleryExecutor(
            config=CeleryConfig(
                broker_url="redis://localhost:6379/0",
                result_backend=None,  # pas de backend
            )
        )
        step = self._make_step()
        ctx = make_context()

        with pytest.raises(StepExecutionError, match="result_backend"):
            executor.execute(step, ctx)

    def test_raises_when_no_handler(self):
        executor, _, _ = self._make_executor_and_mock_app()
        step = Step(name="no_handler", step_type=StepType.FUNCTION, handler=None)
        ctx = make_context()

        with pytest.raises(StepExecutionError, match="no callable"):
            executor.execute(step, ctx)

    def test_raises_on_lambda_handler(self):
        from pyworkflow_engine.adapters.celery.executor import SerializationError

        executor, _, _ = self._make_executor_and_mock_app()
        step = self._make_step(handler=lambda: {"x": 1})
        ctx = make_context()

        with pytest.raises(SerializationError, match="lambda"):
            executor.execute(step, ctx)

    def test_raises_step_execution_error_on_send_task_failure(self):
        executor, mock_app, _ = self._make_executor_and_mock_app()
        mock_app.send_task.side_effect = ConnectionError("broker unreachable")
        step = self._make_step()
        ctx = make_context()

        with pytest.raises(StepExecutionError, match="Impossible d'envoyer"):
            executor.execute(step, ctx)

    def test_raises_step_execution_error_on_timeout(self):
        executor, mock_app, mock_result = self._make_executor_and_mock_app()

        class FakeTimeoutError(Exception):
            pass

        mock_result.get.side_effect = FakeTimeoutError("TimeoutError: timed out")
        step = self._make_step()
        ctx = make_context()

        with pytest.raises(StepExecutionError, match="timed out"):
            executor.execute(step, ctx)

    def test_raises_step_execution_error_on_task_failure(self):
        executor, mock_app, mock_result = self._make_executor_and_mock_app()
        mock_result.get.side_effect = RuntimeError("worker crashed")
        step = self._make_step()
        ctx = make_context()

        with pytest.raises(StepExecutionError, match="Celery execution failed"):
            executor.execute(step, ctx)


# ── CeleryExecutor — configuration et repr ──────────────────────────────────


class TestCeleryExecutorConfig:
    """Tests de la configuration et du cycle de vie du CeleryExecutor."""

    def test_init_from_kwargs(self):
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        executor = CeleryExecutor(
            broker_url="redis://host:6379/0",
            result_backend="redis://host:6379/1",
            task_timeout=60.0,
        )
        assert executor.config.broker_url == "redis://host:6379/0"
        assert executor.config.result_backend == "redis://host:6379/1"
        assert executor.config.task_timeout == 60.0

    def test_init_from_config_object(self):
        from pyworkflow_engine.adapters.celery.config import CeleryConfig
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        config = CeleryConfig(broker_url="amqp://localhost//", task_timeout=30.0)
        executor = CeleryExecutor(config=config)
        assert executor.config is config

    def test_init_raises_on_invalid_config_type(self):
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        with pytest.raises(TypeError, match="CeleryConfig"):
            CeleryExecutor(config={"broker_url": "redis://localhost"})  # type: ignore[arg-type]

    def test_repr(self):
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        executor = CeleryExecutor(
            broker_url="redis://localhost:6379/0",
            result_backend="redis://localhost:6379/1",
        )
        r = repr(executor)
        assert "CeleryExecutor" in r
        assert "redis://localhost:6379/0" in r

    def test_shutdown_clears_app(self):
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        executor = CeleryExecutor()
        executor._celery_app = MagicMock()
        executor._celery_task = MagicMock()

        executor.shutdown()

        assert executor._celery_app is None
        assert executor._celery_task is None

    def test_shutdown_is_idempotent(self):
        """shutdown() sur un executor non initialisé ne lève pas d'erreur."""
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor

        executor = CeleryExecutor()
        executor.shutdown()  # Pas d'erreur attendue
        executor.shutdown()  # Deuxième appel : OK


# ── Routing ExecutorType.CELERY dans WorkflowRunner ──────────────────────────


class TestCeleryExecutorTypeRouting:
    """Tests du routing ExecutorType.CELERY dans WorkflowRunner."""

    def test_celery_type_raises_without_celery_installed(self):
        """Sans Celery installé, _resolve_celery_executor lève StepExecutionError."""
        from pyworkflow_engine.engine.runner import WorkflowRunner
        from pyworkflow_engine.models.enums import ExecutorType

        runner = WorkflowRunner()
        step = Step(
            name="celery_step",
            step_type=StepType.FUNCTION,
            handler=sample_step_handler,
            executor_type=ExecutorType.CELERY,
        )

        with patch(
            "pyworkflow_engine.engine.runner.WorkflowRunner._resolve_celery_executor",
            side_effect=StepExecutionError(
                "Celery adapter not installed",
                step_name="celery_step",
            ),
        ):
            with pytest.raises(
                StepExecutionError, match="Celery adapter not installed"
            ):
                runner._resolve_executor(step)

    def test_celery_type_returns_celery_executor_when_installed(self):
        """Avec Celery installé, _resolve_executor retourne un CeleryExecutor."""
        from pyworkflow_engine.adapters.celery.executor import CeleryExecutor
        from pyworkflow_engine.engine.runner import WorkflowRunner
        from pyworkflow_engine.models.enums import ExecutorType

        runner = WorkflowRunner()
        step = Step(
            name="celery_step",
            step_type=StepType.FUNCTION,
            handler=sample_step_handler,
            executor_type=ExecutorType.CELERY,
        )

        mock_executor = MagicMock(spec=CeleryExecutor)
        with patch.object(
            runner, "_resolve_celery_executor", return_value=mock_executor
        ):
            result = runner._resolve_executor(step)
            assert result is mock_executor


# ── __init__.py — lazy imports ────────────────────────────────────────────────


class TestCeleryLazyImports:
    """Vérifie que CeleryExecutor/CeleryConfig sont accessibles depuis le package."""

    def test_celery_executor_importable_from_package(self):
        from pyworkflow_engine.adapters.celery import CeleryExecutor  # noqa: F401

    def test_celery_config_importable_from_package(self):
        from pyworkflow_engine.adapters.celery import CeleryConfig  # noqa: F401

    def test_celery_executor_importable_from_adapter_path(self):
        from pyworkflow_engine.adapters.celery.executor import (
            CeleryExecutor,
        )  # noqa: F401

    def test_celery_config_in_all(self):
        import pyworkflow_engine

        assert "CeleryExecutor" in pyworkflow_engine.__all__
        assert "CeleryConfig" in pyworkflow_engine.__all__
