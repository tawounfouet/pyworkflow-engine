"""
BaseExecutor et ExecutorRegistry — abstractions de base pour les executors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..engine.context import WorkflowContext
    from ..models import Step


class BaseExecutor(ABC):
    """Classe de base pour tous les executors de steps."""

    @abstractmethod
    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Exécute un step.

        Args:
            step: Step à exécuter.
            context: Contexte de workflow.

        Returns:
            Résultat de l'exécution.
        """


class ExecutorRegistry:
    """Registry pour gérer les executors avancés."""

    def __init__(self):
        self._executors: dict[str, BaseExecutor] = {}

    def register(self, name: str, executor: BaseExecutor) -> None:
        """Enregistre un executor."""
        self._executors[name] = executor

    def get(self, name: str) -> BaseExecutor | None:
        """Retourne un executor par nom."""
        return self._executors.get(name)

    def list_executors(self) -> list[str]:
        """Liste les noms des executors enregistrés."""
        return list(self._executors.keys())

    def shutdown_all(self) -> None:
        """Arrête tous les executors qui le supportent."""
        for executor in self._executors.values():
            if hasattr(executor, "shutdown"):
                import contextlib

                with contextlib.suppress(Exception):
                    executor.shutdown()
