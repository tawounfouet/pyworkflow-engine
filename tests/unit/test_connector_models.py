"""
Tests unitaires — modèles connector (ConnectorRef, ConnectorOutcome) + bridge.

Couvre :
- ConnectorRef : construction, auto-déduction type, frozen, sérialisation
- ConnectorOutcome : construction, sérialisation, repr
- Step + connector_ref : intégration design-time
- StepRun + connector_outcome : intégration runtime
- Bridge connector_step : lazy import, exécution, erreurs
"""

from __future__ import annotations

import importlib
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from pyworkflow_engine.exceptions import StepExecutionError
from pyworkflow_engine.models.workflow.connector import ConnectorOutcome, ConnectorRef
from pyworkflow_engine.models.enums import StepType
from pyworkflow_engine.models.workflow.run import StepRun
from pyworkflow_engine.models.workflow.step import Step

# ======================================================================
# ConnectorRef
# ======================================================================


class TestConnectorRef:
    """Tests pour ConnectorRef (design-time, frozen)."""

    def test_basic_construction(self):
        ref = ConnectorRef(connector_name="database.postgresql")
        assert ref.connector_name == "database.postgresql"
        assert ref.action == "execute"
        assert ref.config == {}
        assert ref.description == ""

    def test_auto_deduce_type_from_name(self):
        ref = ConnectorRef(connector_name="database.postgresql")
        assert ref.connector_type == "database"

    def test_auto_deduce_type_http(self):
        ref = ConnectorRef(connector_name="http.rest")
        assert ref.connector_type == "http"

    def test_auto_deduce_type_social(self):
        ref = ConnectorRef(connector_name="social.slack")
        assert ref.connector_type == "social"

    def test_explicit_type_overrides_deduction(self):
        ref = ConnectorRef(
            connector_name="database.postgresql",
            connector_type="custom_db",
        )
        assert ref.connector_type == "custom_db"

    def test_no_dot_in_name_no_type(self):
        ref = ConnectorRef(connector_name="postgresql")
        assert ref.connector_type == ""

    def test_frozen_immutability(self):
        ref = ConnectorRef(connector_name="database.postgresql")
        with pytest.raises(ValidationError):
            ref.connector_name = "other"  # type: ignore[misc]

    def test_full_construction(self):
        ref = ConnectorRef(
            connector_name="storage.s3",
            connector_type="storage",
            config={"params": {"bucket": "my-bucket"}},
            action="upload",
            description="Upload vers S3",
        )
        assert ref.connector_name == "storage.s3"
        assert ref.connector_type == "storage"
        assert ref.config == {"params": {"bucket": "my-bucket"}}
        assert ref.action == "upload"
        assert ref.description == "Upload vers S3"

    def test_to_dict(self):
        ref = ConnectorRef(
            connector_name="database.postgresql",
            config={"params": {"dsn": "postgres://..."}},
            description="PG extraction",
        )
        d = ref.to_dict()
        assert d["connector_name"] == "database.postgresql"
        assert d["connector_type"] == "database"
        assert d["config"] == {"params": {"dsn": "postgres://..."}}
        assert d["action"] == "execute"
        assert d["description"] == "PG extraction"

    def test_from_dict(self):
        data = {
            "connector_name": "http.rest",
            "connector_type": "http",
            "config": {"params": {"base_url": "https://api.example.com"}},
            "action": "get",
            "description": "REST API call",
        }
        ref = ConnectorRef.from_dict(data)
        assert ref.connector_name == "http.rest"
        assert ref.connector_type == "http"
        assert ref.action == "get"

    def test_from_dict_minimal(self):
        data = {"connector_name": "email.smtp"}
        ref = ConnectorRef.from_dict(data)
        assert ref.connector_name == "email.smtp"
        assert ref.connector_type == "email"
        assert ref.action == "execute"

    def test_roundtrip_serialization(self):
        ref = ConnectorRef(
            connector_name="social.slack",
            config={"params": {"webhook_url": "https://hooks.slack.com/..."}},
            action="send",
            description="Slack notif",
        )
        restored = ConnectorRef.from_dict(ref.to_dict())
        assert restored == ref

    def test_repr(self):
        ref = ConnectorRef(connector_name="database.postgresql", action="query")
        r = repr(ref)
        assert "database.postgresql" in r
        assert "database" in r
        assert "query" in r

    def test_equality(self):
        ref1 = ConnectorRef(connector_name="database.postgresql")
        ref2 = ConnectorRef(connector_name="database.postgresql")
        assert ref1 == ref2

    def test_inequality(self):
        ref1 = ConnectorRef(connector_name="database.postgresql")
        ref2 = ConnectorRef(connector_name="database.mysql")
        assert ref1 != ref2


