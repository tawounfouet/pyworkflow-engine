"""
Tests unitaires — EventBus unifié + événements (ADR-013 / ADR-014 / ADR-016).

Couverture :
  - ``EventBus`` : subscribe, emit, unsubscribe, wildcard, middleware,
    handler_count, clear, error isolation, raise_on_handler_error
  - ``aemit`` : émission asynchrone (sync + async handlers)
  - ``BaseEvent`` : construction, to_dict, defaults
  - Événements Pipeline : started, completed, failed
  - Événements Stage : started, completed, failed, skipped
  - Événements Job : started, completed, failed
  - Événements Step : started, completed, failed
  - Événements Connector : executed, failed
  - ``CustomEvent``
  - ``get_event_bus`` / ``reset_event_bus`` : singleton global
  - Exports ``events/__init__.py``
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from pyworkflow_engine.events import (
    BaseEvent,
    ConnectorExecutedEvent,
    ConnectorFailedEvent,
    CustomEvent,
    EventBus,
    JobCompletedEvent,
    JobFailedEvent,
    JobStartedEvent,
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStartedEvent,
    StageCompletedEvent,
    StageFailedEvent,
    StageSkippedEvent,
    StageStartedEvent,
    StepCompletedEvent,
    StepFailedEvent,
    StepStartedEvent,
    get_event_bus,
    reset_event_bus,
)
from pyworkflow_engine.events.bus import EventHandlerError

# ======================================================================
# BaseEvent
# ======================================================================


class TestBaseEvent:
    """Tests du BaseEvent dataclass."""

    def test_construction(self):
        event = BaseEvent(event_type="test.event")
        assert event.event_type == "test.event"
        assert event.event_id  # non-empty UUID
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}

    def test_unique_ids(self):
        e1 = BaseEvent(event_type="a")
        e2 = BaseEvent(event_type="a")
        assert e1.event_id != e2.event_id

    def test_to_dict(self):
        event = BaseEvent(event_type="test.event", metadata={"key": "val"})
        d = event.to_dict()
        assert d["event_type"] == "test.event"
        assert d["metadata"] == {"key": "val"}
        assert isinstance(d["timestamp"], str)  # ISO format
        assert isinstance(d["event_id"], str)

    def test_custom_metadata(self):
        event = BaseEvent(event_type="x", metadata={"a": 1, "b": [2, 3]})
        assert event.metadata["a"] == 1
        assert event.metadata["b"] == [2, 3]


# ======================================================================
# EventBus — subscribe & emit
# ======================================================================


class TestEventBusBasic:
    """Tests de base de l'EventBus."""

    def test_subscribe_and_emit(self):
        bus = EventBus()
        received: list[BaseEvent] = []

        @bus.on("test.event")
        def handler(event: BaseEvent) -> None:
            received.append(event)

        event = BaseEvent(event_type="test.event")
        bus.emit(event)

        assert len(received) == 1
        assert received[0] is event

    def test_multiple_handlers(self):
        bus = EventBus()
        calls: list[str] = []

        @bus.on("test.event")
        def h1(event: BaseEvent) -> None:
            calls.append("h1")

        @bus.on("test.event")
        def h2(event: BaseEvent) -> None:
            calls.append("h2")

        bus.emit(BaseEvent(event_type="test.event"))
        assert calls == ["h1", "h2"]

    def test_no_handler_no_error(self):
        bus = EventBus()
        bus.emit(BaseEvent(event_type="unhandled"))  # Should not raise

    def test_different_event_types(self):
        bus = EventBus()
        received_a: list[BaseEvent] = []
        received_b: list[BaseEvent] = []

        @bus.on("type.a")
        def ha(event: BaseEvent) -> None:
            received_a.append(event)

        @bus.on("type.b")
        def hb(event: BaseEvent) -> None:
            received_b.append(event)

        bus.emit(BaseEvent(event_type="type.a"))
        bus.emit(BaseEvent(event_type="type.b"))

        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_subscribe_method(self):
        bus = EventBus()
        received: list[BaseEvent] = []

        def handler(event: BaseEvent) -> None:
            received.append(event)

        bus.subscribe("test.event", handler)
        bus.emit(BaseEvent(event_type="test.event"))
        assert len(received) == 1


# ======================================================================
# EventBus — wildcard
# ======================================================================


