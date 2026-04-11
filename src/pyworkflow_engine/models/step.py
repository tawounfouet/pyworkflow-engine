"""
Modèles design-time des étapes — Step et SubJob.

Ces modèles représentent la *définition* des étapes d'un workflow avant
son exécution. Ils sont immuables (frozen dataclasses) et auto-sérialisables.

Utilise ``dataclasses`` de la stdlib — zéro dépendance externe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from .enums import ExecutorType, StepType


@dataclass(frozen=True)
class Step:
    """Définition d'une étape de workflow.

    Une Step représente une unité d'exécution dans un workflow.
    Elle peut être une fonction Python, un appel HTTP, une tâche humaine, etc.

    Attributes:
        name: Nom unique de l'étape dans le workflow.
        step_type: Type d'étape déterminant le comportement d'exécution.
        handler: Fonction Python à exécuter (pour StepType.FUNCTION).
        callable: Alias déprécié pour ``handler``. Utilisez ``handler``.
        config: Configuration spécifique au type d'étape.
        dependencies: Noms des étapes dont celle-ci dépend.
        executor_type: Type d'executor à utiliser pour l'exécution.
        timeout: Timeout d'exécution (None = pas de timeout).
        retry_count: Nombre de tentatives en cas d'échec.
        retry_delay: Délai entre les tentatives.
        condition: Fonction de condition pour exécution conditionnelle.
        metadata: Métadonnées additionnelles.

    Examples:
        >>> def hello():
        ...     return {"message": "Hello World!"}
        >>>
        >>> step = Step(name="say_hello", step_type=StepType.FUNCTION, handler=hello)
        >>> d = step.to_dict()
        >>> restored = Step.from_dict(d)  # handler=None après désérialisation
    """

    name: str
    step_type: StepType
    handler: Callable | None = None
    config: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    executor_type: ExecutorType = ExecutorType.LOCAL
    timeout: timedelta | None = None
    retry_count: int = 0
    retry_delay: timedelta = field(default=timedelta(seconds=1))
    condition: Callable[[dict[str, Any]], bool] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validation après initialisation."""
        if self.retry_count < 0:
            raise ValueError(f"Step '{self.name}': retry_count must be >= 0")
        if self.name in self.dependencies:
            raise ValueError(f"Step '{self.name}': cannot depend on itself")

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible.

        Le handler est volontairement exclu (non portable).
        Une représentation string est conservée pour le debug uniquement.
        """
        handler_repr = str(self.handler) if self.handler is not None else None
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "handler": handler_repr,
            "config": dict(self.config),
            "dependencies": list(self.dependencies),
            "executor_type": self.executor_type.value,
            "timeout": (
                self.timeout.total_seconds() if self.timeout is not None else None
            ),
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay.total_seconds(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        """Désérialise depuis un dict.

        ``handler`` est toujours ``None`` après désérialisation (non restaurable).
        """
        timeout_secs = data.get("timeout")
        retry_delay_secs = data.get("retry_delay", 1.0)
        return cls(
            name=data["name"],
            step_type=StepType(data["step_type"]),
            handler=None,  # Non restaurable depuis la persistence
            config=data.get("config", {}),
            dependencies=data.get("dependencies", []),
            executor_type=ExecutorType(
                data.get("executor_type", ExecutorType.LOCAL.value)
            ),
            timeout=(
                timedelta(seconds=timeout_secs) if timeout_secs is not None else None
            ),
            retry_count=data.get("retry_count", 0),
            retry_delay=timedelta(seconds=retry_delay_secs),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class SubJob:
    """Référence à un sous-workflow.

    Permet d'imbriquer des workflows pour créer des compositions complexes.

    Attributes:
        job_name: Nom du job à exécuter en tant que sous-workflow.
        input_mapping: Mapping des sorties du workflow parent vers les entrées du sous-job.
        output_mapping: Mapping des sorties du sous-job vers le workflow parent.
        inherit_context: Si True, le sous-job hérite du contexte parent.

    Examples:
        >>> sub_job = SubJob(
        ...     job_name="data_processing_pipeline",
        ...     input_mapping={"data": "processed_data"},
        ...     output_mapping={"result": "final_result"}
        ... )
        >>> sub_job.to_dict()
    """

    job_name: str
    input_mapping: dict[str, str] = field(default_factory=dict)
    output_mapping: dict[str, str] = field(default_factory=dict)
    inherit_context: bool = True

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible."""
        return {
            "job_name": self.job_name,
            "input_mapping": dict(self.input_mapping),
            "output_mapping": dict(self.output_mapping),
            "inherit_context": self.inherit_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubJob:
        """Désérialise depuis un dict."""
        return cls(
            job_name=data["job_name"],
            input_mapping=data.get("input_mapping", {}),
            output_mapping=data.get("output_mapping", {}),
            inherit_context=data.get("inherit_context", True),
        )