# ======================================================================
# ConnectorOutcome
# ======================================================================


class TestConnectorOutcome:
    """Tests pour ConnectorOutcome (runtime, mutable)."""

    def test_default_construction(self):
        outcome = ConnectorOutcome()
        assert outcome.connector_name == ""
        assert outcome.success is False
        assert outcome.duration == pytest.approx(0.0)
        assert outcome.error is None
        assert outcome.records_affected is None
        assert outcome.data_summary == {}
        assert outcome.metadata == {}
        assert outcome.id  # UUID generated
        assert outcome.executed_at  # datetime generated

    def test_success_construction(self):
        outcome = ConnectorOutcome(
            connector_name="database.postgresql",
            connector_type="database",
            success=True,
            duration=1.234,
            records_affected=1500,
            data_summary={"row_count": 1500, "columns": ["id", "name"]},
        )
        assert outcome.success is True
        assert outcome.duration == pytest.approx(1.234)
        assert outcome.records_affected == 1500

    def test_failure_construction(self):
        outcome = ConnectorOutcome(
            connector_name="http.rest",
            success=False,
            error="Connection refused",
            duration=0.05,
        )
        assert outcome.success is False
        assert outcome.error == "Connection refused"

    def test_mutable(self):
        """ConnectorOutcome est mutable (runtime)."""
        outcome = ConnectorOutcome()
        outcome.success = True
        outcome.duration = 2.5
        assert outcome.success is True

    def test_to_dict(self):
        outcome = ConnectorOutcome(
            connector_name="storage.s3",
            connector_type="storage",
            success=True,
            duration=0.5,
            records_affected=42,
            data_summary={"type": "list", "count": 42},
            metadata={"bucket": "my-bucket"},
        )
        d = outcome.to_dict()
        assert d["connector_name"] == "storage.s3"
        assert d["connector_type"] == "storage"
        assert d["success"] is True
        assert d["duration"] == pytest.approx(0.5)
        assert d["records_affected"] == 42
        assert d["data_summary"] == {"type": "list", "count": 42}
        assert d["metadata"] == {"bucket": "my-bucket"}
        assert "id" in d
        assert "executed_at" in d

    def test_from_dict(self):
        data = {
            "id": "test-id-123",
            "connector_name": "database.postgresql",
            "connector_type": "database",
            "success": True,
            "duration": 1.0,
            "error": None,
            "records_affected": 100,
            "data_summary": {},
            "metadata": {},
            "executed_at": "2026-04-12T10:00:00+00:00",
        }
        outcome = ConnectorOutcome.from_dict(data)
        assert outcome.id == "test-id-123"
        assert outcome.connector_name == "database.postgresql"
        assert outcome.success is True
        assert outcome.records_affected == 100

    def test_from_dict_minimal(self):
        data = {"connector_name": "http.rest", "success": True}
        outcome = ConnectorOutcome.from_dict(data)
        assert outcome.connector_name == "http.rest"
        assert outcome.success is True
        assert outcome.duration == pytest.approx(0.0)

    def test_from_dict_duration_seconds_compat(self):
        """Rétrocompat : from_dict accepte l'ancien nom duration_seconds."""
        data = {"connector_name": "http.rest", "success": True, "duration_seconds": 1.5}
        outcome = ConnectorOutcome.from_dict(data)
        assert outcome.duration == pytest.approx(1.5)

    def test_roundtrip_serialization(self):
        outcome = ConnectorOutcome(
            connector_name="email.smtp",
            connector_type="email",
            success=True,
            duration=0.321,
            records_affected=1,
            metadata={"message_id": "abc-123"},
        )
        d = outcome.to_dict()
        restored = ConnectorOutcome.from_dict(d)
        assert restored.connector_name == outcome.connector_name
        assert restored.success == outcome.success
        assert restored.duration == pytest.approx(outcome.duration)
        assert restored.records_affected == outcome.records_affected
        assert restored.id == outcome.id

    def test_repr_success(self):
        outcome = ConnectorOutcome(
            connector_name="database.postgresql",
            success=True,
            duration=1.234,
        )
        r = repr(outcome)
        assert "✅" in r
        assert "database.postgresql" in r
        assert "1.234" in r

    def test_repr_failure(self):
        outcome = ConnectorOutcome(
            connector_name="http.rest",
            success=False,
            duration_seconds=0.05,
        )
        r = repr(outcome)
        assert "❌" in r


