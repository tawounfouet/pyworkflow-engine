"""
adapters/ai/tools/registry — Registre central des fonctions Tool.

Associe les clés de tools à leurs fonctions Python (sync ou async).
Supporte l'enregistrement explicite et la résolution via function_path.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any

from pyworkflow_engine.exceptions import AIToolNotFoundError
from pyworkflow_engine.models.ai.tool import ToolDefinition

logger = logging.getLogger(__name__)

ToolFunction = Callable[..., Any]


class ToolRegistry:
    """Registre de fonctions tool pour le function-calling LLM."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolFunction] = {}
        self._definitions: dict[str, ToolDefinition] = {}

    def register(
        self,
        key: str,
        func: ToolFunction,
        definition: ToolDefinition | None = None,
    ) -> None:
        """Enregistre une fonction tool sous une clé donnée."""
        if not callable(func):
            raise TypeError(
                f"Tool function for '{key}' must be callable, got {type(func)}"
            )
        self._tools[key] = func
        if definition is not None:
            self._definitions[key] = definition
        logger.debug("Registered tool: %s", key)

    def register_tool(self, definition: ToolDefinition, func: ToolFunction) -> None:
        """Enregistre un tool depuis sa ToolDefinition."""
        self.register(definition.key, func, definition=definition)

    def get(self, key: str) -> ToolFunction:
        """Récupère la fonction associée à une clé.

        Raises:
            AIToolNotFoundError: Si la clé n'est pas enregistrée.
        """
        fn = self._tools.get(key)
        if fn is None:
            raise AIToolNotFoundError(f"Tool '{key}' not found in registry.")
        return fn

    def get_definition(self, key: str) -> ToolDefinition | None:
        """Récupère la ToolDefinition enregistrée (ou None)."""
        return self._definitions.get(key)

    def has(self, key: str) -> bool:
        """True si une fonction est enregistrée sous cette clé."""
        return key in self._tools

    def keys(self) -> list[str]:
        """Liste toutes les clés enregistrées."""
        return list(self._tools.keys())

    def resolve_from_path(self, key: str, function_path: str) -> None:
        """Résout et enregistre un tool depuis un chemin Python pointé.

        Args:
            key: Clé sous laquelle enregistrer.
            function_path: Chemin dotted vers la fonction (ex: ``myapp.tools.search.run``).
        """
        if not function_path:
            raise ValueError(f"Empty function_path for tool '{key}'")
        module_path, _, func_name = function_path.rpartition(".")
        if not module_path:
            raise ValueError(
                f"Invalid function_path '{function_path}' for tool '{key}'."
            )
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        if not callable(func):
            raise TypeError(
                f"'{function_path}' resolved to {type(func)}, expected callable"
            )
        self.register(key, func)
        logger.debug("Resolved tool '%s' from path '%s'", key, function_path)

    def clear(self) -> None:
        """Supprime tous les tools enregistrés."""
        self._tools.clear()
        self._definitions.clear()

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.has(key)
