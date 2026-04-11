"""
BaseTrigger — contrat abstrait pour tous les déclencheurs de workflow.

Un trigger est responsable de :
  1. Décider *quand* un workflow doit démarrer.
  2. Appeler ``engine.run(job)`` (ou équivalent) au bon moment.
  3. Gérer son propre cycle de vie (start / stop).

Zéro dépendance externe — stdlib uniquement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from pyworkflow_engine.facade import WorkflowEngine
    from pyworkflow_engine.models import Job, JobRun


class TriggerState(Enum):
    """État du cycle de vie d'un trigger."""

    IDLE = "idle"
    """Créé, mais pas encore démarré."""

    RUNNING = "running"
    """Actif — surveille ou attend un événement."""

    STOPPED = "stopped"
    """Arrêté proprement."""

    ERROR = "error"
    """Arrêté suite à une erreur interne."""


class BaseTrigger(ABC):
    """Contrat abstrait pour tous les déclencheurs de workflow.

    Sous-classez ``BaseTrigger`` pour créer un nouveau type de trigger.
    Les sous-classes doivent implémenter :

    - :meth:`start` — démarrer la surveillance/le déclenchement.
    - :meth:`stop`  — arrêter proprement.
    - :meth:`fire`  — déclencher une exécution du job maintenant.

    Args:
        engine: Instance ``WorkflowEngine`` utilisée pour exécuter les jobs.
        name: Nom lisible du trigger (utile pour les logs et le debug).
        on_run_complete: Callback optionnel appelé après chaque exécution
            réussie : ``on_run_complete(job_run)``.
        on_run_error: Callback optionnel appelé en cas d'erreur :
            ``on_run_error(exception)``.

    Examples:
        >>> class MyTrigger(BaseTrigger):
        ...     def start(self): ...
        ...     def stop(self): ...
        ...     def fire(self, job, initial_context=None): ...
        >>>
        >>> trigger = MyTrigger(engine=engine, name="my-trigger")
        >>> trigger.start()
        >>> trigger.stop()
    """

    def __init__(
        self,
        engine: WorkflowEngine,
        name: str = "",
        on_run_complete: Callable[[JobRun], None] | None = None,
        on_run_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._engine = engine
        self._name = name or self.__class__.__name__
        self._on_run_complete = on_run_complete
        self._on_run_error = on_run_error
        self._state = TriggerState.IDLE
        self._run_count = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Nom lisible du trigger."""
        return self._name

    @property
    def state(self) -> TriggerState:
        """État courant du cycle de vie."""
        return self._state

    @property
    def run_count(self) -> int:
        """Nombre de fois que ce trigger a déclenché une exécution."""
        return self._run_count

    @property
    def is_running(self) -> bool:
        """``True`` si le trigger est actif."""
        return self._state == TriggerState.RUNNING

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def start(self) -> None:
        """Démarre le trigger.

        Après l'appel, ``state`` doit être ``TriggerState.RUNNING``.
        Pour les triggers asynchrones (schedule, file watcher, etc.),
        cette méthode démarre un thread ou une coroutine en arrière-plan
        et retourne immédiatement.

        Raises:
            RuntimeError: Si le trigger est déjà en cours ou arrêté.
        """

    @abstractmethod
    def stop(self) -> None:
        """Arrête le trigger proprement.

        Après l'appel, ``state`` doit être ``TriggerState.STOPPED``.
        Les ressources (threads, fichiers, connexions) doivent être libérées.
        """

    @abstractmethod
    def fire(
        self,
        job: Job,
        initial_context: dict[str, Any] | None = None,
    ) -> JobRun:
        """Déclenche une exécution du job immédiatement.

        Args:
            job: Job à exécuter.
            initial_context: Données initiales du contexte.

        Returns:
            ``JobRun`` résultant de l'exécution.
        """

    # ------------------------------------------------------------------
    # Helpers pour les sous-classes
    # ------------------------------------------------------------------

    def _do_fire(
        self,
        job: Job,
        initial_context: dict[str, Any] | None = None,
    ) -> JobRun:
        """Exécute le job via l'engine et notifie les callbacks.

        Utilisé par les implémentations de ``fire`` et les triggers
        asynchrones pour centraliser la gestion des callbacks et du compteur.

        Args:
            job: Job à exécuter.
            initial_context: Données initiales du contexte.

        Returns:
            ``JobRun`` résultant.
        """
        try:
            job_run = self._engine.run(job, initial_context=initial_context)
            self._run_count += 1
            if self._on_run_complete:
                self._on_run_complete(job_run)
            return job_run
        except Exception as exc:
            if self._on_run_error:
                self._on_run_error(exc)
            raise

    def _set_state(self, state: TriggerState) -> None:
        self._state = state

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self._name!r}, "
            f"state={self._state.value}, run_count={self._run_count})"
        )
