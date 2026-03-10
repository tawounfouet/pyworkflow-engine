"""
Modèles design-time — définitions de workflows (dataclasses pures).

Ces modèles représentent la *définition* d'un workflow avant son exécution.
Ils sont immuables et sérialisables.

Utilise ``dataclasses`` de la stdlib — zero dépendance externe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict, List, Union
from datetime import timedelta

from .enums import TriggerType, StepType, ExecutorType, Priority


@dataclass(frozen=True)
class Step:
    """Définition d'une étape de workflow.

    Une Step représente une unité d'exécution dans un workflow.
    Elle peut être une fonction Python, un appel HTTP, une tâche humaine, etc.

    Attributes:
        name: Nom unique de l'étape dans le workflow.
        step_type: Type d'étape déterminant le comportement d'exécution.
        callable: Fonction Python à exécuter (pour StepType.FUNCTION).
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
        >>> step = Step(
        ...     name="say_hello",
        ...     step_type=StepType.FUNCTION,
        ...     callable=hello
        ... )
        >>>
        >>> # Step avec dépendances
        >>> process_step = Step(
        ...     name="process_data",
        ...     step_type=StepType.FUNCTION,
        ...     callable=process_data,
        ...     dependencies=["say_hello"]
        ... )
    """

    name: str
    step_type: StepType
    callable: Optional[Callable] = None
    config: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    executor_type: ExecutorType = ExecutorType.LOCAL
    timeout: Optional[timedelta] = None
    retry_count: int = 0
    retry_delay: timedelta = field(default=timedelta(seconds=1))
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validation après initialisation."""
        if self.step_type == StepType.FUNCTION and self.callable is None:
            raise ValueError(f"Step '{self.name}': StepType.FUNCTION requires callable")

        if self.retry_count < 0:
            raise ValueError(f"Step '{self.name}': retry_count must be >= 0")

        # Vérifier que les dépendances ne sont pas circulaires (check basique)
        if self.name in self.dependencies:
            raise ValueError(f"Step '{self.name}': cannot depend on itself")


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
    """

    job_name: str
    input_mapping: Dict[str, str] = field(default_factory=dict)
    output_mapping: Dict[str, str] = field(default_factory=dict)
    inherit_context: bool = True


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
        >>> def extract_data():
        ...     return {"data": [1, 2, 3]}
        >>>
        >>> def transform_data(context):
        ...     data = context["extract_data"]["data"]
        ...     return {"transformed": [x * 2 for x in data]}
        >>>
        >>> job = Job(
        ...     name="etl_pipeline",
        ...     description="Simple ETL pipeline",
        ...     steps=[
        ...         Step("extract", StepType.FUNCTION, callable=extract_data),
        ...         Step("transform", StepType.FUNCTION, callable=transform_data,
        ...              dependencies=["extract"])
        ...     ]
        ... )
    """

    name: str
    description: str = ""
    steps: List[Step] = field(default_factory=list)
    sub_jobs: List[SubJob] = field(default_factory=list)
    triggers: List[TriggerType] = field(default_factory=lambda: [TriggerType.MANUAL])
    default_executor: ExecutorType = ExecutorType.LOCAL
    priority: Priority = Priority.NORMAL
    timeout: Optional[timedelta] = None
    max_concurrent_steps: int = 10
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    enabled: bool = True

    def __post_init__(self):
        """Validation après initialisation."""
        if not self.name:
            raise ValueError("Job name cannot be empty")

        if not self.name.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Job name must be alphanumeric (with _ and - allowed)")

        # Vérifier l'unicité des noms de steps
        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("Step names must be unique within a job")

        # Vérifier que toutes les dépendances existent
        for step in self.steps:
            for dep in step.dependencies:
                if dep not in step_names:
                    raise ValueError(
                        f"Step '{step.name}': dependency '{dep}' not found"
                    )

        if self.max_concurrent_steps <= 0:
            raise ValueError("max_concurrent_steps must be positive")

    def get_step(self, name: str) -> Optional[Step]:
        """Récupère une étape par son nom."""
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def get_dependencies(self, step_name: str) -> List[str]:
        """Récupère les dépendances d'une étape."""
        step = self.get_step(step_name)
        return step.dependencies if step else []

    def get_dependents(self, step_name: str) -> List[str]:
        """Récupère les étapes qui dépendent de cette étape."""
        dependents = []
        for step in self.steps:
            if step_name in step.dependencies:
                dependents.append(step.name)
        return dependents

    def has_cycles(self) -> bool:
        """Vérifie s'il y a des cycles dans le graphe de dépendances.

        Utilise un algorithme de détection de cycle basique.
        """
        # Algorithme DFS pour détecter les cycles
        visited = set()
        rec_stack = set()

        def has_cycle_util(step_name: str) -> bool:
            visited.add(step_name)
            rec_stack.add(step_name)

            for dep in self.get_dependents(step_name):
                if dep not in visited:
                    if has_cycle_util(dep):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(step_name)
            return False

        for step in self.steps:
            if step.name not in visited:
                if has_cycle_util(step.name):
                    return True

        return False

    def get_entry_steps(self) -> List[str]:
        """Récupère les étapes sans dépendances (points d'entrée)."""
        return [step.name for step in self.steps if not step.dependencies]

    def get_exit_steps(self) -> List[str]:
        """Récupère les étapes sans dépendants (points de sortie)."""
        return [step.name for step in self.steps if not self.get_dependents(step.name)]
