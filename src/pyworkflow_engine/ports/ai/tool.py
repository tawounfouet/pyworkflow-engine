"""
Port IA — interface abstraite pour les Tools.

Un Tool est une fonction atomique (calcul, requête HTTP, recherche web, …)
que le LLM peut invoquer via le mécanisme de function-calling.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from pyworkflow_engine.models.ai.tool import ToolDefinition
from pyworkflow_engine.models.ai.types import ToolType

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Interface abstraite pour tous les Tools concrets.

    Pour créer un tool :

    1. Sous-classer ``BaseTool``.
    2. Définir les attributs de classe ``key``, ``name``, ``description``
       et ``parameters_schema``.
    3. Implémenter ``run(**kwargs)`` (sync obligatoire).
    4. Surcharger optionnellement ``arun(**kwargs)`` pour un async natif.

    Example::

        class AddTool(BaseTool):
            key = "add"
            name = "Add Numbers"
            description = "Adds two numbers."
            parameters_schema = {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            }

            def run(self, *, a: float, b: float, **kwargs: Any) -> float:
                return a + b
    """

    # ── Attributs de classe (à redéfinir) ─────────────────────────────
    key: str = ""
    name: str = ""
    description: str = ""
    tool_type: ToolType = ToolType.FUNCTION
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}}
    requires_approval: bool = False
    is_dangerous: bool = False
    is_active: bool = True
    # Sous-classes qui attribuent leur key dynamiquement en __init__
    # peuvent passer _dynamic_key = True pour sauter la vérification.
    _dynamic_key: bool = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Vérification à la définition de la sous-classe (pas sur BaseTool lui-même).
        # On saute la vérification si :
        #   – la classe est elle-même abstraite (ABC dans __bases__), ou
        #   – elle déclare _dynamic_key = True (key assignée dans __init__).
        if ABC not in cls.__bases__ and not cls._dynamic_key and not cls.key:
            raise TypeError(
                f"Tool class '{cls.__name__}' must define a non-empty 'key' attribute."
            )

    # ── Interface obligatoire ──────────────────────────────────────────

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Exécute le tool de manière synchrone.

        Args:
            **kwargs: Paramètres définis dans ``parameters_schema``.

        Returns:
            Résultat du tool (str, dict, list, …).
        """

    # ── Méthodes par défaut ────────────────────────────────────────────

    async def arun(self, **kwargs: Any) -> Any:
        """Exécute le tool de manière asynchrone.

        Par défaut délègue à ``run()`` dans un thread pool.
        Surcharger pour une implémentation async native.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.run(**kwargs))

    def __call__(self, **kwargs: Any) -> Any:
        """Permet d'appeler le tool directement : ``tool(query="hello")``."""
        return self.run(**kwargs)

    # ── ToolDefinition ─────────────────────────────────────────────────

    @property
    def definition(self) -> ToolDefinition:
        """Retourne la ``ToolDefinition`` associée à ce tool."""
        return ToolDefinition(
            key=self.key,
            name=self.name,
            description=self.description,
            tool_type=self.tool_type,
            parameters_schema=self.parameters_schema,
            function_path=f"{self.__class__.__module__}.{self.__class__.__name__}",
            requires_approval=self.requires_approval,
            is_dangerous=self.is_dangerous,
            is_active=self.is_active,
        )

    def get_function_schema(self) -> dict[str, Any]:
        """Retourne le schéma OpenAI function-calling pour ce tool."""
        return self.definition.get_function_schema()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} key={self.key!r}>"
