# filepath: /Users/awf/Projects/software-engineering/python-packages/pyworkflow-engine/agents/shared/runner.py
"""
agents.shared.runner — Exécution réelle d'un agent du catalogue.

Pont entre les définitions déclaratives (agents/*.py) et la couche LLM
concrète (adapters/ai/llm).  Deux modes :

  1. **One-shot** : ``runner.ask("Résume ce texte.")``
  2. **Interactif (REPL)** : ``runner.repl()``

Le runner :
  - Résout le provider via OPENAI_API_KEY / ``LLMProviderConfig``
  - Injecte le ``system_prompt`` de l'agent
  - Maintient un historique de conversation en mémoire
  - Persiste chaque message dans ``ai_conversations`` / ``ai_messages`` via
    ``SQLiteAIStorage`` (ADR-020 — couche de persistence unifiée)
  - Extrait et injecte les mémoires (``ai_memories``) via ``MemoryExtractor``
  - Affiche les métriques (tokens, temps de réponse)

Architecture : ADR-019 (Phase 4 — runtime), ADR-020 (Phase 1b — convergence)

Usage::

    from agents.assistants.general_assistant import general_assistant
    from agents.shared.runner import AgentRunner

    runner = AgentRunner(general_assistant)
    response = runner.ask("Bonjour, qui es-tu ?")
    print(response.content)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from pyworkflow_engine.adapters.ai.llm.factory import get_llm_client
from pyworkflow_engine.logging import get_logger
from pyworkflow_engine.models.ai.agent import Agent
from pyworkflow_engine.models.ai.conversation import Conversation
from pyworkflow_engine.models.ai.message import Message
from pyworkflow_engine.models.ai.provider import LLMProviderConfig, ProviderSettings
from pyworkflow_engine.models.ai.types import (
    ConversationStatus,
    MessageRole,
    ProviderType,
)
from pyworkflow_engine.ports.ai.llm import BaseLLMClient, LLMRequest, LLMResponse

_log = get_logger("agents.runner")

# Longueur max des contenus de messages dans les extras de log
_LOG_CONTENT_MAX = 500
_LOG_SYSTEM_MAX = 200

# ── Résolution du chemin DB ──────────────────────────────────────────────────

_DEFAULT_DB = "workflow.db"


def _resolve_db_path() -> Path:
    """Retourne le chemin absolu du fichier SQLite.

    Priorité :
      1. Variable d'environnement ``PYWORKFLOW_DB``
      2. ``./workflow.db`` relatif au répertoire de travail courant
    """
    raw = os.environ.get("PYWORKFLOW_DB", _DEFAULT_DB)
    return Path(raw).expanduser().resolve()


def _trunc(text: str | None, max_len: int = _LOG_CONTENT_MAX) -> str | None:
    """Tronque un texte pour les extras de log — ajoute '…' si coupé."""
    if text is None:
        return None
    return text if len(text) <= max_len else text[:max_len] + "…"


def _history_snapshot(
    history: list[Any], content_max: int = 120
) -> list[dict[str, str]]:
    """Construit un snapshot compact de l'historique pour les extras de log.

    Retourne une liste de dicts ``{role, content}`` avec contenu tronqué,
    en excluant le system prompt (premier message SYSTEM).
    """
    return [
        {
            "role": m.role.value,
            "content": _trunc(m.content, content_max) or "",
        }
        for m in history
        if m.role.value != "system"
    ]


# ── Helpers ──────────────────────────────────────────────────────────────


_PROVIDER_ENV_MAP: dict[str, tuple[ProviderType, str]] = {
    "OPENAI_API_KEY": (ProviderType.OPENAI, "gpt-4o"),
    "PYWORKFLOW_AI_OPENAI_API_KEY": (ProviderType.OPENAI, "gpt-4o"),
    "ANTHROPIC_API_KEY": (ProviderType.ANTHROPIC, "claude-3-5-sonnet-latest"),
    "PYWORKFLOW_AI_ANTHROPIC_API_KEY": (
        ProviderType.ANTHROPIC,
        "claude-3-5-sonnet-latest",
    ),
    "GROQ_API_KEY": (ProviderType.GROQ, "llama-3.1-70b-versatile"),
}


class AgentRunnerError(Exception):
    """Erreur lors de l'exécution d'un agent."""


def _resolve_provider(
    agent: Agent,
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider_type: ProviderType | None = None,
) -> LLMProviderConfig:
    """Construit un ``LLMProviderConfig`` à partir de l'agent et de l'environnement.

    Ordre de résolution de la clé API :
      1. Paramètre ``api_key`` explicite
      2. Variable d'environnement ``OPENAI_API_KEY`` (ou équivalent)
      3. ``PYWORKFLOW_AI_OPENAI_API_KEY``

    Raises:
        AgentRunnerError: Si aucune clé API n'est trouvée.
    """
    # Déterminer le provider type
    ptype = provider_type
    default_model = model or agent.model or "gpt-4o"

    if ptype is None:
        # Essayer de déduire depuis provider_id de l'agent
        pid = agent.provider_id.lower()
        if "openai" in pid:
            ptype = ProviderType.OPENAI
        elif "anthropic" in pid:
            ptype = ProviderType.ANTHROPIC
        elif "groq" in pid:
            ptype = ProviderType.GROQ
        elif "ollama" in pid:
            ptype = ProviderType.OLLAMA
        elif "gemini" in pid:
            ptype = ProviderType.GEMINI
        else:
            ptype = ProviderType.OPENAI  # fallback

    # Résoudre la clé API
    resolved_key = api_key
    if not resolved_key:
        for env_var, (env_ptype, env_model) in _PROVIDER_ENV_MAP.items():
            if env_ptype == ptype:
                resolved_key = os.environ.get(env_var)
                if resolved_key:
                    if not model and not agent.model:
                        default_model = env_model
                    break

    # Ollama n'a pas besoin de clé API
    if not resolved_key and ptype != ProviderType.OLLAMA:
        raise AgentRunnerError(
            f"Aucune clé API trouvée pour le provider '{ptype.value}'. "
            f"Définissez la variable d'environnement appropriée "
            f"(ex: OPENAI_API_KEY) ou passez api_key= au runner."
        )

    # Construire le ProviderSettings depuis l'AgentConfig
    agent_temp = agent.config.temperature
    settings = ProviderSettings(
        temperature=agent_temp if agent_temp is not None else 0.7,
        max_tokens=agent.config.max_tokens_per_response,
        max_retries=agent.config.max_retries,
    )

    return LLMProviderConfig(
        name=f"runner-{agent.slug}-{ptype.value}",
        provider_type=ptype,
        default_model=default_model,
        api_key=SecretStr(resolved_key) if resolved_key else None,
        settings=settings,
    )


# ── Storage helpers ──────────────────────────────────────────────────────


def _get_storage() -> Any:
    """Instancie un ``SQLiteAIStorage`` pointant vers workflow.db.

    Retourne ``None`` si l'import échoue ou si le fichier n'est pas accessible.
    """
    try:
        from pyworkflow_engine.adapters.ai.storage.sqlite import SQLiteAIStorage

        db_path = _resolve_db_path()
        return SQLiteAIStorage(db_path)
    except Exception as exc:  # noqa: BLE001
        _log.debug("SQLiteAIStorage non disponible : %s", exc)
        return None


# ── AgentRunner ──────────────────────────────────────────────────────────


class AgentRunner:
    """Exécute un agent du catalogue contre un vrai LLM.

    Persistence unifiée via ``SQLiteAIStorage`` (tables ``ai_conversations``,
    ``ai_messages``, ``ai_memories``).

    Args:
        agent: Instance ``Agent`` du catalogue (ex: ``general_assistant``).
        api_key: Clé API explicite (sinon → environnement).
        model: Override du modèle LLM.
        provider_type: Override du type de provider.
        verbose: Affiche les métriques après chaque réponse.
        persist: Active la persistence dans workflow.db.
        triggered_by: Source du déclenchement (cli, handoff, pipeline…).

    Usage::

        runner = AgentRunner(general_assistant)
        resp = runner.ask("Dis-moi une blague")
        print(resp.content)
    """

    def __init__(
        self,
        agent: Agent,
        *,
        api_key: str | None = None,
        model: str | None = None,
        provider_type: ProviderType | None = None,
        verbose: bool = False,
        persist: bool = True,
        triggered_by: str = "cli",
    ) -> None:
        self.agent = agent
        self.verbose = verbose
        self._triggered_by = triggered_by
        self._provider_config = _resolve_provider(
            agent,
            api_key=api_key,
            model=model,
            provider_type=provider_type,
        )
        self._client: BaseLLMClient = get_llm_client(self._provider_config)
        self._history: list[Message] = []

        # ── Persistence unifiée (SQLiteAIStorage) ─────────────────────
        self._storage: Any | None = None
        self._memory_extractor: Any | None = None
        if persist:
            storage = _get_storage()
            if storage is not None:
                self._storage = storage
                self._sync_agent_to_storage()
                # MemoryExtractor (ADR-020 Phase 2b)
                try:
                    from pyworkflow_engine.engine.ai.memory_extractor import (
                        MemoryExtractor,
                    )

                    self._memory_extractor = MemoryExtractor(storage)
                except Exception as exc:  # noqa: BLE001
                    _log.debug("MemoryExtractor non disponible : %s", exc)

        # ── Conversation / session ─────────────────────────────────────
        self._conversation_id: str | None = None
        self._mode: str = "one-shot"  # "one-shot" ou "chat"
        self._turn: int = 0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_tokens: int = 0
        self._total_response_time_ms: float = 0.0

        # Ajouter le system prompt comme premier message
        if agent.system_prompt:
            self._history.append(
                Message(
                    conversation_id="runner",
                    role=MessageRole.SYSTEM,
                    content=agent.system_prompt,
                )
            )

    # ── Storage sync ─────────────────────────────────────────────────

    def _sync_agent_to_storage(self) -> None:
        """S'assure que l'agent et son provider existent dans le storage.

        Effectue un upsert par slug pour que ``ai_agents`` et ``ai_providers``
        contiennent les entrées nécessaires aux FK des conversations/messages.
        """
        if not self._storage:
            return
        try:
            # Upsert provider
            existing_provider = self._storage.get_provider(
                self._provider_config.id
            )
            if not existing_provider:
                existing_provider = self._storage.get_provider_by_name(
                    self._provider_config.name
                )
            if not existing_provider:
                self._storage.save_provider(self._provider_config)

            # Upsert agent
            existing_agent = self._storage.get_agent_by_slug(self.agent.slug)
            if not existing_agent:
                self._storage.save_agent(self.agent)
            else:
                # Keep the persisted agent's ID so FK references stay consistent
                if self.agent.id != existing_agent.id:
                    self.agent = self.agent.model_copy(
                        update={"id": existing_agent.id}
                    )
        except Exception as exc:  # noqa: BLE001
            _log.debug("Erreur sync agent/provider dans storage : %s", exc)

    # ── Conversation management ──────────────────────────────────────

    def _ensure_conversation(self) -> str | None:
        """Crée une ``Conversation`` dans ``ai_conversations`` si nécessaire.

        Retourne le ``conversation_id`` ou ``None`` si pas de storage.
        """
        if not self._storage:
            return None
        if self._conversation_id:
            return self._conversation_id

        try:
            conv = Conversation(
                agent_id=self.agent.id,
                title=f"{self._mode} — {self.agent.name}",
                metadata={
                    "mode": self._mode,
                    "model": self.model,
                    "provider": self._provider_config.provider_type.value,
                    "triggered_by": self._triggered_by,
                },
            )
            conv = self._storage.save_conversation(conv)
            self._conversation_id = conv.id
            _log.info(
                "Conversation créée : agent=%s conv_id=%s mode=%s",
                self.agent.slug,
                conv.id,
                self._mode,
                extra={
                    "agent_id": self.agent.id,
                    "agent_slug": self.agent.slug,
                    "agent_name": self.agent.name,
                    "conversation_id": conv.id,
                    "model": self.model,
                    "provider": self._provider_config.provider_type.value,
                    "mode": self._mode,
                    "triggered_by": self._triggered_by,
                    "system_prompt": _trunc(
                        self.agent.system_prompt, _LOG_SYSTEM_MAX
                    ),
                    "system_prompt_length": (
                        len(self.agent.system_prompt)
                        if self.agent.system_prompt
                        else 0
                    ),
                    "event": "conversation_start",
                },
            )
            return conv.id
        except Exception as exc:  # noqa: BLE001
            _log.warning("Impossible de créer la conversation : %s", exc)
            return None

    # ── Memory injection (ADR-020 Phase 2a) ──────────────────────────

    def _inject_memories_into_history(self) -> None:
        """Charge les mémoires depuis ``ai_memories`` et les injecte dans l'historique.

        Insère un message SYSTEM juste après le system prompt (position 1) contenant
        les mémoires les plus pertinentes de l'agent. Appelé une seule fois au premier
        tour si ``enable_memory`` est activé.
        """
        if not self._storage or not self.agent.config.enable_memory:
            return
        if self._turn > 1:
            return  # Already injected at turn 1

        try:
            memories = self._storage.list_memories(self.agent.id)
            active = [m for m in memories if not m.is_expired]
            if not active:
                return

            top = sorted(
                active, key=lambda m: m.relevance_score, reverse=True
            )[:20]
            block = "\n".join(
                f"- [{m.memory_type.value}] {m.key}: {m.content}" for m in top
            )
            memory_msg = Message(
                conversation_id=self._conversation_id or "runner",
                role=MessageRole.SYSTEM,
                content=(
                    "## Relevant memories from previous interactions\n"
                    f"{block}\n\n"
                    "Use these to personalize your responses."
                ),
            )
            # Insert after the system prompt (index 1)
            insert_pos = 1 if (
                self._history and self._history[0].role == MessageRole.SYSTEM
            ) else 0
            self._history.insert(insert_pos, memory_msg)

            _log.info(
                "Memories injected : agent=%s count=%d",
                self.agent.slug,
                len(top),
                extra={
                    "agent_slug": self.agent.slug,
                    "memory_count": len(top),
                    "event": "memories_injected",
                },
            )
        except Exception as exc:  # noqa: BLE001
            _log.debug("Erreur injection mémoires : %s", exc)

    # ── Properties ───────────────────────────────────────────────────

    @property
    def client(self) -> BaseLLMClient:
        """Client LLM sous-jacent."""
        return self._client

    @property
    def history(self) -> list[Message]:
        """Historique de conversation (lecture seule)."""
        return list(self._history)

    @property
    def model(self) -> str:
        """Modèle LLM utilisé."""
        return self._provider_config.default_model

    @property
    def conversation_id(self) -> str | None:
        """ID de la conversation en cours (ou None)."""
        return self._conversation_id

    @property
    def storage(self) -> Any | None:
        """Backend de persistence (SQLiteAIStorage ou None)."""
        return self._storage

    # ── ask ───────────────────────────────────────────────────────────

    def ask(self, message: str, **kwargs: Any) -> LLMResponse:
        """Envoie un message et retourne la réponse LLM.

        Le message est ajouté à l'historique, la réponse aussi.
        La conversation est persistée dans ``ai_conversations`` / ``ai_messages``
        via ``SQLiteAIStorage``.

        Args:
            message: Message utilisateur.
            **kwargs: Options supplémentaires pour le LLM (temperature, max_tokens…).

        Returns:
            ``LLMResponse`` avec content, usage, response_time_ms, etc.

        Raises:
            AgentRunnerError: En cas d'erreur LLM.
        """
        # Ensure conversation exists in storage
        conv_id = self._ensure_conversation()

        # Incrémenter le numéro de tour
        self._turn += 1
        turn = self._turn

        # Inject memories at first turn (ADR-020 Phase 2a)
        self._inject_memories_into_history()

        # Ajouter le message utilisateur à l'historique
        user_msg = Message(
            conversation_id=conv_id or "runner",
            role=MessageRole.USER,
            content=message,
        )
        self._history.append(user_msg)

        # Persister le message utilisateur
        if self._storage and conv_id:
            try:
                self._storage.save_message(user_msg)
            except Exception as exc:  # noqa: BLE001
                _log.debug("Erreur persistence message user : %s", exc)

        _log.info(
            "Agent user message : agent=%s turn=%d chars=%d",
            self.agent.slug,
            turn,
            len(message),
            extra={
                "agent_id": self.agent.id,
                "conversation_id": conv_id,
                "agent_slug": self.agent.slug,
                "model": self.model,
                "turn": turn,
                "role": "user",
                "content": _trunc(message),
                "message_length": len(message),
                "mode": self._mode,
                "event": "user_message",
            },
        )

        # Construire la requête
        request = LLMRequest(
            messages=self._history,
            temperature=kwargs.get("temperature", self.agent.config.temperature),
            max_tokens=kwargs.get(
                "max_tokens", self.agent.config.max_tokens_per_response
            ),
        )

        try:
            response = self._client.complete(request)
        except Exception as exc:
            error_msg = f"Erreur LLM ({self.agent.slug}): {exc}"
            _log.error(
                "Agent LLM error : agent=%s turn=%d : %s",
                self.agent.slug,
                turn,
                exc,
                extra={
                    "agent_id": self.agent.id,
                    "conversation_id": conv_id,
                    "agent_slug": self.agent.slug,
                    "model": self.model,
                    "turn": turn,
                    "mode": self._mode,
                    "event": "llm_error",
                    "error": str(exc),
                },
            )
            raise AgentRunnerError(error_msg) from exc

        # Mettre à jour les compteurs de session
        if response.usage:
            self._total_prompt_tokens += response.usage.prompt_tokens or 0
            self._total_completion_tokens += response.usage.completion_tokens or 0
            self._total_tokens += response.usage.total_tokens or 0
        if response.response_time_ms:
            self._total_response_time_ms += response.response_time_ms

        # Ajouter la réponse à l'historique
        assistant_msg = Message(
            conversation_id=conv_id or "runner",
            role=MessageRole.ASSISTANT,
            content=response.content,
            metadata={
                "model": response.model,
                "total_tokens": (
                    response.usage.total_tokens if response.usage else None
                ),
                "response_time_ms": response.response_time_ms,
            },
        )
        self._history.append(assistant_msg)

        # Persister le message assistant
        if self._storage and conv_id:
            try:
                self._storage.save_message(assistant_msg)
            except Exception as exc:  # noqa: BLE001
                _log.debug("Erreur persistence message assistant : %s", exc)

        # ── Memory extraction best-effort (ADR-020 Phase 2c) ──
        if (
            self._memory_extractor
            and self.agent.config.enable_memory
            and response.content
        ):
            try:
                self._memory_extractor.extract_and_save(
                    agent_id=self.agent.id,
                    user_message=message,
                    assistant_message=response.content,
                    llm_client=self._client,
                )
            except Exception:  # noqa: BLE001
                pass  # best-effort — ne bloque jamais le chat

        _log.info(
            "Agent response : agent=%s turn=%d tokens=%s rt=%.0fms",
            self.agent.slug,
            turn,
            response.usage.total_tokens if response.usage else "?",
            response.response_time_ms or 0,
            extra={
                "agent_id": self.agent.id,
                "conversation_id": conv_id,
                "agent_slug": self.agent.slug,
                "model": response.model,
                "turn": turn,
                "role": "assistant",
                "content": _trunc(response.content),
                "history_snapshot": _history_snapshot(self._history),
                "prompt_tokens": (
                    response.usage.prompt_tokens if response.usage else None
                ),
                "completion_tokens": (
                    response.usage.completion_tokens if response.usage else None
                ),
                "total_tokens": (
                    response.usage.total_tokens if response.usage else None
                ),
                "response_time_ms": round(response.response_time_ms or 0),
                "finish_reason": response.finish_reason,
                "temperature": self.agent.config.temperature,
                "mode": self._mode,
                "event": "llm_response",
            },
        )

        return response

    # ── aask (async) ─────────────────────────────────────────────────

    async def aask(self, message: str, **kwargs: Any) -> LLMResponse:
        """Version asynchrone de ``ask``."""
        conv_id = self._ensure_conversation()

        self._turn += 1
        turn = self._turn

        self._inject_memories_into_history()

        user_msg = Message(
            conversation_id=conv_id or "runner",
            role=MessageRole.USER,
            content=message,
        )
        self._history.append(user_msg)

        if self._storage and conv_id:
            try:
                self._storage.save_message(user_msg)
            except Exception as exc:  # noqa: BLE001
                _log.debug("Erreur persistence message user (async) : %s", exc)

        _log.info(
            "Agent user message (async) : agent=%s turn=%d chars=%d",
            self.agent.slug,
            turn,
            len(message),
            extra={
                "agent_id": self.agent.id,
                "conversation_id": conv_id,
                "agent_slug": self.agent.slug,
                "model": self.model,
                "turn": turn,
                "role": "user",
                "content": _trunc(message),
                "message_length": len(message),
                "mode": self._mode,
                "event": "user_message",
            },
        )

        request = LLMRequest(
            messages=self._history,
            temperature=kwargs.get("temperature", self.agent.config.temperature),
            max_tokens=kwargs.get(
                "max_tokens", self.agent.config.max_tokens_per_response
            ),
        )

        try:
            response = await self._client.acomplete(request)
        except Exception as exc:
            _log.error(
                "Agent LLM async error : agent=%s : %s",
                self.agent.slug,
                exc,
                extra={
                    "agent_id": self.agent.id,
                    "conversation_id": conv_id,
                    "agent_slug": self.agent.slug,
                    "model": self.model,
                    "turn": turn,
                    "mode": self._mode,
                    "event": "llm_error",
                    "error": str(exc),
                },
            )
            raise AgentRunnerError(
                f"Erreur LLM async ({self.agent.slug}): {exc}"
            ) from exc

        if response.usage:
            self._total_prompt_tokens += response.usage.prompt_tokens or 0
            self._total_completion_tokens += response.usage.completion_tokens or 0
            self._total_tokens += response.usage.total_tokens or 0
        if response.response_time_ms:
            self._total_response_time_ms += response.response_time_ms

        assistant_msg = Message(
            conversation_id=conv_id or "runner",
            role=MessageRole.ASSISTANT,
            content=response.content,
            metadata={
                "model": response.model,
                "total_tokens": (
                    response.usage.total_tokens if response.usage else None
                ),
                "response_time_ms": response.response_time_ms,
            },
        )
        self._history.append(assistant_msg)

        if self._storage and conv_id:
            try:
                self._storage.save_message(assistant_msg)
            except Exception as exc:  # noqa: BLE001
                _log.debug("Erreur persistence message assistant (async) : %s", exc)

        # Memory extraction (async best-effort)
        if (
            self._memory_extractor
            and self.agent.config.enable_memory
            and response.content
        ):
            try:
                await self._memory_extractor.aextract_and_save(
                    agent_id=self.agent.id,
                    user_message=message,
                    assistant_message=response.content,
                    llm_client=self._client,
                )
            except Exception:  # noqa: BLE001
                pass

        _log.info(
            "Agent response (async) : agent=%s turn=%d tokens=%s rt=%.0fms",
            self.agent.slug,
            turn,
            response.usage.total_tokens if response.usage else "?",
            response.response_time_ms or 0,
            extra={
                "agent_id": self.agent.id,
                "conversation_id": conv_id,
                "agent_slug": self.agent.slug,
                "model": response.model,
                "turn": turn,
                "role": "assistant",
                "content": _trunc(response.content),
                "history_snapshot": _history_snapshot(self._history),
                "prompt_tokens": (
                    response.usage.prompt_tokens if response.usage else None
                ),
                "completion_tokens": (
                    response.usage.completion_tokens if response.usage else None
                ),
                "total_tokens": (
                    response.usage.total_tokens if response.usage else None
                ),
                "response_time_ms": round(response.response_time_ms or 0),
                "finish_reason": response.finish_reason,
                "temperature": self.agent.config.temperature,
                "mode": self._mode,
                "event": "llm_response",
            },
        )

        return response

    # ── finish / reset / close ───────────────────────────────────────

    def finish(self, *, status: str = "success", error: str | None = None) -> None:
        """Clôture la conversation en cours.

        Met à jour la ``Conversation`` avec les métriques cumulées et le statut.

        Args:
            status: ``"success"`` ou ``"error"``.
            error:  Message d'erreur si status == ``"error"``.
        """
        if not self._storage or not self._conversation_id:
            return
        try:
            conv = self._storage.get_conversation(self._conversation_id)
            if conv:
                msg_count = sum(
                    1
                    for m in self._history
                    if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
                )
                conv.message_count = msg_count
                conv.total_tokens = self._total_tokens
                conv.updated_at = datetime.now(UTC)
                conv.status = (
                    ConversationStatus.COMPLETED
                    if status == "success"
                    else ConversationStatus.ARCHIVED
                )
                conv.metadata = {
                    **conv.metadata,
                    "status": status,
                    "total_prompt_tokens": self._total_prompt_tokens,
                    "total_completion_tokens": self._total_completion_tokens,
                    "total_response_time_ms": round(self._total_response_time_ms),
                    **({"error": error} if error else {}),
                }
                self._storage.save_conversation(conv)

            _log.info(
                "Conversation terminée : agent=%s status=%s msgs=%d tokens=%d conv_id=%s",
                self.agent.slug,
                status,
                self._turn * 2,
                self._total_tokens,
                self._conversation_id,
                extra={
                    "agent_id": self.agent.id,
                    "conversation_id": self._conversation_id,
                    "agent_slug": self.agent.slug,
                    "agent_name": self.agent.name,
                    "model": self.model,
                    "provider": self._provider_config.provider_type.value,
                    "status": status,
                    "total_prompt_tokens": self._total_prompt_tokens,
                    "total_completion_tokens": self._total_completion_tokens,
                    "total_tokens": self._total_tokens,
                    "total_response_time_ms": round(self._total_response_time_ms),
                    "triggered_by": self._triggered_by,
                    "mode": self._mode,
                    "event": "conversation_finish",
                    **({"error": error} if error else {}),
                },
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("Impossible de clôturer la conversation : %s", exc)
        finally:
            self._conversation_id = None  # avoid double-close

    def reset(self) -> None:
        """Réinitialise l'historique (conserve le system prompt).

        Si une conversation est en cours, la clôture avec ``status="success"``
        avant de réinitialiser, de sorte que chaque conversation soit une session
        distincte dans ``ai_conversations``.
        """
        self.finish()
        system = [m for m in self._history if m.role == MessageRole.SYSTEM]
        # Keep only the first system prompt (not memory injection)
        self._history = system[:1]
        self._mode = "one-shot"
        self._turn = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_tokens = 0
        self._total_response_time_ms = 0.0

    def close(self) -> None:
        """Ferme le runner et libère les ressources (storage connection)."""
        self.finish()
        if self._storage and hasattr(self._storage, "close"):
            try:
                self._storage.close()
            except Exception:  # noqa: BLE001
                pass

    # ── REPL ─────────────────────────────────────────────────────────

    def repl(self) -> None:
        """Lance une boucle interactive (REPL) dans le terminal.

        Commandes spéciales :
          - ``/quit`` ou ``/exit`` : Quitter
          - ``/reset`` : Réinitialiser la conversation
          - ``/history`` : Afficher l'historique
          - ``/info`` : Informations sur l'agent
          - ``/memories`` : Afficher les mémoires persistées de l'agent
        """
        try:
            from rich.console import Console
            from rich.markdown import Markdown
            from rich.panel import Panel

            console = Console()
            use_rich = True
        except ImportError:
            console = None  # type: ignore[assignment]
            use_rich = False

        def _print(text: str) -> None:
            if use_rich:
                console.print(text)
            else:
                print(text)

        def _print_md(text: str) -> None:
            if use_rich:
                console.print(Markdown(text))
            else:
                print(text)

        # Set mode to "chat" for REPL sessions
        self._mode = "chat"

        # Ensure conversation is created at REPL entry
        self._ensure_conversation()

        # Banner
        if use_rich:
            console.print(
                Panel(
                    f"[bold]{self.agent.name}[/bold]\n"
                    f"[dim]{self.agent.description}[/dim]\n\n"
                    f"Modèle: [cyan]{self.model}[/cyan]  |  "
                    f"Rôle: [green]{self.agent.role.value}[/green]",
                    title="🤖 Agent Runner — REPL",
                    subtitle="Tapez /quit pour quitter, /help pour l'aide",
                    expand=False,
                )
            )
        else:
            print(f"\n🤖 {self.agent.name} ({self.model})")
            print(f"   {self.agent.description}")
            print("   Tapez /quit pour quitter\n")

        if self.agent.welcome_message:
            _print(
                f"\n[bold green]🤖[/bold green] {self.agent.welcome_message}\n"
                if use_rich
                else f"\n🤖 {self.agent.welcome_message}\n"
            )

        _repl_error: str | None = None
        try:
            while True:
                try:
                    user_input = input("👤 > ").strip()
                except (EOFError, KeyboardInterrupt):
                    _print("\n[dim]Au revoir ![/dim]" if use_rich else "\nAu revoir !")
                    break

                if not user_input:
                    continue

                # Commandes spéciales
                if user_input.startswith("/"):
                    cmd = user_input.lower()
                    if cmd in ("/quit", "/exit", "/q"):
                        _print("[dim]Au revoir ![/dim]" if use_rich else "Au revoir !")
                        break
                    if cmd == "/reset":
                        self.reset()
                        self._mode = "chat"
                        self._ensure_conversation()
                        _print(
                            "[yellow]🔄 Conversation réinitialisée.[/yellow]"
                            if use_rich
                            else "🔄 Conversation réinitialisée."
                        )
                        continue
                    if cmd == "/history":
                        for msg in self._history:
                            role = msg.role.value.upper()
                            content = (
                                msg.content[:100] + "…"
                                if len(msg.content) > 100
                                else msg.content
                            )
                            _print(f"  [{role}] {content}")
                        continue
                    if cmd in ("/info", "/agent"):
                        _print(f"  Agent : {self.agent.name} ({self.agent.slug})")
                        _print(f"  Rôle  : {self.agent.role.value}")
                        _print(f"  Modèle: {self.model}")
                        _print(f"  Temp. : {self.agent.config.temperature}")
                        _print(f"  Msgs  : {len(self._history)}")
                        _print(f"  Conv. : {self._conversation_id or '—'}")
                        _print(
                            f"  Memory: {'✅' if self.agent.config.enable_memory else '❌'}"
                        )
                        continue
                    if cmd == "/memories":
                        if self._storage and self.agent.config.enable_memory:
                            try:
                                memories = self._storage.list_memories(self.agent.id)
                                active = [m for m in memories if not m.is_expired]
                                if active:
                                    _print(
                                        f"  🧠 {len(active)} mémoire(s) active(s) :"
                                    )
                                    for m in sorted(
                                        active,
                                        key=lambda x: x.relevance_score,
                                        reverse=True,
                                    ):
                                        _print(
                                            f"    [{m.memory_type.value}] {m.key}: "
                                            f"{m.content[:80]}"
                                            f"{'…' if len(m.content) > 80 else ''}"
                                            f" (score={m.relevance_score:.1f})"
                                        )
                                else:
                                    _print("  🧠 Aucune mémoire persistée.")
                            except Exception as exc:  # noqa: BLE001
                                _print(f"  ⚠️ Erreur lecture mémoires : {exc}")
                        else:
                            _print(
                                "  🧠 Mémoire désactivée pour cet agent."
                            )
                        continue
                    if cmd == "/help":
                        _print("  /quit     — Quitter")
                        _print("  /reset    — Réinitialiser la conversation")
                        _print("  /history  — Afficher l'historique")
                        _print("  /info     — Informations sur l'agent")
                        _print("  /memories — Afficher les mémoires persistées")
                        continue
                    _print(
                        f"[red]Commande inconnue: {user_input}[/red]"
                        if use_rich
                        else f"Commande inconnue: {user_input}"
                    )
                    continue

                # Appel LLM
                try:
                    if use_rich:
                        with console.status("[bold cyan]Réflexion…[/bold cyan]"):
                            response = self.ask(user_input)
                    else:
                        response = self.ask(user_input)
                except AgentRunnerError as exc:
                    _repl_error = str(exc)
                    _print(
                        f"[bold red]✗ Erreur :[/bold red] {exc}"
                        if use_rich
                        else f"✗ Erreur : {exc}"
                    )
                    continue

                # Afficher la réponse
                _print("")
                _print_md(response.content)

                # Métriques
                if self.verbose and response.usage:
                    u = response.usage
                    rt = (
                        f"{response.response_time_ms:.0f}ms"
                        if response.response_time_ms
                        else "—"
                    )
                    _print(
                        f"\n[dim]  ⚡ {u.total_tokens} tokens "
                        f"(prompt: {u.prompt_tokens}, completion: {u.completion_tokens}) "
                        f"— {rt}[/dim]"
                        if use_rich
                        else f"\n  ⚡ {u.total_tokens} tokens — {rt}"
                    )
                _print("")
        finally:
            # Clôturer la conversation à la sortie du REPL
            self.finish(
                status="error" if _repl_error else "success",
                error=_repl_error,
            )

    def __repr__(self) -> str:
        return (
            f"AgentRunner(agent={self.agent.slug!r}, "
            f"model={self.model!r}, "
            f"history={len(self._history)} msgs)"
        )
