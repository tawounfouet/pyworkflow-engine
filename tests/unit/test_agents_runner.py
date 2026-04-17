"""
Tests unitaires — agents/shared/runner.py (ADR-019, Phase 4).

Vérifie le AgentRunner avec un client LLM mocké (pas d'appels réseau).
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Iterator
from unittest.mock import patch

import pytest

from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.types import AgentRole, MessageRole, ProviderType
from pyworkflow_engine.ports.ai.llm import (
    BaseLLMClient,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TokenUsage,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


class FakeLLMClient(BaseLLMClient):
    """Client LLM factice pour les tests (aucun appel réseau)."""

    def __init__(self, provider_config: Any) -> None:
        # Ne pas appeler super().__init__ si provider_config est None
        self.provider_config = provider_config
        self.call_count = 0
        self.last_request: LLMRequest | None = None
        self._model = "fake-model"

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        self.last_request = request
        return LLMResponse(
            content=f"Fake response #{self.call_count}",
            model=self._model,
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            response_time_ms=42.0,
        )

    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        self.last_request = request
        return LLMResponse(
            content=f"Async fake response #{self.call_count}",
            model=self._model,
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            response_time_ms=33.0,
        )

    def stream(self, request: LLMRequest) -> Iterator[StreamChunk]:
        yield StreamChunk(delta="Hello ", finish_reason=None)
        yield StreamChunk(delta="world!", finish_reason="stop")

    async def astream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(delta="Async ", finish_reason=None)
        yield StreamChunk(delta="world!", finish_reason="stop")


@pytest.fixture()
def sample_agent() -> Agent:
    """Agent de test minimal."""
    return Agent(
        name="Test Agent",
        slug="test-agent",
        description="Agent pour les tests unitaires",
        role=AgentRole.ASSISTANT,
        provider_id="default-openai",
        system_prompt="Tu es un assistant de test.",
        welcome_message="Bonjour, test !",
        config=AgentConfig(
            temperature=0.5,
            max_tokens_per_response=100,
            max_iterations=5,
        ),
    )


@pytest.fixture()
def runner_with_fake_client(sample_agent: Agent):
    """AgentRunner avec un FakeLLMClient injecté (persist=False pour isoler des appels LLM)."""
    from agents.shared.runner import AgentRunner

    # Patch get_llm_client pour retourner notre fake
    with patch("agents.shared.runner.get_llm_client") as mock_factory:
        fake_client = FakeLLMClient(None)
        mock_factory.return_value = fake_client
        # persist=False : désactive storage + MemoryExtractor pour éviter
        # que extract_and_save() appelle le client et décale call_count
        runner = AgentRunner(
            sample_agent, api_key="sk-fake-key-for-tests", persist=False
        )
        # Remplacer le client interne par notre fake qui a un provider_config valide
        runner._client = fake_client
        yield runner, fake_client


# ── Tests AgentRunner ─────────────────────────────────────────────────────────


class TestAgentRunnerInit:
    """Tests d'initialisation du runner."""

    def test_init_with_api_key(self, sample_agent: Agent):
        from agents.shared.runner import AgentRunner

        with patch("agents.shared.runner.get_llm_client") as mock_factory:
            mock_factory.return_value = FakeLLMClient(None)
            runner = AgentRunner(sample_agent, api_key="sk-test-key", persist=False)

        assert runner.agent is sample_agent
        assert len(runner.history) == 1  # system prompt
        assert runner.history[0].role == MessageRole.SYSTEM

    def test_init_without_api_key_raises(self, sample_agent: Agent):
        from agents.shared.runner import AgentRunnerError

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(AgentRunnerError, match="Aucune clé API"):
                from agents.shared.runner import AgentRunner

                AgentRunner(sample_agent)

    def test_init_with_env_api_key(self, sample_agent: Agent):
        from agents.shared.runner import AgentRunner

        with patch("agents.shared.runner.get_llm_client") as mock_factory:
            mock_factory.return_value = FakeLLMClient(None)
            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-env-key"}):
                runner = AgentRunner(sample_agent, persist=False)

        assert runner.agent.slug == "test-agent"

    def test_init_system_prompt_in_history(self, sample_agent: Agent):
        from agents.shared.runner import AgentRunner

        with patch("agents.shared.runner.get_llm_client") as mock_factory:
            mock_factory.return_value = FakeLLMClient(None)
            runner = AgentRunner(sample_agent, api_key="sk-test", persist=False)

        assert len(runner.history) == 1
        assert runner.history[0].content == "Tu es un assistant de test."

    def test_init_no_system_prompt(self):
        from agents.shared.runner import AgentRunner

        agent = Agent(
            name="No Prompt",
            slug="no-prompt",
            role=AgentRole.ASSISTANT,
            provider_id="default-openai",
            system_prompt="",
        )
        with patch("agents.shared.runner.get_llm_client") as mock_factory:
            mock_factory.return_value = FakeLLMClient(None)
            runner = AgentRunner(agent, api_key="sk-test", persist=False)

        assert len(runner.history) == 0

    def test_model_property(self, sample_agent: Agent):
        from agents.shared.runner import AgentRunner

        with patch("agents.shared.runner.get_llm_client") as mock_factory:
            mock_factory.return_value = FakeLLMClient(None)
            runner = AgentRunner(sample_agent, api_key="sk-test", model="gpt-4o-mini")

        assert runner.model == "gpt-4o-mini"