# ======================================================================
# Step + ConnectorRef integration
# ======================================================================


class TestStepConnectorRef:
    """Tests d'intégration Step ↔ ConnectorRef."""

    def test_step_without_connector_ref(self):
        step = Step(name="classic", step_type=StepType.FUNCTION)
        assert step.connector_ref is None

    def test_step_with_connector_ref(self):
        ref = ConnectorRef(
            connector_name="database.postgresql",
            config={"params": {"dsn": "postgres://..."}},
        )
        step = Step(
            name="extract_users",
            step_type=StepType.CONNECTOR,
            connector_ref=ref,
        )
        assert step.step_type == StepType.CONNECTOR
        assert step.connector_ref is not None
        assert step.connector_ref.connector_name == "database.postgresql"
        assert step.connector_ref.connector_type == "database"

    def test_step_connector_ref_serialization(self):
        ref = ConnectorRef(
            connector_name="http.rest",
            config={"params": {"base_url": "https://api.example.com"}},
            action="get",
            description="API call",
        )
        step = Step(
            name="fetch_data",
            step_type=StepType.CONNECTOR,
            connector_ref=ref,
        )
        d = step.to_dict()
        assert d["connector_ref"] is not None
        assert d["connector_ref"]["connector_name"] == "http.rest"
        assert d["connector_ref"]["action"] == "get"

    def test_step_connector_ref_deserialization(self):
        data = {
            "name": "write_db",
            "step_type": "connector",
            "connector_ref": {
                "connector_name": "database.postgresql",
                "connector_type": "database",
                "config": {"params": {"dsn": "postgres://..."}},
                "action": "execute",
                "description": "Write to PG",
            },
        }
        step = Step.from_dict(data)
        assert step.step_type == StepType.CONNECTOR
        assert step.connector_ref is not None
        assert step.connector_ref.connector_name == "database.postgresql"
        assert step.connector_ref.description == "Write to PG"

    def test_step_no_connector_ref_serialization(self):
        step = Step(name="classic", step_type=StepType.FUNCTION)
        d = step.to_dict()
        assert d["connector_ref"] is None

    def test_step_no_connector_ref_deserialization(self):
        data = {"name": "classic", "step_type": "function"}
        step = Step.from_dict(data)
        assert step.connector_ref is None

    def test_step_connector_roundtrip(self):
        ref = ConnectorRef(
            connector_name="social.slack",
            config={"params": {"webhook_url": "https://hooks.slack.com/..."}},
            action="send",
        )
        step = Step(
            name="notify",
            step_type=StepType.CONNECTOR,
            connector_ref=ref,
            timeout=timedelta(seconds=30),
            retry_count=2,
        )
        d = step.to_dict()
        restored = Step.from_dict(d)
        assert restored.name == step.name
        assert restored.step_type == StepType.CONNECTOR
        assert restored.connector_ref == ref
        assert restored.retry_count == 2


