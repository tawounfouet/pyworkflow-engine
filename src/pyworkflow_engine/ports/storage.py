"""
Port persistence — contrat abstrait pour tous les backends de persistance.

Ce module définit les interfaces pures (ABC) que toute implémentation de
persistance doit respecter.  Il ne contient aucune implémentation concrète.

Règle hexagonale :
    ``ports/`` ← dépend uniquement de ``exceptions.py`` et de la stdlib.
    ``engine/`` et ``adapters/persistence/`` importent depuis ce module.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job, JobRun

from pyworkflow_engine.exceptions import WorkflowError


# ── Exceptions de contrat ─────────────────────────────────────────────────────


class StorageError(WorkflowError):
    """Exception de base pour les erreurs de persistance."""


class JobNotFoundError(StorageError):
    """Levée quand un job ou un job run demandé est introuvable."""


class TransactionError(StorageError):
    """Levée quand une opération de transaction échoue."""


# ── Port principal ────────────────────────────────────────────────────────────


class BaseStorage(ABC):
    """Contrat abstrait pour tous les backends de persistance.

    Cette interface définit ce que toute implémentation de persistance doit
    exposer.  Elle garantit la cohérence de l'API quelque soit le backend
    utilisé (mémoire, JSON, SQLite, SQLAlchemy, …).

    Principes :
    - Opérations thread-safe
    - Transactions atomiques si le backend le supporte
    - Capacités de requêtage efficaces
    - Gestion d'erreurs cohérente
    """

    @abstractmethod
    def save_job(self, job: Job) -> None:
        """Persiste une définition de job.

        Args:
            job: Le job à sauvegarder.

        Raises:
            StorageError: Si la sauvegarde échoue.
        """

    @abstractmethod
    def get_job(self, job_name: str) -> Job | None:
        """Récupère une définition de job par son nom.

        Args:
            job_name: Nom du job à récupérer.

        Returns:
            Le job si trouvé, ``None`` sinon.

        Raises:
            StorageError: Si la récupération échoue.
        """

    @abstractmethod
    def list_jobs(self, limit: int | None = None, offset: int = 0) -> list[Job]:
        """Liste toutes les définitions de jobs.

        Args:
            limit: Nombre maximum de jobs à retourner.
            offset: Nombre de jobs à ignorer.

        Returns:
            Liste de jobs.

        Raises:
            StorageError: Si la requête échoue.
        """

    @abstractmethod
    def delete_job(self, job_name: str) -> bool:
        """Supprime une définition de job.

        Args:
            job_name: Nom du job à supprimer.

        Returns:
            ``True`` si le job a été supprimé, ``False`` s'il n'existait pas.

        Raises:
            StorageError: Si la suppression échoue.
        """

    @abstractmethod
    def save_job_run(self, job_run: JobRun) -> None:
        """Persiste un job run (état d'exécution).

        Args:
            job_run: Le job run à sauvegarder.

        Raises:
            StorageError: Si la sauvegarde échoue.
        """

    @abstractmethod
    def get_job_run(self, run_id: str) -> JobRun | None:
        """Récupère un job run par son identifiant.

        Args:
            run_id: Identifiant du job run.

        Returns:
            Le job run si trouvé, ``None`` sinon.

        Raises:
            StorageError: Si la récupération échoue.
        """

    @abstractmethod
    def list_job_runs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[JobRun]:
        """Liste les job runs avec filtrage optionnel.

        Args:
            job_name: Filtre par nom de job.
            status: Filtre par statut.
            limit: Nombre maximum de runs à retourner.
            offset: Nombre de runs à ignorer.
            since: Ne retourner que les runs créés après cette date.

        Returns:
            Liste de job runs correspondant aux critères.

        Raises:
            StorageError: Si la requête échoue.
        """

    @abstractmethod
    def delete_job_run(self, run_id: str) -> bool:
        """Supprime un job run.

        Args:
            run_id: Identifiant du job run à supprimer.

        Returns:
            ``True`` si le run a été supprimé, ``False`` s'il n'existait pas.

        Raises:
            StorageError: Si la suppression échoue.
        """

    @abstractmethod
    def update_job_run(self, job_run: JobRun) -> None:
        """Met à jour un job run existant.

        Args:
            job_run: Le job run avec les données mises à jour.

        Raises:
            JobNotFoundError: Si le job run n'existe pas.
            StorageError: Si la mise à jour échoue.
        """

    # ── Méthodes utilitaires (non-abstract) ───────────────────────────────────

    def get_job_run_count(self, job_name: str | None = None) -> int:
        """Retourne le nombre de job runs.

        Args:
            job_name: Filtre par nom de job.  ``None`` = tous les runs.

        Returns:
            Nombre de job runs correspondant aux critères.
        """
        runs = self.list_job_runs(job_name=job_name)
        return len(runs)

    # ── Support des transactions ──────────────────────────────────────────────

    def begin_transaction(self) -> None:  # noqa: B027
        """Ouvre une transaction.

        Les backends qui ne supportent pas les transactions doivent laisser
        cette méthode en no-op.
        """

    def commit_transaction(self) -> None:  # noqa: B027
        """Valide la transaction courante.

        Raises:
            TransactionError: Si aucune transaction n'est active ou si le
                commit échoue.
        """

    def rollback_transaction(self) -> None:  # noqa: B027
        """Annule la transaction courante.

        Raises:
            TransactionError: Si aucune transaction n'est active ou si le
                rollback échoue.
        """

    def transaction(self) -> TransactionContext:
        """Retourne un context manager pour gérer les transactions.

        Usage::

            with persistence.transaction():
                persistence.save_job_run(job_run)
                persistence.save_job(job)
                # commit automatique en sortie normale, rollback sur exception
        """
        return TransactionContext(self)

    # ── Observabilité ─────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Vérifie la santé du backend.

        Returns:
            Dictionnaire contenant le statut et les métriques.
        """
        return {
            "status": "healthy",
            "backend": self.__class__.__name__,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_statistics(self) -> dict[str, Any]:
        """Retourne des statistiques sur les données stockées.

        Returns:
            Dictionnaire contenant les statistiques.
        """
        try:
            jobs = self.list_jobs()
            job_runs = self.list_job_runs()
            return {
                "total_jobs": len(jobs),
                "total_job_runs": len(job_runs),
                "backend": self.__class__.__name__,
            }
        except Exception:
            return {
                "total_jobs": 0,
                "total_job_runs": 0,
                "backend": self.__class__.__name__,
                "error": "Unable to collect statistics",
            }

    def cleanup_old_runs(self, older_than: datetime, dry_run: bool = False) -> int:
        """Nettoie les vieux job runs.

        Args:
            older_than: Supprimer les runs antérieurs à cette date.
            dry_run: Si ``True``, compter seulement sans supprimer.

        Returns:
            Nombre de runs supprimés (ou qui auraient été supprimés si
            ``dry_run=True``).
        """
        old_runs = [
            run
            for run in self.list_job_runs()
            if run.start_time and run.start_time < older_than
        ]
        if not dry_run:
            for run in old_runs:
                self.delete_job_run(run.job_run_id)
        return len(old_runs)


# ── Context manager de transaction ───────────────────────────────────────────


class TransactionContext:
    """Context manager pour les transactions de persistance."""

    def __init__(self, persistence: BaseStorage) -> None:
        self.storage = persistence
        self._in_transaction = False

    def __enter__(self) -> BaseStorage:
        self.persistence.begin_transaction()
        self._in_transaction = True
        return self.persistence

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._in_transaction:
            if exc_type is None:
                try:
                    self.persistence.commit_transaction()
                except Exception:
                    with contextlib.suppress(Exception):
                        self.persistence.rollback_transaction()
                    raise
            else:
                with contextlib.suppress(Exception):
                    self.persistence.rollback_transaction()
            self._in_transaction = False
