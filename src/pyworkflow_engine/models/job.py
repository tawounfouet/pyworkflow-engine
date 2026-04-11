"""
Modèle design-time du workflow — Job.

Représente la *définition complète* d'un workflow avec ses étapes,
ses déclencheurs, et sa configuration. Immuable et auto-sérialisable.

Utilise ``dataclasses`` de la stdlib — zéro dépendance externe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .enums import ExecutorType, Priority, TriggerType
from .step import Step, SubJob


@dataclass(frozen=True)
class Job:
    """Définition d'un workflow complet.

    Un Job représente la définition complète d'un workflow avec ses étapes,
    ses déclencheurs, et sa configuration d'exécution.

    Attributes:
        name: Nom unique du workflow.
        description: Description textuelle du workflow.
        steps: Liste des étapes du workflow.
        sub_jobs: Liste des sous-workflows.
        triggers: Types de déclencheurs acceptés.
        default_executor: Executor par défaut pour les steps.
        priority: Priorité d'exécution.
        timeout: Timeout global du workflow.
        max_concurrent_steps: Nombre maximum d'étapes concurrentes.
        input_schema: Schéma JSON des paramètres d'entrée attendus.
        output_schema: Schéma JSON des sorties produites.
        tags: Tags pour catégorisation et recherche.
        metadata: Métadonnées additionnelles.
        version: Version de la définition du workflow.
        enabled: Si False, le workflow ne peut pas être exécuté.

    Examples:
        >>> job = Job(
        ...     name="etl_pipeline",
        ...     steps=[Step("extract", StepType.FUNCTION, handler=fn)]
        ... )
        >>> d = job.to_dict()
        >>> restored = Job.from_dict(d)  # handlers=None après désérialisation
    """

    name: str
    description: str = ""
    steps: list[Step] = field(default_factory=list)
    sub_jobs: list[SubJob] = field(default_factory=list)
    triggers: list[TriggerType] = field(default_factory=lambda: [TriggerType.MANUAL])
    default_executor: ExecutorType = ExecutorType.LOCAL
    priority: Priority = Priority.NORMAL
    timeout: timedelta | None = None
    max_concurrent_steps: int = 10
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validation après initialisation."""
        if not self.name:
            raise ValueError("Job name cannot be empty")
        if not self.name.replace("_", "").replace("-", "").replace(" ", "").isalnum():
            raise ValueError(
                "Job name must contain only alphanumeric characters, spaces, _ and -"
            )
        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("Step names must be unique within a job")
        for step in self.steps:
            for dep in step.dependencies:
                if dep not in step_names:
                    raise ValueError(
                        f"Step '{step.name}': dependency '{dep}' not found"
                    )
        if self.max_concurrent_steps <= 0:
            raise ValueError("max_concurrent_steps must be positive")

    # ------------------------------------------------------------------
    # Graph helpers
    # ------------------------------------------------------------------

    def get_step(self, name: str) -> Step | None:
        """Récupère une étape par son nom."""
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def get_dependencies(self, step_name: str) -> list[str]:
        """Récupère les dépendances d'une étape."""
        step = self.get_step(step_name)
        return step.dependencies if step else []

    def get_dependents(self, step_name: str) -> list[str]:
        """Récupère les étapes qui dépendent de cette étape."""
        return [s.name for s in self.steps if step_name in s.dependencies]

    def get_exit_steps(self) -> list[str]:
        """Étapes sans dépendants (points de sortie du graphe)."""
        return [s.name for s in self.steps if not self.get_dependents(s.name)]

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible."""
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "sub_jobs": [sj.to_dict() for sj in self.sub_jobs],
            "triggers": [t.value for t in self.triggers],
            "default_executor": self.default_executor.value,
            "priority": self.priority.value,
            "timeout": (
                self.timeout.total_seconds() if self.timeout is not None else None
            ),
            "max_concurrent_steps": self.max_concurrent_steps,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "version": self.version,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Désérialise depuis un dict. Les callables des Steps sont ``None``."""
        timeout_secs = data.get("timeout")
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            steps=[Step.from_dict(s) for s in data.get("steps", [])],
            sub_jobs=[SubJob.from_dict(sj) for sj in data.get("sub_jobs", [])],
            triggers=[
                TriggerType(t) for t in data.get("triggers", [TriggerType.MANUAL.value])
            ],
            default_executor=ExecutorType(
                data.get("default_executor", ExecutorType.LOCAL.value)
            ),
            priority=Priority(data.get("priority", Priority.NORMAL.value)),
            timeout=(
                timedelta(seconds=timeout_secs) if timeout_secs is not None else None
            ),
            max_concurrent_steps=data.get("max_concurrent_steps", 10),
            input_schema=data.get("input_schema"),
            output_schema=data.get("output_schema"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            version=data.get("version", "1.0.0"),
            enabled=data.get("enabled", True),
        )