# ======================================================================
# StepRun + ConnectorOutcome integration
# ======================================================================


class TestStepRunConnectorOutcome:
    """Tests d'intégration StepRun ↔ ConnectorOutcome."""

    def test_step_run_without_outcome(self):
        sr = StepRun(step_name="classic", job_run_id="job-1")
        assert sr.connector_outcome is None

    def test_step_run_with_outcome(self):
        outcome = ConnectorOutcome(
            connector_name="database.postgresql",
            connector_type="database",
            success=True,
            duration=1.5,
            records_affected=100,
        )
        sr = StepRun(
            step_name="extract_users",
            job_run_id="job-1",
            connector_outcome=outcome,
        )
        assert sr.connector_outcome is not None
        assert sr.connector_outcome.success is True
        assert sr.connector_outcome.records_affected == 100

    def test_step_run_assign_outcome_later(self):
        sr = StepRun(step_name="fetch", job_run_id="job-1")
        assert sr.connector_outcome is None
        sr.connector_outcome = ConnectorOutcome(
            connector_name="http.rest",
            success=True,
            duration=0.5,
        )
        assert sr.connector_outcome is not None
        assert sr.connector_outcome.connector_name == "http.rest"

    def test_step_run_outcome_serialization(self):
        outcome = ConnectorOutcome(
            connector_name="storage.s3",
            connector_type="storage",
            success=True,
            duration=2.0,
            records_affected=42,
            data_summary={"type": "list", "count": 42},
        )
        sr = StepRun(
            step_name="upload",
            job_run_id="job-1",
            connector_outcome=outcome,
        )
        d = sr.to_dict()
        assert d["connector_outcome"] is not None
        assert d["connector_outcome"]["connector_name"] == "storage.s3"
        assert d["connector_outcome"]["success"] is True

    def test_step_run_outcome_deserialization(self):
        data = {
            "step_run_id": "sr-1",
            "step_name": "write_db",
            "job_run_id": "job-1",
            "status": "success",
            "connector_outcome": {
                "id": "co-1",
                "connector_name": "database.postgresql",
                "connector_type": "database",
                "success": True,
                "duration": 1.0,
                "error": None,
                "records_affected": 500,
                "data_summary": {},
                "metadata": {},
                "executed_at": "2026-04-12T10:00:00+00:00",
            },
        }
        sr = StepRun.from_dict(data)
        assert sr.connector_outcome is not None
        assert sr.connector_outcome.connector_name == "database.postgresql"
        assert sr.connector_outcome.records_affected == 500

    def test_step_run_no_outcome_serialization(self):
        sr = StepRun(step_name="classic", job_run_id="job-1")
        d = sr.to_dict()
        assert d["connector_outcome"] is None

    def test_step_run_no_outcome_deserialization(self):
        data = {
            "step_run_id": "sr-1",
            "step_name": "classic",
            "job_run_id": "job-1",
            "status": "pending",
        }
        sr = StepRun.from_dict(data)
        assert sr.connector_outcome is None

    def test_step_run_outcome_roundtrip(self):
        outcome = ConnectorOutcome(
            connector_name="email.smtp",
            connector_type="email",
            success=True,
            duration=0.3,
            records_affected=1,
            metadata={"message_id": "msg-abc"},
        )
        sr = StepRun(
            step_name="send_email",
            job_run_id="job-1",
            connector_outcome=outcome,
        )
        d = sr.to_dict()
        restored = StepRun.from_dict(d)
        assert restored.connector_outcome is not None
        assert restored.connector_outcome.connector_name == "email.smtp"
        assert restored.connector_outcome.records_affected == 1
        assert restored.connector_outcome.metadata == {"message_id": "msg-abc"}


# ======================================================================
# StepType.CONNECTOR enum
# ======================================================================


