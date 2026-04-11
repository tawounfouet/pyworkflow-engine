"""
ManualTrigger — déclenchement explicite d'un workflow par le code.

Le trigger le plus simple : pas de surveillance en arrière-plan, pas de
planification. L'utilisateur appelle ``fire(job)`` quand il le souhaite.

Utile pour :
  - Les pipelines déclenchés par une action utilisateur ou une API.
  - Les tests unitaires de workflows.
  - Les workflows ad-hoc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import BaseTrigger, TriggerState

if TYPE_CHECKING:
    from ..facade import WorkflowEngine
    from ..models import Job, JobRun


class ManualTrigger(BaseTrigger):
    """Trigger à déclenchement manuel — aucune automatisation.

    ``start()`` et ``stop()`` gèrent uniquement l'état interne. L'exécution
    du workflow se fait exclusivement via ``fire(job)``.

    Args:
        engine: Instance ``WorkflowEngine``.
        name: Nom lisible (défaut : ``"ManualTrigger"``).
        **kwargs: Transmis à ``BaseTrigger.__init__``.

    Examples:
        >>> trigger = ManualTrigger(engine=engine, name="etl-trigger")
        >>> trigger.start()
        >>> job_run = trigger.fire(job, initial_context={"env": "prod"})
        >>> print(job_run.status)
        RunStatus.SUCCESS
        >>> trigger.stop()
    """

    def __init__(self, engine: WorkflowEngine, name: str = "ManualTrigger", **kwargs: Any) -> None:
        super().__init__(engine=engine, name=name, **kwargs)

    # ------------------------------------------------------------------
    # BaseTrigger interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Marque le trigger comme actif.

        Pour ManualTrigger, cela ne démarre aucun thread ou processus.

        Raises:
            RuntimeError: Si le trigger est déjà actif.
        """
        if self._state == TriggerState.RUNNING:
            raise RuntimeError(f"Trigger '{self._name}' is already running")
        self._set_state(TriggerState.RUNNING)

    def stop(self) -> None:
        """Marque le trigger comme arrêté."""
        self._set_state(TriggerState.STOPPED)

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

        Raises:
            RuntimeError: Si le trigger n'a pas été démarré.
        """
        if self._state != TriggerState.RUNNING:
            raise RuntimeError(
                f"Trigger '{self._name}' is not running. Call start() first."
            )
        return self._do_fire(job, initial_context=initial_context)
