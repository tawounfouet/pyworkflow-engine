"""
Tests unitaires — agents/ catalogue (ADR-019).

Vérifie :
- La structure du catalogue et du manifest
- Le chargement dynamique des agents via le loader
- La validité de chaque agent concret
- Les utilitaires partagés (configs, prompts, tool_sets)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.types import AgentRole

# ── Chemins ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]  # pyworkflow-engine/
AGENTS_DIR = ROOT / "agents"
MANIFEST_PATH = AGENTS_DIR / "manifest.yaml"


# ── Manifest ──────────────────────────────────────────────────────────────────


class TestManifest:
    """Vérifie la structure et la cohérence du manifest."""

    def test_manifest_exists(self):
        assert MANIFEST_PATH.exists(), f"Manifest introuvable : {MANIFEST_PATH}"

    def test_manifest_valid_yaml(self):
        raw = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        assert "agents" in raw

    def test_manifest_entries_have_required_fields(self):
        raw = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        required_fields = {"name", "module", "attr", "role", "description"}

        for i, entry in enumerate(raw["agents"]):
            missing = required_fields - set(entry.keys())
            assert not missing, (
                f"Entrée #{i} ({entry.get('name', '?')}) : "
                f"champs manquants : {missing}"
            )

    def test_manifest_slugs_unique(self):
        raw = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        slugs = [e["name"] for e in raw["agents"]]
        assert len(slugs) == len(set(slugs)), f"Slugs en doublon : {slugs}"

    def test_manifest_roles_valid(self):
        raw = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        valid_roles = {r.value for r in AgentRole}

        for entry in raw["agents"]:
            assert entry["role"] in valid_roles, (
                f"Rôle invalide pour {entry['name']}: {entry['role']!r}. "
                f"Valeurs acceptées : {valid_roles}"
            )


# ── Loader ────────────────────────────────────────────────────────────────────


class TestLoader:
    """Vérifie le chargement dynamique des agents."""

    def test_load_manifest(self):
        from agents.shared.loader import load_manifest

        entries = load_manifest(MANIFEST_PATH)
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_load_all_agents(self):
        from agents.shared.loader import load_all_agents

        agents = load_all_agents(MANIFEST_PATH)
        assert len(agents) > 0
        for agent in agents:
            assert isinstance(agent, Agent)

    def test_load_agent_by_slug(self):
        from agents.shared.loader import load_agent_by_slug

        agent = load_agent_by_slug("general-assistant", MANIFEST_PATH)
        assert agent.slug == "general-assistant"
        assert agent.role == AgentRole.ASSISTANT

    def test_load_agent_by_slug_not_found(self):
        from agents.shared.loader import AgentLoadError, load_agent_by_slug

        with pytest.raises(AgentLoadError, match="introuvable"):
            load_agent_by_slug("nonexistent-agent", MANIFEST_PATH)

    def test_load_manifest_file_not_found(self):
        from agents.shared.loader import load_manifest

        with pytest.raises(FileNotFoundError):
            load_manifest("/tmp/nonexistent_manifest.yaml")


# ── Agents concrets ──────────────────────────────────────────────────────────


class TestConcreteAgents:
    """Vérifie que chaque agent concret est bien formé."""

    @pytest.fixture(
        params=[
            (
                "agents.assistants.general_assistant",
                "general_assistant",
                AgentRole.ASSISTANT,
            ),
            (
                "agents.researchers.doc_researcher",
                "doc_researcher",
                AgentRole.RESEARCHER,
            ),
            ("agents.coders.code_reviewer", "code_reviewer", AgentRole.CODER),
            ("agents.analysts.data_analyst", "data_analyst", AgentRole.ANALYST),
            (
                "agents.orchestrators.pipeline_planner",
                "pipeline_planner",
                AgentRole.ORCHESTRATOR,
            ),
        ]
    )
    def agent_info(self, request):
        return request.param

    def _import_agent(self, module_path: str, attr: str) -> Agent:
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    def test_is_agent_instance(self, agent_info):
        module_path, attr, _ = agent_info
        agent = self._import_agent(module_path, attr)
        assert isinstance(agent, Agent)

    def test_has_valid_role(self, agent_info):
        module_path, attr, expected_role = agent_info
        agent = self._import_agent(module_path, attr)
        assert agent.role == expected_role

    def test_has_name_and_slug(self, agent_info):
        module_path, attr, _ = agent_info
        agent = self._import_agent(module_path, attr)
        assert agent.name, f"Agent {attr} has no name"
        assert agent.slug, f"Agent {attr} has no slug"

    def test_has_system_prompt(self, agent_info):
        module_path, attr, _ = agent_info
        agent = self._import_agent(module_path, attr)
        assert agent.system_prompt, f"Agent {attr} has no system_prompt"

    def test_has_provider_id(self, agent_info):
        module_path, attr, _ = agent_info
        agent = self._import_agent(module_path, attr)
        assert agent.provider_id, f"Agent {attr} has no provider_id"

    def test_has_valid_config(self, agent_info):
        module_path, attr, _ = agent_info
        agent = self._import_agent(module_path, attr)
        assert isinstance(agent.config, AgentConfig)
        assert agent.config.max_iterations >= 1
        assert agent.config.max_tokens_per_run >= 1

    def test_slug_matches_manifest(self, agent_info):
        """Vérifie que le slug de l'agent correspond à une entrée du manifest."""
        module_path, attr, _ = agent_info
        agent = self._import_agent(module_path, attr)

        raw = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest_slugs = [e["name"] for e in raw["agents"]]
        assert agent.slug in manifest_slugs, (
            f"Agent {attr} (slug={agent.slug!r}) "
            f"absent du manifest. Slugs existants : {manifest_slugs}"
        )