class TestEventBusWildcard:
    """Tests des wildcard handlers."""

    def test_subscribe_all(self):
        bus = EventBus()
        all_events: list[BaseEvent] = []

        bus.subscribe_all(lambda event: all_events.append(event))

        bus.emit(BaseEvent(event_type="pipeline.started"))
        bus.emit(BaseEvent(event_type="step.completed"))

        assert len(all_events) == 2

    def test_wildcard_plus_specific(self):
        bus = EventBus()
        specific: list[str] = []
        wild: list[str] = []

        @bus.on("pipeline.started")
        def h_specific(event: BaseEvent) -> None:
            specific.append(event.event_type)

        bus.subscribe_all(lambda event: wild.append(event.event_type))

        bus.emit(BaseEvent(event_type="pipeline.started"))
        bus.emit(BaseEvent(event_type="other"))

        assert specific == ["pipeline.started"]
        assert wild == ["pipeline.started", "other"]


# ======================================================================
# EventBus — unsubscribe
# ======================================================================


class TestEventBusUnsubscribe:
    """Tests de la désinscription."""

    def test_unsubscribe_returns_true(self):
        bus = EventBus()

        def handler(event: BaseEvent) -> None:
            pass

        bus.subscribe("x", handler)
        assert bus.unsubscribe("x", handler) is True

    def test_unsubscribe_returns_false_not_found(self):
        bus = EventBus()

        def handler(event: BaseEvent) -> None:
            pass

        assert bus.unsubscribe("x", handler) is False

    def test_unsubscribed_handler_not_called(self):
        bus = EventBus()
        calls: list[str] = []

        def handler(event: BaseEvent) -> None:
            calls.append("called")

        bus.subscribe("x", handler)
        bus.unsubscribe("x", handler)
        bus.emit(BaseEvent(event_type="x"))

        assert calls == []


# ======================================================================
# EventBus — middleware
# ======================================================================


class TestEventBusMiddleware:
    """Tests des middlewares."""

    def test_middleware_called_before_handlers(self):
        bus = EventBus()
        order: list[str] = []

        bus.add_middleware(lambda event: order.append("middleware"))

        @bus.on("test")
        def handler(event: BaseEvent) -> None:
            order.append("handler")

        bus.emit(BaseEvent(event_type="test"))
        assert order == ["middleware", "handler"]

    def test_middleware_error_does_not_block(self):
        bus = EventBus()
        calls: list[str] = []

        def bad_mw(event: BaseEvent) -> None:
            raise RuntimeError("middleware error")

        bus.add_middleware(bad_mw)

        @bus.on("test")
        def handler(event: BaseEvent) -> None:
            calls.append("ok")

        bus.emit(BaseEvent(event_type="test"))
        assert calls == ["ok"]


# ======================================================================
# EventBus — error handling
# ======================================================================


class TestEventBusErrorHandling:
    """Tests de l'isolation des erreurs."""

    def test_handler_error_isolated(self):
        bus = EventBus(raise_on_handler_error=False)
        calls: list[str] = []

        @bus.on("test")
        def bad_handler(event: BaseEvent) -> None:
            raise RuntimeError("boom")

        @bus.on("test")
        def good_handler(event: BaseEvent) -> None:
            calls.append("ok")

        bus.emit(BaseEvent(event_type="test"))
        assert calls == ["ok"]

    def test_raise_on_handler_error(self):
        bus = EventBus(raise_on_handler_error=True)

        @bus.on("test")
        def bad_handler(event: BaseEvent) -> None:
            raise RuntimeError("boom")

        with pytest.raises(EventHandlerError, match="boom"):
            bus.emit(BaseEvent(event_type="test"))


# ======================================================================
# EventBus — handler_count & clear
# ======================================================================


