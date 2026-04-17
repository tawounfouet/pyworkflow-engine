"""
engine/ai/agent_service — Service de haut niveau pour la gestion des agents IA.

Orchestration :
  - Création et configuration des agents
  - Conversations avec boucle tool-calling automatique
  - Gestion de la mémoire et du contexte

Usage::

    storage = InMemoryAIStorage()
    service = AgentService(storage)

    agent = service.create_agent(
        name="Assistant",
        provider_id="openai-gpt4",
        system_prompt="You are a helpful assistant.",
    )
    reply, conv = service.chat(agent.id, "Hello!")
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pyworkflow_engine.adapters.ai.llm.factory import get_llm_client
from pyworkflow_engine.adapters.ai.tools.executor import ToolExecutor
from pyworkflow_engine.adapters.ai.tools.registry import ToolRegistry
from pyworkflow_engine.engine.ai.memory_extractor import MemoryExtractor
from pyworkflow_engine.exceptions import (
    AgentError,
    AgentNotFoundError,
    ProviderNotFoundError,
)
from pyworkflow_engine.models.ai.agent import Agent, AgentConfig
from pyworkflow_engine.models.ai.conversation import Conversation
from pyworkflow_engine.models.ai.message import Message
from pyworkflow_engine.models.ai.types import AgentRole, MessageRole
from pyworkflow_engine.ports.ai.llm import LLMRequest
from pyworkflow_engine.ports.ai.storage import BaseAIStorage


class AgentService:
    """Service principal pour la gestion des agents IA."""

    def __init__(
        self,
        storage: BaseAIStorage,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.storage = storage
        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_executor = ToolExecutor(self.tool_registry)
        self.memory_extractor = MemoryExtractor(storage)

    # ── CRUD agents ────────────────────────────────────────────────────

    def create_agent(
        self,
        name: str,
        provider_id: str,
        system_prompt: str = "",
        role: AgentRole = AgentRole.ASSISTANT,
        config: AgentConfig | None = None,
        **kwargs: Any,
    ) -> Agent:
        """Crée un nouvel agent.

        Raises:
            ProviderNotFoundError: Si le provider n'existe pas.
        """
        provider = self.storage.get_provider(provider_id)
        if not provider:
            raise ProviderNotFoundError(provider_id)

        if config is None:
            config = AgentConfig()

        slug_raw = kwargs.pop("slug", None)
        slug = slug_raw if slug_raw is not None else name.lower().replace(" ", "-")

        agent = Agent(
            name=name,
            provider_id=provider_id,
            system_prompt=system_prompt,
            role=role,
            config=config,
            slug=slug,
            **kwargs,
        )
        return self.storage.save_agent(agent)

    def get_agent(self, agent_id: str) -> Agent:
        """Récupère un agent par ID.

        Raises:
            AgentNotFoundError: Si l'agent n'existe pas.
        """
        agent = self.storage.get_agent(agent_id)
        if not agent:
            raise AgentNotFoundError(agent_id)
        return agent

    def update_agent(self, agent_id: str, **updates: Any) -> Agent:
        """Met à jour les champs d'un agent."""
        agent = self.get_agent(agent_id)
        data = agent.model_dump()
        data.update({k: v for k, v in updates.items() if k in data})
        data["updated_at"] = datetime.now(UTC)
        updated = agent.model_validate(data)
        return self.storage.save_agent(updated)

    def delete_agent(self, agent_id: str) -> bool:
        """Supprime un agent. Retourne True si trouvé et supprimé."""
        return self.storage.delete_agent(agent_id)

    def list_agents(
        self,
        owner_id: str | None = None,
        role: AgentRole | None = None,
        is_active: bool | None = None,
    ) -> list[Agent]:
        """Liste les agents selon des critères."""
        return self.storage.list_agents(
            owner_id=owner_id, role=role, is_active=is_active
        )

    # ── Conversations ──────────────────────────────────────────────────

    def create_conversation(
        self,
        agent_id: str,
        title: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        """Crée une nouvelle conversation pour un agent."""
        agent = self.get_agent(agent_id)
        conversation = Conversation(
            agent_id=agent_id,
            title=title or f"Conversation with {agent.name}",
            metadata=metadata or {},
        )
        return self.storage.save_conversation(conversation)

    def chat(
        self,
        agent_id: str,
        message: str,
        conversation_id: str | None = None,
        **llm_options: Any,
    ) -> tuple[Message, Conversation]:
        """Envoie un message à un agent et retourne sa réponse.

        Si l'agent a des tools et que le LLM demande des tool_calls,
        la boucle tool-calling est exécutée automatiquement.

        Args:
            agent_id: ID de l'agent.
            message: Message utilisateur.
            conversation_id: ID de la conversation (créée si None).
            **llm_options: Options pour le LLM (temperature, max_tokens, …).

        Returns:
            Tuple (message de réponse, conversation).

        Raises:
            AgentNotFoundError: Si l'agent n'existe pas.
            ProviderNotFoundError: Si le provider n'est pas configuré.
            AgentError: En cas d'erreur lors de la conversation.
        """
        agent = self.get_agent(agent_id)
        provider = self.storage.get_provider(agent.provider_id)
        if not provider:
            raise ProviderNotFoundError(agent.provider_id)

        if conversation_id:
            conversation = self.storage.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")
        else:
            conversation = self.create_conversation(agent_id)

        user_message = Message(
            conversation_id=conversation.id,
            content=message,
            role=MessageRole.USER,
        )
        self.storage.save_message(user_message)

        messages = self._build_conversation_context(agent, conversation.id)
        messages.append(user_message)

        llm_client = get_llm_client(provider)

        try:
            has_tools = agent.config.enable_tools and len(self.tool_registry) > 0

            if has_tools:
                llm_response = self.tool_executor.run_tool_loop(
                    client=llm_client,
                    messages=messages,
                    max_iterations=agent.config.max_iterations,
                    conversation_id=conversation.id,
                )
            else:
                llm_request = LLMRequest(
                    messages=messages,
                    temperature=llm_options.get(
                        "temperature", agent.config.temperature
                    ),
                    max_tokens=llm_options.get(
                        "max_tokens", agent.config.max_tokens_per_response
                    ),
                )
                llm_response = llm_client.complete(llm_request)

            assistant_message = Message(
                conversation_id=conversation.id,
                content=llm_response.content,
                role=MessageRole.ASSISTANT,
                metadata={"llm_response_id": llm_response.id, "agent_id": agent_id},
            )
            self.storage.save_message(assistant_message)

            # ── Extraction mémoire best-effort (ADR-020 Phase 2c) ──
            if agent.config.enable_memory:
                try:
                    self.memory_extractor.extract_and_save(
                        agent_id=agent_id,
                        user_message=message,
                        assistant_message=llm_response.content,
                        llm_client=llm_client,
                    )
                except Exception:  # noqa: BLE001
                    pass  # best-effort — ne bloque jamais le chat

            conversation.updated_at = datetime.now(UTC)
            conversation = self.storage.save_conversation(conversation)

            return assistant_message, conversation

        except Exception as exc:
            raise AgentError(f"Error during agent conversation: {exc}") from exc

    def get_conversation_history(
        self,
        conversation_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Message]:
        """Récupère l'historique d'une conversation."""
        return self.storage.get_messages(
            conversation_id=conversation_id,
            limit=limit,
            offset=offset,
        )

    # ── Helpers privés ─────────────────────────────────────────────────

    def _build_conversation_context(
        self,
        agent: Agent,
        conversation_id: str,
        max_messages: int = 50,
    ) -> list[Message]:
        """Construit le contexte de conversation (system prompt + mémoires + historique)."""
        messages: list[Message] = []
        if agent.system_prompt:
            messages.append(
                Message(
                    content=agent.system_prompt,
                    role=MessageRole.SYSTEM,
                    conversation_id=conversation_id,
                )
            )

        # ── Injection des mémoires persistantes (ADR-020 Phase 2a) ──
        if agent.config.enable_memory:
            memories = self.storage.list_memories(agent.id)
            # Filtrer les mémoires expirées et trier par score de pertinence
            active = [m for m in memories if not m.is_expired]
            if active:
                top = sorted(active, key=lambda m: m.relevance_score, reverse=True)[:20]
                block = "\n".join(
                    f"- [{m.memory_type.value}] {m.key}: {m.content}" for m in top
                )
                messages.append(
                    Message(
                        content=(
                            "## Relevant memories from previous interactions\n"
                            f"{block}\n\n"
                            "Use these to personalize your responses."
                        ),
                        role=MessageRole.SYSTEM,
                        conversation_id=conversation_id,
                    )
                )

        history = self.storage.get_messages(
            conversation_id=conversation_id, limit=max_messages
        )
        messages.extend(history)
        return messages

    def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        """Retourne des statistiques sur l'agent (conversations, messages)."""
        conversations = self.storage.list_conversations(agent_id=agent_id)
        total_messages = sum(self.storage.count_messages(c.id) for c in conversations)
        return {
            "agent_id": agent_id,
            "conversation_count": len(conversations),
            "total_messages": total_messages,
        }
