"""
WorkflowContext — gestion des données partagées entre steps.

Fournit un accès centralisé aux données du contexte d'exécution,
aux sorties des steps précédents, et aux métadonnées de run.

Utilise des structures stdlib — zero dépendance externe.
"""

from __future__ import annotations

import copy
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pyworkflow_engine.models import JobRun, StepRun

from pyworkflow_engine.exceptions import ContextError


class WorkflowContext:
    """Contexte d'exécution d'un workflow.

    Fournit un accès centralisé aux données partagées entre les steps,
    aux métadonnées d'exécution, et aux résultats des steps précédents.

    Examples:
        >>> context = WorkflowContext(job_run)
        >>> context.set("config", {"database_url": "sqlite:///app.db"})
        >>> context.set_step_output("extract", {"records": 1000})
        >>>
        >>> # Dans une step suivante
        >>> records = context.get_step_output("extract")["records"]
    """

    def __init__(self, job_run: JobRun):
        self.job_run = job_run
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._step_outputs: dict[str, Any] = {}
        self._metadata: dict[str, Any] = {}
        self._frozen = False
        if job_run.input_data:
            self._data.update(job_run.input_data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if self._frozen:
                raise ContextError(
                    "Context is frozen and cannot be modified",
                    context_key=key,
                    context_operation="set",
                    job_name=self.job_run.job_name,
                )
            self._data[key] = value

    def get_step_output(self, step_name: str, default: Any = None) -> Any:
        with self._lock:
            return self._step_outputs.get(step_name, default)

    def set_step_output(self, step_name: str, output: Any) -> None:
        with self._lock:
            if self._frozen:
                raise ContextError(
                    f"Context is frozen, cannot set output for step '{step_name}'",
                    context_key=step_name,
                    context_operation="set_step_output",
                    job_name=self.job_run.job_name,
                )
            self._step_outputs[step_name] = output
            self.job_run.update_context(step_name, output)

    def has(self, key: str) -> bool:
        return key in self._data

    def has_step_output(self, step_name: str) -> bool:
        return step_name in self._step_outputs

    def keys(self) -> Iterator[str]:
        return iter(self._data.keys())

    def step_names(self) -> Iterator[str]:
        return iter(self._step_outputs.keys())

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def freeze(self) -> None:
        self._frozen = True

    def unfreeze(self) -> None:
        self._frozen = False

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_run_id": self.job_run.job_run_id,
            "job_name": self.job_run.job_name,
            "data": copy.deepcopy(self._data),
            "step_outputs": copy.deepcopy(self._step_outputs),
            "metadata": copy.deepcopy(self._metadata),
            "frozen": self._frozen,
            "created_at": self.job_run.created_at.isoformat(),
        }

    def copy(self) -> WorkflowContext:
        new_context = WorkflowContext(self.job_run)
        new_context._data = copy.deepcopy(self._data)
        new_context._step_outputs = copy.deepcopy(self._step_outputs)
        new_context._metadata = copy.deepcopy(self._metadata)
        new_context._frozen = self._frozen
        return new_context

    def merge_from(self, other: WorkflowContext, overwrite: bool = False) -> None:
        with self._lock:
            if self._frozen:
                raise ContextError(
                    "Cannot merge into frozen context",
                    context_operation="merge",
                    job_name=self.job_run.job_name,
                )
            for key, value in other._data.items():
                if overwrite or key not in self._data:
                    self._data[key] = copy.deepcopy(value)
            for step_name, output in other._step_outputs.items():
                if overwrite or step_name not in self._step_outputs:
                    self.set_step_output(step_name, copy.deepcopy(output))
            for key, value in other._metadata.items():
                if overwrite or key not in self._metadata:
                    self._metadata[key] = copy.deepcopy(value)

    def clear(self) -> None:
        with self._lock:
            if self._frozen:
                raise ContextError(
                    "Cannot clear frozen context",
                    context_operation="clear",
                    job_name=self.job_run.job_name,
                )
            self._data.clear()
            self._step_outputs.clear()
            self._metadata.clear()

    def get_step_run(self, step_name: str) -> StepRun | None:
        return self.job_run.get_step_run(step_name)

    def get_completed_steps(self) -> list[str]:
        from pyworkflow_engine.models import RunStatus

        return [
            r.step_name for r in self.job_run.get_step_runs_by_status(RunStatus.SUCCESS)
        ]

    def get_failed_steps(self) -> list[str]:
        from pyworkflow_engine.models import RunStatus

        return [
            r.step_name for r in self.job_run.get_step_runs_by_status(RunStatus.FAILED)
        ]

    def get_all_outputs(self) -> dict[str, Any]:
        return copy.deepcopy(self._step_outputs)

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __getitem__(self, key: str) -> Any:
        if not self.has(key):
            raise KeyError(f"Context key '{key}' not found")
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __repr__(self) -> str:
        return (
            f"WorkflowContext(job_run_id={self.job_run.job_run_id[:8]}..., "
            f"data_keys={list(self._data.keys())}, "
            f"step_outputs={list(self._step_outputs.keys())}, "
            f"frozen={self._frozen})"
        )
