"""
engine/ai/memory_extractor — Extraction LLM de faits mémorisables.

Après chaque échange agent ↔ utilisateur, analyse le contenu via LLM
pour identifier les faits saillants à retenir, et les persiste via
``BaseAIStorage.save_memory()``.

Design :
  - Best-effort : toute exception est avalée, le chat n'est pas bloqué
  - Upsert par clé : si le fait existe déjà, il est mis à jour
  - Désactivable via ``AgentConfig.enable_memory = False``

Architecture : ADR-020 (Phase 2b)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pyworkflow_engine.models.ai.memory import AgentMemory
from pyworkflow_engine.models.ai.message import Message, TokenUsage
from pyworkflow_engine.models.ai.types import MemoryType
from pyworkflow_engine.ports.ai.llm import BaseLLMClient, LLMRequest
from pyworkflow_engine.ports.ai.storage import BaseAIStorage

_log = logging.getLogger("pyworkflow.engine.ai.memory_extractor")

# Prompt pour guider l'extraction de faits mémorisables
_EXTRACTION_PROMPT = """\
You are a memory extraction assistant. Analyze the following conversation exchange \
and extract key facts worth remembering for future interactions.

User message: {user_message}
Assistant response: {assistant_response}

Extract facts as a JSON array. Each item must have:
  - "key": short snake_case identifier (e.g. "user_language", "preferred_format")
  - "content": the fact to remember (concise, < 200 chars)
  - "memory_type": one of "long_term", "episodic", "short_term"
  - "importance": float between 0.0 and 1.0

Return ONLY valid JSON. If nothing is worth remembering, return an empty array [].

Examples of things worth extracting:
  - User preferences (language, format, tone)
  - Stated constraints or requirements
  - Names, project context, domain knowledge shared
  - Explicit corrections made by the user

DO NOT extract generic conversation content or LLM boilerplate.
"""

_MEMORY_TYPE_MAP: dict[str, MemoryType] = {
    "long_term": MemoryType.LONG_TERM,
    "episodic": MemoryType.EPISODIC,
    "short_term": MemoryType.SHORT_TERM,
}


class MemoryExtractor:
    """Extrait et persiste les mémoires depuis les échanges agent-utilisateur.

    Args:
        storage: Backend de persistence IA.
        temperature: Température LLM pour l'extraction (faible = déterministe).
        max_facts: Nombre maximum de faits extraits par échange.

    Usage::

        extractor = MemoryExtractor(storage)
        extractor.extract_and_save(
            agent_id="agent-uuid",
            user_message="Please always respond in French.",
            assistant_message="Bien sûr, je répondrai en français.",
            llm_client=client,
        )
    """

    def __init__(
        self,
        storage: BaseAIStorage,
        *,
        temperature: float = 0.0,
        max_facts: int = 10,
    ) -> None:
        self._storage = storage
        self._temperature = temperature
        self._max_facts = max_facts

    def extract_and_save(
        self,
        agent_id: str,
        user_message: str,
        assistant_message: str,
        llm_client: BaseLLMClient,
    ) -> int:
        """Analyse un échange et persiste les faits mémorisables.

        Args:
            agent_id: ID de l'agent propriétaire des mémoires.
            user_message: Message de l'utilisateur.
            assistant_message: Réponse de l'assistant.
            llm_client: Client LLM pour l'extraction.

        Returns:
            Nombre de faits extraits et persistés.

        Note:
            Ne lève jamais d'exception — opération best-effort.
        """
        try:
            facts = self._call_llm(user_message, assistant_message, llm_client)
            return self._persist_facts(agent_id, facts)
        except Exception as exc:  # noqa: BLE001
            _log.debug(
                "MemoryExtractor best-effort failure for agent=%s : %s",
                agent_id,
                exc,
            )
            return 0

    async def aextract_and_save(
        self,
        agent_id: str,
        user_message: str,
        assistant_message: str,
        llm_client: BaseLLMClient,
    ) -> int:
        """Version asynchrone de ``extract_and_save``."""
        try:
            facts = await self._acall_llm(user_message, assistant_message, llm_client)
            return self._persist_facts(agent_id, facts)
        except Exception as exc:  # noqa: BLE001
            _log.debug(
                "MemoryExtractor async best-effort failure for agent=%s : %s",
                agent_id,
                exc,
            )
            return 0

    # ── Private helpers ──────────────────────────────────────────────

    def _build_extraction_request(
        self, user_message: str, assistant_message: str
    ) -> LLMRequest:
        from pyworkflow_engine.models.ai.message import Message as Msg
        from pyworkflow_engine.models.ai.types import MessageRole

        prompt = _EXTRACTION_PROMPT.format(
            user_message=user_message[:1000],
            assistant_response=assistant_message[:1000],
        )
        return LLMRequest(
            messages=[
                Msg(
                    conversation_id="memory-extraction",
                    role=MessageRole.USER,
                    content=prompt,
                )
            ],
            temperature=self._temperature,
            max_tokens=512,
        )

    def _call_llm(
        self,
        user_message: str,
        assistant_message: str,
        llm_client: BaseLLMClient,
    ) -> list[dict[str, Any]]:
        request = self._build_extraction_request(user_message, assistant_message)
        response = llm_client.complete(request)
        return self._parse_facts(response.content)

    async def _acall_llm(
        self,
        user_message: str,
        assistant_message: str,
        llm_client: BaseLLMClient,
    ) -> list[dict[str, Any]]:
        request = self._build_extraction_request(user_message, assistant_message)
        response = await llm_client.acomplete(request)
        return self._parse_facts(response.content)

    def _parse_facts(self, content: str) -> list[dict[str, Any]]:
        """Parse la réponse JSON du LLM en liste de faits."""
        content = content.strip()
        # Extraire le JSON si enveloppé dans un bloc markdown
        if "```" in content:
            start = content.find("[")
            end = content.rfind("]") + 1
            if start != -1 and end > start:
                content = content[start:end]
        try:
            facts = json.loads(content)
            if not isinstance(facts, list):
                return []
            return facts[: self._max_facts]
        except json.JSONDecodeError:
            _log.debug("MemoryExtractor: failed to parse LLM response as JSON")
            return []

    def _persist_facts(self, agent_id: str, facts: list[dict[str, Any]]) -> int:
        """Upsert les faits dans le storage (par agent_id + key)."""
        saved = 0
        now = datetime.now(UTC)
        for fact in facts:
            key = fact.get("key", "").strip()
            content = fact.get("content", "").strip()
            if not key or not content:
                continue

            raw_type = fact.get("memory_type", "long_term")
            mem_type = _MEMORY_TYPE_MAP.get(raw_type, MemoryType.LONG_TERM)
            importance = float(fact.get("importance", 0.8))
            importance = max(0.0, min(1.0, importance))

            # Upsert : chercher une mémoire existante avec la même clé
            existing = self._storage.get_memory(agent_id, key)
            if existing:
                # Mettre à jour le contenu et l'importance
                existing.content = content
                existing.memory_type = mem_type
                existing.relevance_score = importance
                existing.updated_at = now
                self._storage.save_memory(existing)
            else:
                memory = AgentMemory(
                    agent_id=agent_id,
                    key=key,
                    content=content,
                    memory_type=mem_type,
                    relevance_score=importance,
                )
                self._storage.save_memory(memory)
            saved += 1

        if saved:
            _log.debug(
                "MemoryExtractor: persisted %d fact(s) for agent=%s",
                saved,
                agent_id,
            )
        return saved
