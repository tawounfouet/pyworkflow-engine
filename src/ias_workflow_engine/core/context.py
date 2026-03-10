"""
Contexte d'exécution de workflow — gestion des données partagées.

Le WorkflowContext gère le passage de données entre les steps d'un workflow,
fournit l'accès aux métadonnées d'exécution, et maintient l'état global.

Utilise des structures stdlib — zero dépendance externe.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union, Iterator, List
from datetime import datetime
import copy

from .models import JobRun, StepRun
from .exceptions import ContextError


class WorkflowContext:
    """Contexte d'exécution d'un workflow.

    Le contexte fournit un accès centralisé aux données partagées entre
    les steps, aux métadonnées d'exécution, et aux résultats des steps précédents.

    Le contexte est thread-safe pour les opérations de lecture, mais les
    opérations d'écriture doivent être synchronisées par l'engine.

    Attributes:
        job_run: Instance JobRun associée à ce contexte.
        _data: Dictionnaire des données du contexte.
        _step_outputs: Dictionnaire des sorties des steps.
        _metadata: Métadonnées additionnelles du contexte.
        _frozen: Si True, le contexte est en lecture seule.

    Examples:
        >>> context = WorkflowContext(job_run)
        >>> context.set("config", {"database_url": "sqlite:///app.db"})
        >>> context.set_step_output("extract", {"records": 1000})
        >>>
        >>> # Dans une step suivante
        >>> records = context.get_step_output("extract")["records"]
        >>> config = context.get("config")
    """

    def __init__(self, job_run: JobRun):
        """Initialise le contexte avec un JobRun.

        Args:
            job_run: Instance JobRun pour laquelle ce contexte est créé.
        """
        self.job_run = job_run
        self._data: Dict[str, Any] = {}
        self._step_outputs: Dict[str, Any] = {}
        self._metadata: Dict[str, Any] = {}
        self._frozen = False

        # Initialiser avec les données d'entrée du job
        if job_run.input_data:
            self._data.update(job_run.input_data)

    def get(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur du contexte.

        Args:
            key: Clé de la donnée à récupérer.
            default: Valeur par défaut si la clé n'existe pas.

        Returns:
            La valeur associée à la clé, ou default.
        """
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Définit une valeur dans le contexte.

        Args:
            key: Clé de la donnée.
            value: Valeur à stocker.

        Raises:
            ContextError: Si le contexte est gelé.
        """
        if self._frozen:
            raise ContextError(
                "Context is frozen and cannot be modified",
                context_key=key,
                context_operation="set",
                job_name=self.job_run.job_name,
            )

        self._data[key] = value

    def get_step_output(self, step_name: str, default: Any = None) -> Any:
        """Récupère la sortie d'une step.

        Args:
            step_name: Nom de la step.
            default: Valeur par défaut si la step n'a pas de sortie.

        Returns:
            La sortie de la step, ou default.
        """
        return self._step_outputs.get(step_name, default)

    def set_step_output(self, step_name: str, output: Any) -> None:
        """Définit la sortie d'une step.

        Args:
            step_name: Nom de la step.
            output: Sortie de la step.

        Raises:
            ContextError: Si le contexte est gelé.
        """
        if self._frozen:
            raise ContextError(
                f"Context is frozen, cannot set output for step '{step_name}'",
                context_key=step_name,
                context_operation="set_step_output",
                job_name=self.job_run.job_name,
            )

        self._step_outputs[step_name] = output
        # Synchroniser avec le JobRun
        self.job_run.update_context(step_name, output)

    def has(self, key: str) -> bool:
        """Vérifie si une clé existe dans le contexte."""
        return key in self._data

    def has_step_output(self, step_name: str) -> bool:
        """Vérifie si une step a une sortie."""
        return step_name in self._step_outputs

    def keys(self) -> Iterator[str]:
        """Itère sur les clés du contexte."""
        return iter(self._data.keys())

    def step_names(self) -> Iterator[str]:
        """Itère sur les noms des steps qui ont des sorties."""
        return iter(self._step_outputs.keys())

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Récupère une métadonnée du contexte."""
        return self._metadata.get(key, default)

    def set_metadata(self, key: str, value: Any) -> None:
        """Définit une métadonnée du contexte.

        Les métadonnées peuvent être modifiées même si le contexte est gelé.
        """
        self._metadata[key] = value

    def freeze(self) -> None:
        """Gèle le contexte en lecture seule.

        Après gel, les opérations set() et set_step_output() lèveront
        une exception. Les métadonnées restent modifiables.
        """
        self._frozen = True

    def unfreeze(self) -> None:
        """Dégèle le contexte pour permettre les modifications."""
        self._frozen = False

    @property
    def is_frozen(self) -> bool:
        """Vérifie si le contexte est gelé."""
        return self._frozen

    def to_dict(self) -> Dict[str, Any]:
        """Exporte le contexte vers un dictionnaire.

        Utile pour la sérialisation et le debugging.

        Returns:
            Dictionnaire contenant toutes les données du contexte.
        """
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
        """Crée une copie du contexte.

        La copie est indépendante mais partage la même référence JobRun.
        Utile pour créer des contextes isolés pour des sub-workflows.

        Returns:
            Nouvelle instance WorkflowContext avec les mêmes données.
        """
        new_context = WorkflowContext(self.job_run)
        new_context._data = copy.deepcopy(self._data)
        new_context._step_outputs = copy.deepcopy(self._step_outputs)
        new_context._metadata = copy.deepcopy(self._metadata)
        new_context._frozen = self._frozen
        return new_context

    def merge_from(self, other: WorkflowContext, overwrite: bool = False) -> None:
        """Fusionne les données d'un autre contexte.

        Args:
            other: Contexte source pour la fusion.
            overwrite: Si True, écrase les clés existantes.

        Raises:
            ContextError: Si le contexte est gelé.
        """
        if self._frozen:
            raise ContextError(
                "Cannot merge into frozen context",
                context_operation="merge",
                job_name=self.job_run.job_name,
            )

        # Fusionner les données
        for key, value in other._data.items():
            if overwrite or key not in self._data:
                self._data[key] = copy.deepcopy(value)

        # Fusionner les sorties de steps
        for step_name, output in other._step_outputs.items():
            if overwrite or step_name not in self._step_outputs:
                self.set_step_output(step_name, copy.deepcopy(output))

        # Fusionner les métadonnées
        for key, value in other._metadata.items():
            if overwrite or key not in self._metadata:
                self._metadata[key] = copy.deepcopy(value)

    def clear(self) -> None:
        """Vide le contexte de toutes ses données.

        Raises:
            ContextError: Si le contexte est gelé.
        """
        if self._frozen:
            raise ContextError(
                "Cannot clear frozen context",
                context_operation="clear",
                job_name=self.job_run.job_name,
            )

        self._data.clear()
        self._step_outputs.clear()
        self._metadata.clear()

    def get_step_run(self, step_name: str) -> Optional[StepRun]:
        """Récupère le StepRun d'une step par son nom.

        Args:
            step_name: Nom de la step.

        Returns:
            StepRun correspondant ou None si non trouvé.
        """
        return self.job_run.get_step_run(step_name)

    def get_completed_steps(self) -> List[str]:
        """Récupère la liste des steps complétées avec succès.

        Returns:
            Liste des noms de steps complétées.
        """
        from .models import RunStatus

        completed_runs = self.job_run.get_step_runs_by_status(RunStatus.SUCCESS)
        return [run.step_name for run in completed_runs]

    def get_failed_steps(self) -> List[str]:
        """Récupère la liste des steps échouées.

        Returns:
            Liste des noms de steps échouées.
        """
        from .models import RunStatus

        failed_runs = self.job_run.get_step_runs_by_status(RunStatus.FAILED)
        return [run.step_name for run in failed_runs]

    def get_all_outputs(self) -> Dict[str, Any]:
        """Récupère toutes les sorties des steps.

        Returns:
            Dictionnaire {step_name: output} de toutes les sorties.
        """
        return copy.deepcopy(self._step_outputs)

    def __contains__(self, key: str) -> bool:
        """Support de l'opérateur 'in' pour vérifier les clés."""
        return self.has(key)

    def __getitem__(self, key: str) -> Any:
        """Support de l'accès par crochets context[key]."""
        if not self.has(key):
            raise KeyError(f"Context key '{key}' not found")
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Support de l'assignation par crochets context[key] = value."""
        self.set(key, value)

    def __repr__(self) -> str:
        """Représentation string pour le debugging."""
        return (
            f"WorkflowContext(job_run_id={self.job_run.job_run_id[:8]}..., "
            f"data_keys={list(self._data.keys())}, "
            f"step_outputs={list(self._step_outputs.keys())}, "
            f"frozen={self._frozen})"
        )
