"""
Tests unitaires — config/ai.py (AISettings) (ADR-013, Phase 3.4).
"""

from __future__ import annotations

import os

import pytest

from pyworkflow_engine.config.ai import AISettings, ai_settings


class TestAISettingsDefaults:
    def test_default_provider(self):
        cfg = AISettings()
        assert cfg.default_provider_type == "openai"

    def test_default_model(self):
        cfg = AISettings()
        assert cfg.default_model == "gpt-4o"

    def test_api_keys_empty_by_default(self):
        cfg = AISettings()
        assert cfg.openai_api_key == ""
        assert cfg.anthropic_api_key == ""

    def test_max_tool_iterations(self):
        cfg = AISettings()
        assert cfg.max_tool_iterations == 10

    def test_temperature(self):
        cfg = AISettings()
        assert cfg.default_temperature == pytest.approx(0.7)

    def test_max_tokens(self):
        cfg = AISettings()
        assert cfg.default_max_tokens == 4096

    def test_timeout(self):
        cfg = AISettings()
        assert cfg.default_timeout == 30

    def test_streaming_enabled(self):
        cfg = AISettings()
        assert cfg.enable_streaming is True

    def test_rag_disabled(self):
        cfg = AISettings()
        assert cfg.enable_rag is False

    def test_debug_disabled(self):
        cfg = AISettings()
        assert cfg.debug is False


class TestAISettingsOverride:
    def test_programmatic_override(self):
        cfg = AISettings(
            default_provider_type="anthropic",
            default_model="claude-3-5-sonnet-latest",
            max_tool_iterations=20,
            enable_rag=True,
        )
        assert cfg.default_provider_type == "anthropic"
        assert cfg.default_model == "claude-3-5-sonnet-latest"
        assert cfg.max_tool_iterations == 20
        assert cfg.enable_rag is True

    def test_frozen(self):
        """AISettings doit être immutable (frozen dataclass)."""
        cfg = AISettings()
        with pytest.raises((AttributeError, TypeError)):
            cfg.default_model = "changed"  # type: ignore[misc]

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("PYWORKFLOW_AI_DEFAULT_PROVIDER_TYPE", "gemini")
        monkeypatch.setenv("PYWORKFLOW_AI_DEFAULT_MODEL", "gemini-2.0-flash")
        monkeypatch.setenv("PYWORKFLOW_AI_MAX_TOOL_ITERATIONS", "25")
        monkeypatch.setenv("PYWORKFLOW_AI_ENABLE_STREAMING", "false")

        cfg = AISettings()
        assert cfg.default_provider_type == "gemini"
        assert cfg.default_model == "gemini-2.0-flash"
        assert cfg.max_tool_iterations == 25
        assert cfg.enable_streaming is False


class TestAISettingsSingleton:
    def test_singleton_exists(self):
        assert ai_settings is not None
        assert isinstance(ai_settings, AISettings)

    def test_singleton_is_ai_settings(self):
        assert isinstance(ai_settings, AISettings)


class TestAISettingsConfigImport:
    def test_importable_from_config(self):
        from pyworkflow_engine.config import AISettings as AIS
        from pyworkflow_engine.config import ai_settings as ais

        assert AIS is AISettings
        assert isinstance(ais, AISettings)
