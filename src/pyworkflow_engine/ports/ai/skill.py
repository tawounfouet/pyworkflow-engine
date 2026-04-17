"""
Port IA — interface abstraite pour les Skills.

Un Skill est une capacité de haut niveau qui orchestre plusieurs Tools
et un LLM pour accomplir une tâche complexe (ex : ResearchSkill,
SummarySkill, CodeReviewSkill, …).

Différence Tool vs Skill :
    - Tool  = fonction atomique (calcul, requête HTTP, …)
    - Skill = orchestration Tools + raisonnement LLM
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pyworkflow_engine.models.ai.types import SkillCategory

if TYPE_CHECKING:
    from pyworkflow_engine.ports.ai.llm import BaseLLMClient

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """Interface abstraite pour tous les Skills concrets.

    Pour créer un skill :

    1. Sous-classer ``BaseSkill``.
    2. Définir les attributs de classe ``key``, ``name``, ``description``,
       ``category`` et ``required_tool_keys``.
    3. Implémenter ``run(*, llm_client, **kwargs)`` (sync obligatoire).
    4. Surcharger optionnellement ``arun(...)`` pour un async natif.
    """

    # ── Attributs de classe (à redéfinir) ─────────────────────────────
    key: str = ""
    name: str = ""
    description: str = ""
    category: SkillCategory = SkillCategory.CUSTOM
    required_tool_keys: list[str] = []
    is_active: bool = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if ABC not in cls.__bases__ and not cls.key:
            raise TypeError(
                f"Skill class '{cls.__name__}' must define a non-empty 'key' attribute."
            )

    # ── Interface obligatoire ──────────────────────────────────────────

    @abstractmethod
    def run(
        self,
        *,
        llm_client: BaseLLMClient,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Exécute le skill de manière synchrone.

        Args:
            llm_client: Client LLM à utiliser pour le raisonnement.
            agent_id: ID de l'agent appelant (optionnel).
            conversation_id: ID de la conversation (optionnel).
            **kwargs: Paramètres spécifiques au skill.

        Returns:
            Résultat du skill (str, dict, list, …).
        """

    # ── Méthodes par défaut ────────────────────────────────────────────

    async def arun(
        self,
        *,
        llm_client: BaseLLMClient,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Exécute le skill de manière asynchrone.

        Par défaut délègue à ``run()`` dans un thread pool.
        Surcharger pour une implémentation async native.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run(
                llm_client=llm_client,
                agent_id=agent_id,
                conversation_id=conversation_id,
                **kwargs,
            ),
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} key={self.key!r}>"
