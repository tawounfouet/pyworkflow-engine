"""
Tests unitaires — models/ai/execution.py (ADR-013, Phase 3.2).
Vérifie les champs IA optionnels (agent_id, tool_id, token_usage) sur ExecutionStep.
"""

from __future__ import annotations

import pytest

from pyworkflow_engine.models.ai.execution import Execution, ExecutionStep
from pyworkflow_engine.models.ai.message import TokenUsage
from pyworkflow_engine.models.ai.types import AIStepType, ExecutionStatus
from pyworkflow_engine.models.enums import RunStatus


class TestExecutionStep:
    def test_creation_minimal(self):
        step = ExecutionStep(
            execution_id="exec-1",
            step_type=AIStepType.LLM_CALL,
        )
        assert step.execution_id == "exec-1"
        assert step.step_type == AIStepType.LLM_CALL
        assert step.order == 0
        assert step.agent_id is None
        assert step.tool_id is None
        assert step.token_usage is None

    def test_ai_fields_optional(self):
        tu = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        step = ExecutionStep(
            execution_id="exec-1",
            step_type=AIStepType.TOOL_CALL,
            agent_id="agent-uuid",
            tool_id="tool-uuid",
            token_usage=tu,
        )
        assert step.agent_id == "agent-uuid"
        assert step.tool_id == "tool-uuid"
        assert step.token_usage is not None
        assert step.token_usage.total_tokens == 150

    def test_order_ge_0(self):
        with pytest.raises(Exception):
            ExecutionStep(execution_id="e", step_type=AIStepType.LLM_CALL, order=-1)

    def test_id_auto_generated(self):
        s1 = ExecutionStep(execution_id="e", step_type=AIStepType.LLM_CALL)
        s2 = ExecutionStep(execution_id="e", step_type=AIStepType.LLM_CALL)
        assert s1.id != s2.id


class TestExecution:
    def test_creation_minimal(self):
        ex = Execution(agent_id="agent-uuid")
        assert ex.agent_id == "agent-uuid"
        assert ex.status == ExecutionStatus.PENDING
        assert ex.status == RunStatus.PENDING  # alias check
        assert ex.total_steps == 0
        assert ex.error == ""

    def test_token_usage_default(self):
        ex = Execution(agent_id="ag-1")
        assert ex.token_usage.total_tokens == 0

    def test_status_transitions(self):
        ex = Execution(agent_id="ag-1")
        # PENDING → RUNNING → SUCCESS
        ex.status = ExecutionStatus.RUNNING
        assert ex.status == RunStatus.RUNNING
        ex.status = ExecutionStatus.SUCCESS
        assert ex.status == RunStatus.SUCCESS

    def test_id_auto_generated(self):
        e1 = Execution(agent_id="a")
        e2 = Execution(agent_id="a")
        assert e1.id != e2.id

    def test_optional_relations(self):
        ex = Execution(
            agent_id="ag-1",
            graph_id="graph-uuid",
            conversation_id="conv-uuid",
        )
        assert ex.graph_id == "graph-uuid"
        assert ex.conversation_id == "conv-uuid"
