"""
pyworkflow_engine.events — EventBus unifié.

Expose le bus, les événements et les helpers.

Usage ::

    from pyworkflow_engine.events import EventBus, get_event_bus
    from pyworkflow_engine.events import PipelineStartedEvent

    bus = get_event_bus()

    @bus.on("pipeline.started")
    def on_start(event: PipelineStartedEvent) -> None:
        print(f"Pipeline {event.pipeline_name} started")

    bus.emit(PipelineStartedEvent(pipeline_name="etl"))
"""

from __future__ import annotations

from pyworkflow_engine.events.bus import EventBus, get_event_bus, reset_event_bus
from pyworkflow_engine.events.events import (
    BaseEvent,
    ConnectorExecutedEvent,
    ConnectorFailedEvent,
    CustomEvent,
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
)

__all__ = [
    # Bus
    "EventBus",
    "get_event_bus",
    "reset_event_bus",
    # Base
    "BaseEvent",
    # Pipeline events
    "PipelineStartedEvent",
    "PipelineCompletedEvent",
    "PipelineFailedEvent",
    # Stage events
    "StageStartedEvent",
    "StageCompletedEvent",
    "StageFailedEvent",
    "StageSkippedEvent",
    # Job events
    "JobStartedEvent",
    "JobCompletedEvent",
    "JobFailedEvent",
    # Step events
    "StepStartedEvent",
    "StepCompletedEvent",
    "StepFailedEvent",
    # Connector events
    "ConnectorExecutedEvent",
    "ConnectorFailedEvent",
    # Custom
    "CustomEvent",
]
