"""
Port executor — contrat abstrait pour tous les executors de steps.

Ce module définit les interfaces pures (ABC) que toute implémentation
d'executor doit respecter.  Il ne contient aucune implémentation concrète.

Règle hexagonale :
    ``ports/`` ← dépend uniquement de la stdlib.
    ``engine/`` et ``adapters/executors/`` importent depuis ce module.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.engine.context import WorkflowContext
    from pyworkflow_engine.models import Step


# ── Port principal ────────────────────────────────────────────────────────────


class BaseExecutor(ABC):
    """Contrat abstrait pour tous les executors de steps."""

    @abstractmethod
    def execute(self, step: Step, context: WorkflowContext) -> Any:
        """Exécute un step.

        Args:
            step: Step à exécuter.
            context: Contexte de workflow.

        Returns:
            Résultat de l'exécution.
        """


# ── Registry ─────────────────────────────────────────────────────────────────


class ExecutorRegistry:
    """Registry pour gérer les executors avancés."""

    def __init__(self) -> None:
        self._executors: dict[str, BaseExecutor] = {}

    def register(self, name: str, executor: BaseExecutor) -> None:
        """Enregistre un executor sous un nom donné."""
        self._executors[name] = executor

    def get(self, name: str) -> BaseExecutor | None:
        """Retourne un executor par son nom, ou ``None``."""
        return self._executors.get(name)

    def list_executors(self) -> list[str]:
        """Retourne la liste des noms d'executors enregistrés."""
        return list(self._executors.keys())

    def shutdown_all(self) -> None:
        """Arrête tous les executors qui exposent une méthode ``shutdown``."""
        for executor in self._executors.values():
            if hasattr(executor, "shutdown"):
                with contextlib.suppress(Exception):
                    executor.shutdown()