class TestStepTypeConnector:
    """Tests pour StepType.CONNECTOR."""

    def test_connector_enum_exists(self):
        assert hasattr(StepType, "CONNECTOR")
        assert StepType.CONNECTOR.value == "connector"

    def test_connector_enum_from_value(self):
        assert StepType("connector") == StepType.CONNECTOR

    def test_all_step_types_present(self):
        """Vérifie qu'on n'a pas cassé les types existants."""
        expected = {
            "function",
            "subprocess",
            "http_request",
            "sql_query",
            "human_task",
            "external_task",
            "sub_workflow",
            "connector",
        }
        actual = {st.value for st in StepType}
        assert expected.issubset(actual)


# ======================================================================
# Bridge connector_step
# ======================================================================


class TestBridgeConnectorStep:
    """Tests pour adapters/steps/connector_step.py."""

    def test_import_error_raises_step_execution_error(self):
        """Si pyconnectors n'est pas importable, StepExecutionError."""
        from pyworkflow_engine.adapters.steps.connector_step import execute_connector

        ref = ConnectorRef(connector_name="database.postgresql")

        # Simuler l'absence de pyconnectors
        with (
            patch.dict(
                sys.modules,
                {"pyconnectors.services.factory": None, "pyconnectors.config": None},
            ),
            pytest.raises(StepExecutionError, match="pyconnectors is not installed"),
        ):
            execute_connector(ref=ref)

    def test_execute_connector_success(self):
        """Le bridge retourne un ConnectorOutcome quand le connecteur réussit."""
        from pyworkflow_engine.adapters.steps.connector_step import (  # noqa: F401
            execute_connector,
        )

        # Mock du résultat pyconnectors
        mock_result = SimpleNamespace(
            success=True,
            data=[{"id": 1}, {"id": 2}],
            error=None,
            duration=0.5,
            metadata={"records_affected": 2},
        )

        mock_connector = MagicMock()
        mock_connector.safe_execute.return_value = mock_result

        mock_factory_cls = MagicMock()
        mock_factory_cls.create.return_value = mock_connector

        mock_config_cls = MagicMock()
        mock_config_cls.from_dict.return_value = MagicMock()

        ref = ConnectorRef(
            connector_name="database.postgresql",
            config={"params": {"dsn": "postgres://..."}},
        )

        with patch.dict(
            sys.modules,
            {
                "pyconnectors.services.factory": MagicMock(
                    ConnectorFactory=mock_factory_cls
                ),
                "pyconnectors.config": MagicMock(ConnectorConfig=mock_config_cls),
            },
        ):
            # Re-import pour que le lazy import utilise nos mocks
            import pyworkflow_engine.adapters.steps.connector_step as bridge_mod

            importlib.reload(bridge_mod)

            outcome = bridge_mod.execute_connector(ref=ref, query="SELECT 1")

        assert isinstance(outcome, ConnectorOutcome)
        assert outcome.success is True
        assert outcome.connector_name == "database.postgresql"
        assert outcome.connector_type == "database"
        assert outcome.records_affected == 2
        assert outcome.data_summary == {"type": "list", "count": 2}
        assert outcome.duration >= 0  # mocked call is near-instant

    def test_execute_connector_failure_raises(self):
        """Le bridge lève StepExecutionError quand ConnectorResult.success=False."""
        from pyworkflow_engine.adapters.steps.connector_step import (  # noqa: F401
            execute_connector,
        )

        mock_result = SimpleNamespace(
            success=False,
            data=None,
            error="Connection refused",
            duration=0.01,
            metadata={},
        )

        mock_connector = MagicMock()
        mock_connector.safe_execute.return_value = mock_result

        mock_factory_cls = MagicMock()
        mock_factory_cls.create.return_value = mock_connector

        mock_config_cls = MagicMock()
        mock_config_cls.from_dict.return_value = MagicMock()

        ref = ConnectorRef(connector_name="database.postgresql")

        with patch.dict(
            sys.modules,
            {
                "pyconnectors.services.factory": MagicMock(
                    ConnectorFactory=mock_factory_cls
                ),
                "pyconnectors.config": MagicMock(ConnectorConfig=mock_config_cls),
            },
        ):
            import pyworkflow_engine.adapters.steps.connector_step as bridge_mod

            importlib.reload(bridge_mod)

            with pytest.raises(StepExecutionError, match="failed"):
                bridge_mod.execute_connector(ref=ref)

    def test_execute_connector_unknown_action(self):
        """Le bridge lève StepExecutionError si l'action n'existe pas."""
        from pyworkflow_engine.adapters.steps.connector_step import (  # noqa: F401
            execute_connector,
        )

        mock_connector = MagicMock(spec=[])  # aucune méthode

        mock_factory_cls = MagicMock()
        mock_factory_cls.create.return_value = mock_connector

        mock_config_cls = MagicMock()
        mock_config_cls.from_dict.return_value = MagicMock()

        ref = ConnectorRef(
            connector_name="database.postgresql",
            action="nonexistent_action",
        )

        with patch.dict(
            sys.modules,
            {
                "pyconnectors.services.factory": MagicMock(
                    ConnectorFactory=mock_factory_cls
                ),
                "pyconnectors.config": MagicMock(ConnectorConfig=mock_config_cls),
            },
        ):
            import pyworkflow_engine.adapters.steps.connector_step as bridge_mod

            importlib.reload(bridge_mod)

            with pytest.raises(StepExecutionError, match="no action"):
                bridge_mod.execute_connector(ref=ref)

    def test_execute_connector_exception_during_execution(self):
        """Le bridge attrape les exceptions du connecteur et lève StepExecutionError."""
        from pyworkflow_engine.adapters.steps.connector_step import (  # noqa: F401
            execute_connector,
        )

        mock_connector = MagicMock()
        mock_connector.safe_execute.side_effect = RuntimeError("Network error")

        mock_factory_cls = MagicMock()
        mock_factory_cls.create.return_value = mock_connector

        mock_config_cls = MagicMock()
        mock_config_cls.from_dict.return_value = MagicMock()

        ref = ConnectorRef(connector_name="http.rest")

        with patch.dict(
            sys.modules,
            {
                "pyconnectors.services.factory": MagicMock(
                    ConnectorFactory=mock_factory_cls
                ),
                "pyconnectors.config": MagicMock(ConnectorConfig=mock_config_cls),
            },
        ):
            import pyworkflow_engine.adapters.steps.connector_step as bridge_mod

            importlib.reload(bridge_mod)

            with pytest.raises(StepExecutionError, match="raised"):
                bridge_mod.execute_connector(ref=ref)

    def test_build_summary_list(self):
        """_build_summary retourne type+count pour une liste."""
        from pyworkflow_engine.adapters.steps.connector_step import _build_summary

        assert _build_summary([1, 2, 3]) == {"type": "list", "count": 3}

    def test_build_summary_dict(self):
        """_build_summary retourne type+keys pour un dict."""
        from pyworkflow_engine.adapters.steps.connector_step import _build_summary

        result = _build_summary({"a": 1, "b": 2})
        assert result["type"] == "dict"
        assert "a" in result["keys"]
        assert "b" in result["keys"]

    def test_build_summary_none(self):
        """_build_summary retourne {} pour None."""
        from pyworkflow_engine.adapters.steps.connector_step import _build_summary

        assert _build_summary(None) == {}

    def test_build_summary_other(self):
        """_build_summary retourne le type pour un objet quelconque."""
        from pyworkflow_engine.adapters.steps.connector_step import _build_summary

        assert _build_summary(42) == {"type": "int"}
        assert _build_summary("hello") == {"type": "str"}


# ======================================================================
# models/__init__.py exports
# ======================================================================


class TestModelsExports:
    """Vérifie que ConnectorRef et ConnectorOutcome sont exportés."""

    def test_connector_ref_importable(self):
        from pyworkflow_engine.models import ConnectorRef as CR

        assert CR is ConnectorRef

    def test_connector_outcome_importable(self):
        from pyworkflow_engine.models import ConnectorOutcome as CO

        assert CO is ConnectorOutcome

    def test_in_all(self):
        import pyworkflow_engine.models as m

        assert "ConnectorRef" in m.__all__
        assert "ConnectorOutcome" in m.__all__
