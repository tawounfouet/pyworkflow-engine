"""
RetryHandler — gestion unifiée des tentatives de réexécution.

Remplace à la fois ``engine._retry_step_execution()`` et ``RetryableExecutor``,
évitant les cascades de retry non documentées de l'ancienne architecture.

Comportement lors d'une reprise (``resume``) :
    - Les steps déjà terminés avec succès ne sont **jamais réexécutés**.
    - Un step qui a épuisé ses tentatives (``StepRun.status == FAILED``) n'est
      pas automatiquement relancé : son ``StepRun`` reste en état ``FAILED``.
    - ``step_run.retry_count`` suit le nombre de tentatives écoulées et est
      persisté dans le backend. Il ne se réinitialise pas entre les reprises.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from pyworkflow_engine.engine.context import WorkflowContext

from pyworkflow_engine.models import RunStatus, Step, StepRun


class RetryHandler:
    """Gère les tentatives de réexécution pour un step donné.

    Utilise la configuration de retry définie sur le step lui-même
    (``step.retry_count``, ``step.retry_delay``).

    Comportement du ``retry_count`` :
        - ``Step.retry_count`` est le **nombre maximum de tentatives supplémentaires**
          après l'échec initial (0 = aucun retry, 3 = jusqu'à 4 tentatives au total).
        - ``StepRun.retry_count`` est le compteur de tentatives écoulées
          (incrémenté à chaque essai, persisté dans le backend).
        - Lors d'une **reprise** de workflow, le ``StepRun`` existant est réutilisé ;
          ``StepRun.retry_count`` n'est pas remis à zéro permettant de distinguer
          les reprises manuelles des retries automatiques.
    """

    def attempt(
        self,
        step: Step,
        step_run: StepRun,
        context: WorkflowContext,
        execute_fn: Callable[[Step, WorkflowContext], Any],
    ) -> bool:
        """Tente de réexécuter un step après échec initial.

        Args:
            step: Step à réexécuter. ``step.retry_count`` définit le nombre
                maximum de tentatives supplémentaires (0 = pas de retry).
            step_run: StepRun en échec (modifié en place). ``step_run.retry_count``
                est incrémenté à chaque tentative et persisté.
            context: Contexte de workflow (mis à jour en cas de succès).
            execute_fn: Fonction d'exécution du step (``runner.execute_single``).

        Returns:
            ``True`` si une tentative a réussi, ``False`` si toutes ont échoué.

        Note:
            Si ``step.retry_count == 0``, cette méthode retourne immédiatement
            ``False`` sans retenter. Le ``StepRun`` reste en état ``FAILED``.
        """
        for _ in range(step.retry_count):
            if step.retry_delay.total_seconds() > 0:
                time.sleep(step.retry_delay.total_seconds())

            step_run.retry_count += 1
            step_run.add_log(
                "INFO",
                f"Retrying step — attempt {step_run.retry_count}/{step.retry_count}",
            )
            step_run.status = RunStatus.RUNNING
            step_run.error = None

            try:
                output = execute_fn(step, context)
                step_run.complete_success(output)
                context.set_step_output(step.name, output)
                return True

            except Exception as retry_error:
                step_run.add_log(
                    "ERROR", f"Retry {step_run.retry_count} failed: {retry_error}"
                )
                if step_run.retry_count >= step.retry_count:
                    step_run.complete_failure(str(retry_error))
                    self._log_error(step_run, retry_error)
                    return False

        return False

    def _log_error(self, step_run: StepRun, error: Exception) -> None:
        from pyworkflow_engine.logging import get_logger

        get_logger("engine.retry").error(
            "RETRY EXHAUSTED [%s]: %s", step_run.step_name, error
        )
