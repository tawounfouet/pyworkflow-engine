"""
Tests unitaires — models/ai/provider.py (ADR-013, Phase 3.2).

Vérifie :
  - Construction et valeurs par défaut de LLMProviderConfig
  - ProviderCapabilities, PricingConfig, ProviderSettings
  - get_api_key_value() / get_secret()
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from pyworkflow_engine.models.ai.provider import (
    LLMProviderConfig,
    PricingConfig,
    ProviderCapabilities,
    ProviderSettings,
)
from pyworkflow_engine.models.ai.types import ProviderType


class TestProviderCapabilities:
    def test_defaults(self):
        caps = ProviderCapabilities()
        assert caps.vision is False
        assert caps.function_calling is True
        assert caps.streaming is True
        assert caps.context_window == 4096

    def test_custom(self):
        caps = ProviderCapabilities(vision=True, context_window=128_000)
        assert caps.vision is True
        assert caps.context_window == 128_000


class TestPricingConfig:
    def test_defaults(self):
        p = PricingConfig()
        assert p.input_per_1k_tokens == 0.0
        assert p.currency == "USD"


class TestProviderSettings:
    def test_temperature_default(self):
        s = ProviderSettings()
        assert s.temperature == 0.7

    def test_temperature_bounds(self):
        with pytest.raises(Exception):
            ProviderSettings(temperature=3.0)  # > 2.0

    def test_max_tokens_nullable(self):
        s = ProviderSettings(max_tokens=None)
        assert s.max_tokens is None


class TestLLMProviderConfig:
    def _make(self, **kwargs) -> LLMProviderConfig:
        return LLMProviderConfig(
            name="Test Provider",
            provider_type=ProviderType.OPENAI,
            default_model="gpt-4o",
            **kwargs,
        )

    def test_creation_minimal(self):
        p = self._make()
        assert p.name == "Test Provider"
        assert p.provider_type == ProviderType.OPENAI
        assert p.default_model == "gpt-4o"
        assert p.is_active is True
        assert p.is_default is False

    def test_id_auto_generated(self):
        p1 = self._make()
        p2 = self._make()
        assert p1.id != p2.id

    def test_api_key_none_by_default(self):
        p = self._make()
        assert p.get_api_key_value() is None

    def test_api_key_secret(self):
        p = self._make(api_key=SecretStr("sk-secret"))
        assert p.get_api_key_value() == "sk-secret"
        # SecretStr ne fuite pas en repr
        assert "sk-secret" not in repr(p)

    def test_get_secret(self):
        p = self._make(extra_secrets={"my_token": "tok-abc"})
        assert p.get_secret("my_token") == "tok-abc"
        assert p.get_secret("missing", "fallback") == "fallback"

    def test_nested_defaults(self):
        p = self._make()
        assert isinstance(p.settings, ProviderSettings)
        assert isinstance(p.capabilities, ProviderCapabilities)
        assert isinstance(p.pricing, PricingConfig)
