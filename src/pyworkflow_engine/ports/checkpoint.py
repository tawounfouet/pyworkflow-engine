"""
ports/checkpoint — Contrat abstrait pour la persistence de checkpoints.

Permet de sauvegarder l'état d'un pipeline à un point donné et de
reprendre l'exécution depuis ce checkpoint (pattern LangGraph-inspiré).

Règle hexagonale :
    Ce module ne contient aucune implémentation concrète.
    Les adapters (SQLiteCheckpointStore, …) implémentent cette interface.

Architecture : ADR-021 (Phase 2)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CheckpointNotFoundError(Exception):
    """Levée quand un checkpoint demandé n'existe pas."""

    def __init__(self, checkpoint_id: str) -> None:
        super().__init__(f"Checkpoint not found: {checkpoint_id}")
        self.checkpoint_id = checkpoint_id


class CheckpointRecord:
    """Enregistrement d'un checkpoint de pipeline.

    Attributes:
        checkpoint_id: Identifiant unique du checkpoint.
        pipeline_run_id: ID du run de pipeline associé.
        stage_index: Index du stage au moment du checkpoint.
        stage_name: Nom du stage (informatif).
        context: Snapshot du contexte au moment du checkpoint (dict JSON-sérialisable).
        created_at: Timestamp ISO de création.
        metadata: Données arbitraires (tags, labels, etc.).
    """

    __slots__ = (
        "checkpoint_id",
        "context",
        "created_at",
        "metadata",
        "pipeline_run_id",
        "stage_index",
        "stage_name",
    )

    def __init__(
        self,
        checkpoint_id: str,
        pipeline_run_id: str,
        stage_index: int,
        context: dict[str, Any],
        *,
        stage_name: str = "",
        created_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.checkpoint_id = checkpoint_id
        self.pipeline_run_id = pipeline_run_id
        self.stage_index = stage_index
        self.stage_name = stage_name
        self.context = context
        self.created_at = created_at
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return (
            f"CheckpointRecord(id={self.checkpoint_id!r}, "
            f"run={self.pipeline_run_id!r}, stage={self.stage_index})"
        )


class BaseCheckpointStore(ABC):
    """Contrat pour la persistence de checkpoints de pipeline.

    Usage::

        store = SQLiteCheckpointStore("workflow.db")
        cid = store.save(
            pipeline_run_id="run-uuid",
            stage_index=2,
            context={"output": {"count": 42}},
        )
        record = store.load(cid)
        # Reprendre depuis record.context, record.stage_index
    """

    @abstractmethod
    def save(
        self,
        pipeline_run_id: str,
        stage_index: int,
        context: dict[str, Any],
        *,
        stage_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Sauvegarde un snapshot du contexte à un stage donné.

        Args:
            pipeline_run_id: ID du run de pipeline à checkpointer.
            stage_index: Index du stage courant (0-based).
            context: Snapshot complet du contexte pipeline.
            stage_name: Nom lisible du stage (optionnel).
            metadata: Données arbitraires supplémentaires.

        Returns:
            ``checkpoint_id`` généré (UUID).
        """

    @abstractmethod
    def load(self, checkpoint_id: str) -> CheckpointRecord:
        """Charge un checkpoint par son ID.

        Args:
            checkpoint_id: UUID du checkpoint.

        Returns:
            ``CheckpointRecord`` avec contexte + métadonnées.

        Raises:
            CheckpointNotFoundError: Si le checkpoint n'existe pas.
        """

    @abstractmethod
    def list_for_run(self, pipeline_run_id: str) -> list[CheckpointRecord]:
        """Liste les checkpoints disponibles pour un run, triés par stage_index.

        Args:
            pipeline_run_id: ID du run de pipeline.

        Returns:
            Liste de ``CheckpointRecord`` ordonnés par ``stage_index`` croissant.
        """

    @abstractmethod
    def get_latest(self, pipeline_run_id: str) -> CheckpointRecord | None:
        """Récupère le checkpoint le plus récent pour un run.

        Args:
            pipeline_run_id: ID du run de pipeline.

        Returns:
            ``CheckpointRecord`` du dernier stage checkpointé, ou ``None``
            si aucun checkpoint n'existe pour ce run.
        """

    @abstractmethod
    def delete(self, checkpoint_id: str) -> bool:
        """Supprime un checkpoint.

        Args:
            checkpoint_id: UUID du checkpoint à supprimer.

        Returns:
            ``True`` si trouvé et supprimé, ``False`` sinon.
        """

    @abstractmethod
    def delete_for_run(self, pipeline_run_id: str) -> int:
        """Supprime tous les checkpoints d'un run.

        Args:
            pipeline_run_id: ID du run de pipeline.

        Returns:
            Nombre de checkpoints supprimés.
        """

    def close(self) -> None:  # noqa: B027
        """Libère les ressources (no-op par défaut)."""
