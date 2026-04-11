"""
SuspensionManager — suspension et reprise des workflows.

Si un backend de persistence est fourni, l'état suspendu est sauvegardé,
permettant la reprise après redémarrage.
Sinon, fallback sur un dict en mémoire (comportement v0.2).
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.models import JobRun, RunStatus
from pyworkflow_engine.engine.context import WorkflowContext
from pyworkflow_engine.engine.dag import DAGResolver


class SuspensionManager:
    """Gère la suspension et la reprise des workflows.

    Persistence-aware : si un backend est fourni, ``suspend()`` persiste l'état
    et ``get_suspended()`` peut retrouver un workflow après redémarrage.
    Sans backend, utilise un dict en mémoire (fonctionnement v0.2 inchangé).
    """

    def __init__(self, persistence: Any | None = None):
        self._storage = persistence
        self._in_memory: dict[str, JobRun] = {}

    @property
    def storage(self) -> Any | None:
        return self._storage

    @storage.setter
    def persistence(self, backend: Any | None) -> None:
        self._storage = backend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suspend(self, job_run: JobRun, reason: str) -> None:
        """Enregistre un workflow suspendu.

        Args:
            job_run: JobRun à suspendre.
            reason: Raison de la suspension.
        """
        job_run.suspend(reason)
        self._in_memory[job_run.job_run_id] = job_run

        if self._storage:
            import contextlib

            with contextlib.suppress(Exception):
                self._storage.save_job_run(job_run)

    def get_suspended(self, run_id: str) -> JobRun | None:
        """Retrouve un workflow suspendu.

        Cherche d'abord en mémoire, puis dans la persistence si disponible.

        Args:
            run_id: ID du workflow suspendu.

        Returns:
            JobRun suspendu ou None si non trouvé.
        """
        if run_id in self._in_memory:
            return self._in_memory[run_id]

        if self._storage:
            try:
                job_run = self._storage.get_job_run(run_id)
                if job_run and job_run.status == RunStatus.SUSPENDED:
                    self._in_memory[run_id] = job_run
                    return job_run
            except Exception:
                pass

        return None

    def remove(self, run_id: str) -> None:
        """Supprime un workflow suspendu (après reprise ou annulation).

        Args:
            run_id: ID du workflow à supprimer.
        """
        self._in_memory.pop(run_id, None)

    def list_suspended(self) -> list[str]:
        """Liste les IDs des workflows suspendus.

        Interroge d'abord la persistence si disponible (pour retrouver les
        workflows suspendus après un redémarrage), puis fusionne avec le dict
        en mémoire. Sans backend, retourne uniquement les IDs en mémoire.

        Returns:
            Liste dédupliquée des IDs de workflows suspendus.
        """
        ids: set[str] = set(self._in_memory.keys())

        if self._storage:
            try:
                runs = self._storage.list_job_runs(status="suspended")
                ids.update(r.job_run_id for r in runs)
            except Exception:
                pass  # Fallback silencieux — le dict mémoire reste disponible

        return list(ids)

    def has_suspended(self, run_id: str) -> bool:
        """Vérifie si un workflow est suspendu (mémoire ou persistence)."""
        if run_id in self._in_memory:
            return True
        if self._storage:
            try:
                job_run = self._storage.get_job_run(run_id)
                return job_run is not None and job_run.status.value == "suspended"
            except Exception:
                pass
        return False

    # ------------------------------------------------------------------
    # Resume helpers
    # ------------------------------------------------------------------

    def apply_resume_outputs(
        self, job_run: JobRun, step_outputs: dict[str, Any] | None
    ) -> None:
        """Applique les sorties fournies lors de la reprise."""
        if not step_outputs:
            return
        for step_name, output in step_outputs.items():
            for step_run in job_run.step_runs:
                if (
                    step_run.step_name == step_name
                    and step_run.status == RunStatus.SUSPENDED
                ):
                    step_run.complete_success(output)

    def restore_context(
        self, job_run: JobRun, extra_data: dict | None = None
    ) -> WorkflowContext:
        """Restaure le contexte depuis les steps déjà complétés.

        Args:
            job_run: JobRun suspendu.
            extra_data: Données additionnelles à injecter dans le contexte
                (ex. ``approval_decision`` fourni lors du resume).
        """
        context = WorkflowContext(job_run)
        for step_run in job_run.step_runs:
            if step_run.status == RunStatus.SUCCESS and step_run.output_data:
                context.set_step_output(step_run.step_name, step_run.output_data)
        if extra_data:
            for key, value in extra_data.items():
                context.set(key, value)
        return context

    def calculate_remaining_steps(self, job_run: JobRun) -> list[str]:
        """Calcule les steps restants après une suspension.

        Les steps SUCCESS et SUSPENDED sont considérés comme déjà traités :
        les steps SUSPENDED ont déclenché la suspension mais ne doivent pas
        être ré-exécutés lors de la reprise.
        """
        resolver = DAGResolver(job_run.job)
        done = {
            sr.step_name
            for sr in job_run.step_runs
            if sr.status in (RunStatus.SUCCESS, RunStatus.SUSPENDED)
        }
        return [s for s in resolver.get_execution_order() if s not in done]