# ── Shared utilities ─────────────────────────────────────────────────────────


class TestSharedConfigs:
    """Vérifie les presets AgentConfig."""

    def test_all_presets_are_valid(self):
        from agents.shared.configs import (
            BALANCED,
            CODE,
            CREATIVE,
            MINIMAL,
            PRECISE,
            RAG_ENABLED,
        )

        for preset in [CREATIVE, PRECISE, BALANCED, RAG_ENABLED, CODE, MINIMAL]:
            assert isinstance(preset, AgentConfig)
            assert preset.max_iterations >= 1
            assert preset.max_tokens_per_run >= 1

    def test_creative_has_high_temperature(self):
        from agents.shared.configs import CREATIVE

        assert CREATIVE.temperature is not None
        assert CREATIVE.temperature > 1.0

    def test_precise_has_low_temperature(self):
        from agents.shared.configs import PRECISE

        assert PRECISE.temperature is not None
        assert PRECISE.temperature <= 0.2

    def test_code_has_zero_temperature(self):
        from agents.shared.configs import CODE

        assert CODE.temperature == 0.0

    def test_rag_enabled_has_rag(self):
        from agents.shared.configs import RAG_ENABLED

        assert RAG_ENABLED.enable_rag is True

    def test_minimal_has_no_tools(self):
        from agents.shared.configs import MINIMAL

        assert MINIMAL.enable_tools is False
        assert MINIMAL.enable_memory is False
        assert MINIMAL.max_iterations == 1


class TestSharedPrompts:
    """Vérifie les fragments de prompts."""

    def test_compose_basic(self):
        from agents.shared.prompts.base_prompts import compose

        result = compose("A", "B", "C")
        assert result == "A\nB\nC"

    def test_compose_with_separator(self):
        from agents.shared.prompts.base_prompts import compose

        result = compose("A", "B", separator=" | ")
        assert result == "A | B"

    def test_compose_skips_empty(self):
        from agents.shared.prompts.base_prompts import compose

        result = compose("A", "", "C")
        assert result == "A\nC"

    def test_compose_with_constants(self):
        from agents.shared.prompts.base_prompts import CONCISE, FRENCH, compose

        result = compose("Intro.", CONCISE, FRENCH)
        assert "Intro." in result
        assert "concise" in result
        assert "français" in result

    def test_all_fragments_are_strings(self):
        from agents.shared.prompts import base_prompts

        for name in dir(base_prompts):
            if name.isupper() and not name.startswith("_"):
                val = getattr(base_prompts, name)
                assert isinstance(val, str), f"{name} is not a string: {type(val)}"


class TestSharedToolSets:
    """Vérifie les groupes de tool_ids."""

    def test_all_tool_sets_are_lists(self):
        from agents.shared import tool_sets

        for name in dir(tool_sets):
            if name.isupper() and not name.startswith("_"):
                val = getattr(tool_sets, name)
                assert isinstance(val, list), f"{name} is not a list: {type(val)}"
                for item in val:
                    assert isinstance(
                        item, str
                    ), f"{name} contains non-string: {item!r}"

    def test_researcher_tools_includes_web_search(self):
        from agents.shared.tool_sets import RESEARCHER_TOOLS

        assert "web-search" in RESEARCHER_TOOLS

    def test_analyst_tools_includes_sql(self):
        from agents.shared.tool_sets import ANALYST_TOOLS

        assert "sql-query" in ANALYST_TOOLS
