"""
Tests unitaires — models/run.py champs IA (ADR-013, Phase 3.3).

Vérifie que les champs agent_id, tool_id et token_usage sont bien
présents sur StepRun, sérialisés / désérialisés correctement.
"""

from __future__ import annotations

import pytest

from pyworkflow_engine.models.workflow.run import StepRun


class TestStepRunAIFields:
    def test_ai_fields_default_none(self):
        sr = StepRun(step_name="llm_step")
        assert sr.agent_id is None
        assert sr.tool_id is None
        assert sr.token_usage is None

    def test_ai_fields_set(self):
        sr = StepRun(
            step_name="llm_step",
            agent_id="agent-uuid",
            tool_id="tool-uuid",
            token_usage={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "estimated_cost_usd": 0.002,
            },
        )
        assert sr.agent_id == "agent-uuid"
        assert sr.tool_id == "tool-uuid"
        assert sr.token_usage["total_tokens"] == 150

    def test_to_dict_includes_ai_fields(self):
        sr = StepRun(
            step_name="llm_step",
            agent_id="agent-uuid",
            tool_id="tool-uuid",
            token_usage={
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.0,
            },
        )
        d = sr.to_dict()
        assert d["agent_id"] == "agent-uuid"
        assert d["tool_id"] == "tool-uuid"
        assert d["token_usage"]["total_tokens"] == 15

    def test_to_dict_ai_fields_none(self):
        sr = StepRun(step_name="regular_step")
        d = sr.to_dict()
        assert d["agent_id"] is None
        assert d["tool_id"] is None
        assert d["token_usage"] is None

    def test_from_dict_round_trip_with_ai_fields(self):
        sr = StepRun(
            step_name="tool_step",
            agent_id="ag-1",
            tool_id="tl-1",
            token_usage={
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "estimated_cost_usd": 0.001,
            },
        )
        restored = StepRun.from_dict(sr.to_dict())
        assert restored.agent_id == "ag-1"
        assert restored.tool_id == "tl-1"
        assert restored.token_usage["total_tokens"] == 30

    def test_from_dict_round_trip_no_ai_fields(self):
        sr = StepRun(step_name="regular")
        restored = StepRun.from_dict(sr.to_dict())
        assert restored.agent_id is None
        assert restored.tool_id is None
        assert restored.token_usage is None

    def test_from_dict_backward_compat_missing_ai_keys(self):
        """Désérialisation d'un dict ancien (sans les clés IA) ne doit pas planter."""
        d = StepRun(step_name="old_step").to_dict()
        # Simule un ancien dict sans les nouvelles clés
        d.pop("agent_id", None)
        d.pop("tool_id", None)
        d.pop("token_usage", None)
        restored = StepRun.from_dict(d)
        assert restored.agent_id is None
        assert restored.tool_id is None
        assert restored.token_usage is None
