"""
Modèles runtime — instances d'exécution de workflows (dataclasses pures).

Ces modèles représentent l'*exécution* d'un workflow en cours ou terminée.
Ils trackent l'état, les résultats, et les métriques d'exécution.

Utilise ``dataclasses`` de la stdlib — zero dépendance externe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
import uuid

from .enums import RunStatus, ExecutorType
from .design_time import Job, Step


def utc_now() -> datetime:
    """Retourne l'heure UTC actuelle."""
    return datetime.now(timezone.utc)


def generate_id() -> str:
    """Génère un ID unique pour les runs."""
    return str(uuid.uuid4())


@dataclass
class StepLog:
    """Log d'exécution d'une étape.

    Capture les informations de logging pendant l'exécution d'une étape.

    Attributes:
        timestamp: Horodatage du log.
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        message: Message de log.
        data: Données additionnelles structurées.
        source: Source du log (système, step, executor, etc.).
    """

    timestamp: datetime
    level: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = "step"

    def __post_init__(self):
        """Validation après initialisation."""
        if self.level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid log level: {self.level}")


@dataclass
class StepRun:
    """Instance d'exécution d'une étape.

    Représente l'exécution actuelle ou passée d'une Step dans un workflow.
    Mutable pour permettre la mise à jour des états pendant l'exécution.

    Attributes:
        step_run_id: ID unique de cette exécution d'étape.
        step_name: Nom de l'étape correspondante.
        job_run_id: ID du JobRun parent.
        status: État actuel de l'exécution.
        executor_type: Type d'executor utilisé.
        input_data: Données d'entrée de l'étape.
        output_data: Données de sortie produites.
        error: Information d'erreur en cas d'échec.
        start_time: Heure de début d'exécution.
        end_time: Heure de fin d'exécution.
        duration_ms: Durée d'exécution en millisecondes.
        retry_count: Nombre de tentatives effectuées.
        executor_info: Informations sur l'executor utilisé.
        logs: Liste des logs d'exécution.
        metadata: Métadonnées additionnelles.

    Examples:
        >>> step_run = StepRun(
        ...     step_name="process_data",
        ...     job_run_id="job-123"
        ... )
        >>> step_run.start_execution()
        >>> # ... exécution ...
        >>> step_run.complete_success({"result": "processed"})
    """

    step_run_id: str = field(default_factory=generate_id)
    step_name: str = ""
    job_run_id: str = ""
    status: RunStatus = RunStatus.PENDING
    executor_type: ExecutorType = ExecutorType.LOCAL
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    retry_count: int = 0
    executor_info: Dict[str, Any] = field(default_factory=dict)
    logs: List[StepLog] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def start_execution(self) -> None:
        """Marque le début de l'exécution."""
        self.status = RunStatus.RUNNING
        self.start_time = utc_now()
        self.add_log("INFO", f"Starting execution of step '{self.step_name}'")

    def complete_success(self, output_data: Dict[str, Any]) -> None:
        """Marque l'exécution comme réussie."""
        self.status = RunStatus.SUCCESS
        self.output_data = output_data
        self.end_time = utc_now()
        self._calculate_duration()
        self.add_log("INFO", f"Step '{self.step_name}' completed successfully")

    def complete_failure(self, error: str) -> None:
        """Marque l'exécution comme échouée."""
        self.status = RunStatus.FAILED
        self.error = error
        self.end_time = utc_now()
        self._calculate_duration()
        self.add_log("ERROR", f"Step '{self.step_name}' failed: {error}")

    def suspend(self, reason: str) -> None:
        """Suspend l'exécution avec une raison."""
        self.status = RunStatus.SUSPENDED
        self.add_log("WARNING", f"Step '{self.step_name}' suspended: {reason}")

    def wait_human(self, reason: str) -> None:
        """Met en attente d'intervention humaine."""
        self.status = RunStatus.WAITING_HUMAN
        self.add_log("INFO", f"Step '{self.step_name}' waiting for human: {reason}")

    def wait_external(self, reason: str) -> None:
        """Met en attente de système externe."""
        self.status = RunStatus.WAITING_EXTERNAL
        self.add_log("INFO", f"Step '{self.step_name}' waiting for external: {reason}")

    def cancel(self) -> None:
        """Annule l'exécution."""
        self.status = RunStatus.CANCELLED
        self.end_time = utc_now()
        self._calculate_duration()
        self.add_log("WARNING", f"Step '{self.step_name}' cancelled")

    def timeout(self) -> None:
        """Marque l'exécution comme timeout."""
        self.status = RunStatus.TIMEOUT
        self.end_time = utc_now()
        self._calculate_duration()
        self.add_log("ERROR", f"Step '{self.step_name}' timed out")

    def add_log(
        self, level: str, message: str, data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Ajoute un log à l'exécution."""
        log = StepLog(
            timestamp=utc_now(),
            level=level,
            message=message,
            data=data or {},
            source=f"step:{self.step_name}",
        )
        self.logs.append(log)

    def _calculate_duration(self) -> None:
        """Calcule la durée d'exécution."""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            self.duration_ms = int(delta.total_seconds() * 1000)

    @property
    def is_terminal(self) -> bool:
        """Vérifie si l'exécution est dans un état terminal."""
        from .enums import is_terminal

        return is_terminal(self.status)

    @property
    def is_suspended(self) -> bool:
        """Vérifie si l'exécution est suspendue."""
        from .enums import is_suspended

        return is_suspended(self.status)

    @property
    def can_resume(self) -> bool:
        """Vérifie si l'exécution peut être reprise."""
        from .enums import can_resume

        return can_resume(self.status)


@dataclass
class JobRun:
    """Instance d'exécution d'un workflow complet.

    Représente l'exécution actuelle ou passée d'un Job avec toutes ses étapes.
    Mutable pour permettre la mise à jour des états pendant l'exécution.

    Attributes:
        job_run_id: ID unique de cette exécution de workflow.
        job_name: Nom du job correspondant.
        job_version: Version du job au moment de l'exécution.
        status: État global du workflow.
        input_data: Données d'entrée du workflow.
        output_data: Données de sortie finales.
        context: Contexte partagé entre les étapes.
        step_runs: Liste des exécutions d'étapes.
        error: Information d'erreur globale.
        start_time: Heure de début du workflow.
        end_time: Heure de fin du workflow.
        duration_ms: Durée totale en millisecondes.
        triggered_by: Source du déclenchement.
        trigger_data: Données du déclenchement.
        priority: Priorité d'exécution.
        executor_config: Configuration des executors.
        metadata: Métadonnées additionnelles.
        created_at: Heure de création du run.
        updated_at: Heure de dernière mise à jour.

    Examples:
        >>> job_run = JobRun(
        ...     job_name="etl_pipeline",
        ...     input_data={"source": "customers.csv"}
        ... )
        >>> job_run.start_execution()
        >>> # ... ajout et exécution des steps ...
        >>> job_run.complete_success({"processed_records": 1000})
    """

    job_run_id: str = field(default_factory=generate_id)
    job: Optional[Job] = None  # Job definition for this run
    job_name: str = ""
    job_version: str = "1.0.0"
    status: RunStatus = RunStatus.PENDING
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    step_runs: List[StepRun] = field(default_factory=list)
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    triggered_by: str = "manual"
    trigger_data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # Priority.NORMAL.value
    executor_config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def start_execution(self) -> None:
        """Marque le début de l'exécution du workflow."""
        self.status = RunStatus.RUNNING
        self.start_time = utc_now()
        self.updated_at = utc_now()

    def complete_success(self, output_data: Optional[Dict[str, Any]] = None) -> None:
        """Marque l'exécution comme réussie."""
        self.status = RunStatus.SUCCESS
        if output_data:
            self.output_data = output_data
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    def complete_failure(self, error: str) -> None:
        """Marque l'exécution comme échouée."""
        self.status = RunStatus.FAILED
        self.error = error
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    def suspend(self, reason: str) -> None:
        """Suspend l'exécution avec une raison."""
        self.status = RunStatus.SUSPENDED
        self.updated_at = utc_now()
        # Le reason peut être stocké dans metadata
        self.metadata["suspend_reason"] = reason

    def cancel(self) -> None:
        """Annule l'exécution."""
        self.status = RunStatus.CANCELLED
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    def timeout(self) -> None:
        """Marque l'exécution comme timeout."""
        self.status = RunStatus.TIMEOUT
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    def add_step_run(self, step_run: StepRun) -> None:
        """Ajoute une exécution d'étape."""
        step_run.job_run_id = self.job_run_id
        self.step_runs.append(step_run)
        self.updated_at = utc_now()

    def get_step_run(self, step_name: str) -> Optional[StepRun]:
        """Récupère une exécution d'étape par nom."""
        for step_run in self.step_runs:
            if step_run.step_name == step_name:
                return step_run
        return None

    def get_step_runs_by_status(self, status: RunStatus) -> List[StepRun]:
        """Récupère les exécutions d'étapes par statut."""
        return [sr for sr in self.step_runs if sr.status == status]

    def get_completed_step_runs(self) -> List[StepRun]:
        """Récupère les exécutions d'étapes terminées avec succès."""
        return self.get_step_runs_by_status(RunStatus.SUCCESS)

    def get_failed_step_runs(self) -> List[StepRun]:
        """Récupère les exécutions d'étapes échouées."""
        return self.get_step_runs_by_status(RunStatus.FAILED)

    def update_context(self, step_name: str, output_data: Dict[str, Any]) -> None:
        """Met à jour le contexte avec les sorties d'une étape."""
        self.context[step_name] = output_data
        self.updated_at = utc_now()

    def _calculate_duration(self) -> None:
        """Calcule la durée totale d'exécution."""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            self.duration_ms = int(delta.total_seconds() * 1000)

    @property
    def is_terminal(self) -> bool:
        """Vérifie si l'exécution est dans un état terminal."""
        from .enums import is_terminal

        return is_terminal(self.status)

    @property
    def is_suspended(self) -> bool:
        """Vérifie si l'exécution est suspendue."""
        from .enums import is_suspended

        return is_suspended(self.status)

    @property
    def can_resume(self) -> bool:
        """Vérifie si l'exécution peut être reprise."""
        from .enums import can_resume

        return can_resume(self.status)

    @property
    def progress_percentage(self) -> float:
        """Calcule le pourcentage de progression basé sur les étapes terminées."""
        if not self.step_runs:
            return 0.0

        completed = len([sr for sr in self.step_runs if sr.is_terminal])
        return (completed / len(self.step_runs)) * 100.0