class TestEventBusUtilities:
    """Tests des utilitaires."""

    def test_handler_count_empty(self):
        bus = EventBus()
        assert bus.handler_count() == 0

    def test_handler_count_specific(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)

        assert bus.handler_count("a") == 2
        assert bus.handler_count("b") == 1
        assert bus.handler_count() == 3

    def test_clear_specific(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.clear("a")

        assert bus.handler_count("a") == 0
        assert bus.handler_count("b") == 1

    def test_clear_all(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.clear()

        assert bus.handler_count() == 0

    def test_repr(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        assert "handlers=1" in repr(bus)


# ======================================================================
# EventBus — async (aemit)
# ======================================================================


class TestEventBusAsync:
    """Tests de l'émission asynchrone."""

    def test_aemit_async_handler(self):
        bus = EventBus()
        received: list[str] = []

        @bus.on("test")
        async def async_handler(event: BaseEvent) -> None:
            received.append("async")

        asyncio.run(bus.aemit(BaseEvent(event_type="test")))
        assert received == ["async"]

    def test_aemit_sync_handler(self):
        bus = EventBus()
        received: list[str] = []

        @bus.on("test")
        def sync_handler(event: BaseEvent) -> None:
            received.append("sync")

        asyncio.run(bus.aemit(BaseEvent(event_type="test")))
        assert received == ["sync"]

    def test_aemit_mixed_handlers(self):
        bus = EventBus()
        received: list[str] = []

        @bus.on("test")
        def sync_handler(event: BaseEvent) -> None:
            received.append("sync")

        @bus.on("test")
        async def async_handler(event: BaseEvent) -> None:
            received.append("async")

        asyncio.run(bus.aemit(BaseEvent(event_type="test")))
        assert "sync" in received
        assert "async" in received

    def test_aemit_error_isolation(self):
        bus = EventBus(raise_on_handler_error=False)
        received: list[str] = []

        @bus.on("test")
        async def bad(event: BaseEvent) -> None:
            raise RuntimeError("boom")

        @bus.on("test")
        async def good(event: BaseEvent) -> None:
            received.append("ok")

        asyncio.run(bus.aemit(BaseEvent(event_type="test")))
        assert received == ["ok"]

    def test_aemit_raise_on_handler_error(self):
        bus = EventBus(raise_on_handler_error=True)

        @bus.on("test")
        async def bad(event: BaseEvent) -> None:
            raise RuntimeError("async boom")

        with pytest.raises(EventHandlerError, match="async boom"):
            asyncio.run(bus.aemit(BaseEvent(event_type="test")))


# ======================================================================
# Global singleton
# ======================================================================


class TestGlobalEventBus:
    """Tests du singleton global."""

    def test_get_event_bus_returns_instance(self):
        reset_event_bus()
        bus = get_event_bus()
        assert isinstance(bus, EventBus)

    def test_get_event_bus_singleton(self):
        reset_event_bus()
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_event_bus(self):
        reset_event_bus()
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2


# ======================================================================
# Pipeline Events
# ======================================================================


class TestPipelineEvents:
    """Tests des événements Pipeline."""

    def test_pipeline_started(self):
        e = PipelineStartedEvent(
            pipeline_name="etl",
            pipeline_run_id="run-1",
            pipeline_version="1.0.0",
            triggered_by="schedule",
        )
        assert e.event_type == "pipeline.started"
        assert e.pipeline_name == "etl"
        assert e.triggered_by == "schedule"

    def test_pipeline_completed(self):
        e = PipelineCompletedEvent(
            pipeline_name="etl",
            pipeline_run_id="run-1",
            duration_ms=5000,
            stage_count=3,
        )
        assert e.event_type == "pipeline.completed"
        assert e.duration_ms == 5000
        assert e.stage_count == 3

    def test_pipeline_failed(self):
        e = PipelineFailedEvent(
            pipeline_name="etl",
            pipeline_run_id="run-1",
            error="Stage 2 failed",
            failed_stage="transform",
        )
        assert e.event_type == "pipeline.failed"
        assert e.error == "Stage 2 failed"
        assert e.failed_stage == "transform"

    def test_pipeline_event_emitted_and_received(self):
        bus = EventBus()
        received: list[PipelineStartedEvent] = []

        @bus.on("pipeline.started")
        def handler(event: PipelineStartedEvent) -> None:
            received.append(event)

        event = PipelineStartedEvent(pipeline_name="test")
        bus.emit(event)

        assert len(received) == 1
        assert received[0].pipeline_name == "test"


# ======================================================================
# Stage Events
# ======================================================================


class TestStageEvents:
    """Tests des événements Stage."""

    def test_stage_started(self):
        e = StageStartedEvent(
            pipeline_run_id="pr-1",
            stage_run_id="sr-1",
            job_name="ingestion",
            stage_index=0,
        )
        assert e.event_type == "stage.started"
        assert e.job_name == "ingestion"

    def test_stage_completed(self):
        e = StageCompletedEvent(
            job_name="transform",
            stage_index=1,
            duration_ms=3000,
        )
        assert e.event_type == "stage.completed"
        assert e.duration_ms == 3000

    def test_stage_failed(self):
        e = StageFailedEvent(
            job_name="transform",
            error="Timeout exceeded",
        )
        assert e.event_type == "stage.failed"
        assert e.error == "Timeout exceeded"

    def test_stage_skipped(self):
        e = StageSkippedEvent(
            job_name="optional",
            reason="Condition returned False",
        )
        assert e.event_type == "stage.skipped"
        assert e.reason == "Condition returned False"


# ======================================================================
# Job Events
# ======================================================================


class TestJobEvents:
    """Tests des événements Job."""

    def test_job_started(self):
        e = JobStartedEvent(
            job_name="ingestion-job",
            job_run_id="jr-1",
            job_version="1.0.0",
        )
        assert e.event_type == "job.started"
        assert e.job_name == "ingestion-job"

    def test_job_completed(self):
        e = JobCompletedEvent(
            job_name="ingestion-job",
            job_run_id="jr-1",
            duration_ms=10000,
            step_count=3,
        )
        assert e.event_type == "job.completed"
        assert e.step_count == 3

    def test_job_failed(self):
        e = JobFailedEvent(
            job_name="ingestion-job",
            error="Step fetch failed",
            failed_step="fetch",
        )
        assert e.event_type == "job.failed"
        assert e.failed_step == "fetch"


# ======================================================================
# Step Events
# ======================================================================


class TestStepEvents:
    """Tests des événements Step."""

    def test_step_started(self):
        e = StepStartedEvent(
            job_run_id="jr-1",
            step_name="fetch",
            step_type="function",
        )
        assert e.event_type == "step.started"
        assert e.step_name == "fetch"

    def test_step_completed(self):
        e = StepCompletedEvent(
            step_name="fetch",
            step_type="function",
            duration_ms=500,
        )
        assert e.event_type == "step.completed"
        assert e.duration_ms == 500

    def test_step_failed(self):
        e = StepFailedEvent(
            step_name="fetch",
            step_type="http_request",
            error="Connection refused",
        )
        assert e.event_type == "step.failed"
        assert e.error == "Connection refused"


# ======================================================================
# Connector Events (ADR-016)
# ======================================================================


class TestConnectorEvents:
    """Tests des événements Connector."""

    def test_connector_executed(self):
        e = ConnectorExecutedEvent(
            connector_name="database.postgresql",
            connector_type="database",
            action="query",
            duration_ms=150,
            records_affected=42,
            step_name="fetch_raw",
            job_run_id="jr-1",
        )
        assert e.event_type == "connector.executed"
        assert e.connector_name == "database.postgresql"
        assert e.connector_type == "database"
        assert e.records_affected == 42

    def test_connector_failed(self):
        e = ConnectorFailedEvent(
            connector_name="http.rest",
            connector_type="http",
            action="get",
            error="404 Not Found",
            step_name="fetch_api",
        )
        assert e.event_type == "connector.failed"
        assert e.error == "404 Not Found"

    def test_connector_event_emitted(self):
        bus = EventBus()
        received: list[ConnectorExecutedEvent] = []

        @bus.on("connector.executed")
        def handler(event: ConnectorExecutedEvent) -> None:
            received.append(event)

        bus.emit(
            ConnectorExecutedEvent(
                connector_name="database.postgresql",
                records_affected=10,
            )
        )

        assert len(received) == 1
        assert received[0].records_affected == 10


# ======================================================================
# Custom Event
# ======================================================================


class TestCustomEvent:
    """Tests du CustomEvent."""

    def test_custom_event(self):
        e = CustomEvent(name="my.event", data={"key": "value"})
        assert e.event_type == "custom"
        assert e.name == "my.event"
        assert e.data == {"key": "value"}

    def test_custom_event_to_dict(self):
        e = CustomEvent(name="test", data={"x": 1})
        d = e.to_dict()
        assert d["name"] == "test"
        assert d["data"] == {"x": 1}
        assert d["event_type"] == "custom"


# ======================================================================
# Exports from events/__init__.py
# ======================================================================


class TestEventExports:
    """Vérifie les exports de ``events/__init__.py``."""

    def test_all_pipeline_events(self):
        from pyworkflow_engine.events import (  # noqa: F401
            PipelineCompletedEvent,
            PipelineFailedEvent,
            PipelineStartedEvent,
        )

    def test_all_stage_events(self):
        from pyworkflow_engine.events import (  # noqa: F401
            StageCompletedEvent,
            StageFailedEvent,
            StageSkippedEvent,
            StageStartedEvent,
        )

    def test_all_job_events(self):
        from pyworkflow_engine.events import (  # noqa: F401
            JobCompletedEvent,
            JobFailedEvent,
            JobStartedEvent,
        )

    def test_all_step_events(self):
        from pyworkflow_engine.events import (  # noqa: F401
            StepCompletedEvent,
            StepFailedEvent,
            StepStartedEvent,
        )

    def test_all_connector_events(self):
        from pyworkflow_engine.events import (  # noqa: F401
            ConnectorExecutedEvent,
            ConnectorFailedEvent,
        )

    def test_bus_exports(self):
        from pyworkflow_engine.events import (  # noqa: F401
            EventBus,
            get_event_bus,
            reset_event_bus,
        )

    def test_base_and_custom(self):
        from pyworkflow_engine.events import BaseEvent, CustomEvent  # noqa: F401