class TestAgentRunnerAsk:
    """Tests de la méthode ask (synchrone)."""

    def test_ask_returns_response(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        response = runner.ask("Bonjour")
        assert isinstance(response, LLMResponse)
        assert response.content == "Fake response #1"

    def test_ask_adds_to_history(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        initial_len = len(runner.history)
        runner.ask("Première question")

        # system + user + assistant = initial + 2
        assert len(runner.history) == initial_len + 2

    def test_ask_multi_turn(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        r1 = runner.ask("Q1")
        r2 = runner.ask("Q2")
        r3 = runner.ask("Q3")

        assert r1.content == "Fake response #1"
        assert r2.content == "Fake response #2"
        assert r3.content == "Fake response #3"
        assert fake.call_count == 3

        # system + 3*(user+assistant) = 1 + 6 = 7
        assert len(runner.history) == 7

    def test_ask_passes_temperature(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        runner.ask("Test", temperature=0.2)

        assert fake.last_request is not None
        assert fake.last_request.temperature == 0.2

    def test_ask_uses_agent_temperature_by_default(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        runner.ask("Test")

        assert fake.last_request is not None
        assert fake.last_request.temperature == 0.5  # from AgentConfig

    def test_ask_response_has_usage(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        response = runner.ask("Test")

        assert response.usage is not None
        assert response.usage.total_tokens == 15

    def test_ask_response_has_time(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        response = runner.ask("Test")

        assert response.response_time_ms == 42.0


class TestAgentRunnerAask:
    """Tests de la méthode aask (asynchrone)."""

    @pytest.mark.asyncio
    async def test_aask_returns_response(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        response = await runner.aask("Async question")

        assert isinstance(response, LLMResponse)
        assert response.content == "Async fake response #1"

    @pytest.mark.asyncio
    async def test_aask_adds_to_history(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        initial_len = len(runner.history)
        await runner.aask("Async Q")

        assert len(runner.history) == initial_len + 2


class TestAgentRunnerReset:
    """Tests de la méthode reset."""

    def test_reset_keeps_system_prompt(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        runner.ask("Q1")
        runner.ask("Q2")

        assert len(runner.history) > 1
        runner.reset()

        assert len(runner.history) == 1
        assert runner.history[0].role == MessageRole.SYSTEM

    def test_reset_clears_conversation(self, runner_with_fake_client):
        runner, fake = runner_with_fake_client
        runner.ask("Q1")
        runner.reset()
        response = runner.ask("Q2 après reset")

        # Après reset + 1 ask : system + user + assistant = 3
        assert len(runner.history) == 3
        assert response.content == "Fake response #2"  # 2nd call total


class TestAgentRunnerRepr:
    """Tests du __repr__."""

    def test_repr(self, runner_with_fake_client):
        runner, _ = runner_with_fake_client
        r = repr(runner)
        assert "AgentRunner" in r
        assert "test-agent" in r


# ── Tests _resolve_provider ───────────────────────────────────────────────────


class TestResolveProvider:
    """Tests de la résolution du provider."""

    def test_openai_from_provider_id(self, sample_agent: Agent):
        from agents.shared.runner import _resolve_provider

        config = _resolve_provider(sample_agent, api_key="sk-test")
        assert config.provider_type == ProviderType.OPENAI

    def test_anthropic_from_provider_id(self):
        from agents.shared.runner import _resolve_provider

        agent = Agent(
            name="Anthro",
            slug="anthro",
            role=AgentRole.ASSISTANT,
            provider_id="default-anthropic",
        )
        config = _resolve_provider(agent, api_key="sk-ant-test")
        assert config.provider_type == ProviderType.ANTHROPIC

    def test_model_override(self, sample_agent: Agent):
        from agents.shared.runner import _resolve_provider

        config = _resolve_provider(sample_agent, api_key="sk-test", model="gpt-4o-mini")
        assert config.default_model == "gpt-4o-mini"

    def test_provider_type_override(self, sample_agent: Agent):
        from agents.shared.runner import _resolve_provider

        config = _resolve_provider(
            sample_agent,
            api_key="sk-test",
            provider_type=ProviderType.ANTHROPIC,
        )
        assert config.provider_type == ProviderType.ANTHROPIC

    def test_no_api_key_raises(self, sample_agent: Agent):
        from agents.shared.runner import AgentRunnerError, _resolve_provider

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(AgentRunnerError, match="Aucune clé API"):
                _resolve_provider(sample_agent)

    def test_ollama_no_api_key_ok(self):
        from agents.shared.runner import _resolve_provider

        agent = Agent(
            name="Local",
            slug="local",
            role=AgentRole.ASSISTANT,
            provider_id="default-ollama",
        )
        with patch.dict("os.environ", {}, clear=True):
            config = _resolve_provider(agent)
        assert config.provider_type == ProviderType.OLLAMA

    def test_env_api_key_resolution(self, sample_agent: Agent):
        from agents.shared.runner import _resolve_provider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-env-key"}, clear=True):
            config = _resolve_provider(sample_agent)
        assert config.get_api_key_value() == "sk-env-key"

    def test_settings_from_agent_config(self, sample_agent: Agent):
        from agents.shared.runner import _resolve_provider

        config = _resolve_provider(sample_agent, api_key="sk-test")
        assert config.settings.temperature == 0.5
        assert config.settings.max_tokens == 100


# ── Tests avec agents concrets du catalogue ───────────────────────────────────


class TestRunnerWithCatalogAgents:
    """Vérifie que le runner peut se construire avec chaque agent du catalogue."""

    @pytest.fixture(
        params=[
            "agents.assistants.general_assistant:general_assistant",
            "agents.researchers.doc_researcher:doc_researcher",
            "agents.coders.code_reviewer:code_reviewer",
            "agents.analysts.data_analyst:data_analyst",
            "agents.orchestrators.pipeline_planner:pipeline_planner",
        ]
    )
    def catalog_agent(self, request) -> Agent:
        import importlib

        module_path, attr_name = request.param.split(":")
        mod = importlib.import_module(module_path)
        return getattr(mod, attr_name)

    def test_runner_builds_with_catalog_agent(self, catalog_agent: Agent):
        from agents.shared.runner import AgentRunner

        with patch("agents.shared.runner.get_llm_client") as mock_factory:
            mock_factory.return_value = FakeLLMClient(None)
            runner = AgentRunner(catalog_agent, api_key="sk-test", persist=False)

        assert runner.agent is catalog_agent
        assert len(runner.history) >= 1  # system prompt

    def test_runner_ask_with_catalog_agent(self, catalog_agent: Agent):
        from agents.shared.runner import AgentRunner

        with patch("agents.shared.runner.get_llm_client") as mock_factory:
            fake = FakeLLMClient(None)
            mock_factory.return_value = fake
            runner = AgentRunner(catalog_agent, api_key="sk-test", persist=False)
            runner._client = fake

        response = runner.ask("Test question")
        assert response.content.startswith("Fake response")
