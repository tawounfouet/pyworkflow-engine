"""
AIFacade — sous-façade dédiée aux opérations IA.

Regroupe toutes les fonctionnalités IA (agents, conversations, connaissances)
dans un objet cohérent accessible via ``engine.ai``.

Usage::

    from pyworkflow_engine import WorkflowEngine

    engine = WorkflowEngine()

    agent = engine.ai.create_agent(
        name="DataAnalyst",
        model="claude-3-5-sonnet",
        system_prompt="Tu es un analyste de données expert.",
    )
    response = engine.ai.chat(agent.agent_id, "Analyse ces ventes…")

    # Accès direct au storage IA (pour lecture avancée sans AgentService)
    raw_agents = engine.ai.storage.list_agents()

Règle d'isolation :
    Cette classe importe ``engine.ai.*`` uniquement via ``try/except ImportError``,
    ce qui garantit que l'absence du sous-package ``[ai]`` ne rompt pas l'import
    du cœur du moteur.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from pyworkflow_engine.exceptions import WorkflowError
from pyworkflow_engine.logging import get_logger

_logger = get_logger("engine.facade.ai")


class AIFacade:
    """Sous-façade dédiée aux opérations IA de PyWorkflow Engine.

    Accessible via ``WorkflowEngine.ai`` — ne pas instancier directement.

    Regroupe :
    - Gestion des agents (CRUD)
    - Chat / conversations
    - Accès direct au storage IA

    Args:
        ai_storage: Backend de storage IA optionnel.  Si ``None``, un
            ``SQLiteAIStorage`` par défaut est créé lors du premier appel.

    Examples:
        >>> engine = WorkflowEngine()
        >>> agent = engine.ai.create_agent(name="Bot", model="claude-3-5-sonnet")
        >>> reply = engine.ai.chat(agent.agent_id, "Bonjour !")
        >>> print(reply.content)
    """

    def __init__(self, ai_storage: Any | None = None) -> None:
        self._ai_storage = ai_storage
        self._cached_service: Any | None = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _service(self) -> Any:
        """Retourne (et met en cache) l'``AgentService``.

        Lazy-importe pour ne pas forcer la dépendance ``[ai]`` à l'import.

        Raises:
            WorkflowError: Si le sous-package ``engine.ai`` n'est pas
                disponible (extra ``[ai]`` non installé).
        """
        if self._cached_service is None:
            try:
                from pyworkflow_engine.adapters.ai.storage.sqlite import (  # noqa: PLC0415
                    SQLiteAIStorage,
                )
                from pyworkflow_engine.engine.ai.agent_service import (  # noqa: PLC0415
                    AgentService,
                )
            except ImportError as exc:
                raise WorkflowError(
                    "AI subsystem not available. "
                    "Install with: pip install 'pyworkflow-engine[ai]'",
                    details={"missing": str(exc)},
                ) from exc

            storage = self._ai_storage or SQLiteAIStorage()
            self._cached_service = AgentService(storage=storage)

        return self._cached_service

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    def create_agent(self, **kwargs: Any) -> Any:
        """Crée un agent IA et le persiste dans le storage IA.

        Args:
            **kwargs: Champs passés à ``AgentService.create_agent()``.
                ``name`` et ``model`` sont obligatoires.

        Returns:
            ``Agent`` Pydantic model.

        Raises:
            WorkflowError: Si le sous-package ``[ai]`` n'est pas installé.
        """
        return self._service().create_agent(**kwargs)

    def get_agent(self, agent_id: str) -> Any:
        """Récupère un agent IA par son identifiant.

        Args:
            agent_id: Identifiant unique de l'agent.

        Returns:
            ``Agent`` ou ``None`` si non trouvé.
        """
        return self._service().get_agent(agent_id)

    def list_agents(self, **filters: Any) -> list[Any]:
        """Liste les agents IA avec filtres optionnels.

        Args:
            **filters: Critères de filtrage passés à ``AgentService.list_agents()``.

        Returns:
            Liste d'``Agent``.
        """
        return self._service().list_agents(**filters)

    def delete_agent(self, agent_id: str) -> bool:
        """Supprime un agent IA.

        Args:
            agent_id: Identifiant de l'agent à supprimer.

        Returns:
            ``True`` si supprimé, ``False`` s'il n'existait pas.
        """
        return self._service().delete_agent(agent_id)

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    def chat(
        self,
        agent_id: str,
        message: str,
        conversation_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Envoie un message à un agent IA et retourne sa réponse.

        Args:
            agent_id: Identifiant de l'agent destinataire.
            message: Message de l'utilisateur.
            conversation_id: ID d'une conversation existante.
                Si ``None``, une nouvelle conversation est créée.
            **kwargs: Options supplémentaires passées à ``AgentService.chat()``.

        Returns:
            ``Message`` Pydantic model (réponse de l'agent).

        Raises:
            WorkflowError: Si le sous-package ``[ai]`` n'est pas installé.
        """
        return self._service().chat(
            agent_id=agent_id,
            message=message,
            conversation_id=conversation_id,
            **kwargs,
        )

    def get_conversation_history(self, conversation_id: str) -> list[Any]:
        """Récupère l'historique d'une conversation.

        Args:
            conversation_id: Identifiant de la conversation.

        Returns:
            Liste de ``Message`` dans l'ordre chronologique.
        """
        return self._service().get_conversation_history(conversation_id)

    # ------------------------------------------------------------------
    # Storage access
    # ------------------------------------------------------------------

    @property
    def storage(self) -> Any:
        """Accès direct au backend ``SQLiteAIStorage`` (lazy-init).

        Utile pour des lectures avancées sans passer par ``AgentService``
        (ex. vues GUI qui listent agents/conversations/messages).

        Returns:
            Instance de storage IA, ou ``None`` si le sous-package ``[ai]``
            n'est pas disponible.
        """
        try:
            return self._service().storage
        except WorkflowError:
            return None
        except Exception as exc:  # noqa: BLE001
            _logger.warning("AI storage unavailable: %s", exc)
            return None
