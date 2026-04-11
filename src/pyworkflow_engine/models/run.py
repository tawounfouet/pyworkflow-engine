"""
Modèles runtime — instances d'exécution de workflows.

StepLog, StepRun et JobRun représentent l'*exécution* d'un workflow.
Ces objets sont mutables (mise à jour des états en cours d'exécution)
et auto-sérialisables via ``to_dict()`` / ``from_dict()``.

Utilise ``dataclasses`` de la stdlib — zéro dépendance externe.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .enums import ExecutorType, RunStatus, can_resume, is_suspended, is_terminal

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """Retourne l'heure UTC actuelle."""
    return datetime.now(UTC)


def generate_id() -> str:
    """Génère un identifiant UUID4 unique."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# StepLog
# ---------------------------------------------------------------------------


@dataclass
class StepLog:
    """Log d'exécution d'une étape.

    Attributes:
        timestamp: Horodatage du log.
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        message: Message de log.
        data: Données additionnelles structurées.
        source: Source du log (système, step, executor, etc.).

    Examples:
        >>> log = StepLog(timestamp=utc_now(), level="INFO", message="Done")
        >>> d = log.to_dict()
        >>> restored = StepLog.from_dict(d)
    """

    timestamp: datetime
    level: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "step"

    _VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

    def __post_init__(self) -> None:
        if self.level not in self._VALID_LEVELS:
            raise ValueError(f"Invalid log level: {self.level!r}")

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "data": self.data,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepLog:
        """Désérialise depuis un dict."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            level=data["level"],
            message=data["message"],
            data=data.get("data", {}),
            source=data.get("source", "step"),
        )


# ---------------------------------------------------------------------------
# StepRun
# ---------------------------------------------------------------------------


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
        >>> step_run = StepRun(step_name="process_data", job_run_id="job-123")
        >>> step_run.start_execution()
        >>> step_run.complete_success({"result": "processed"})
        >>> d = step_run.to_dict()
        >>> restored = StepRun.from_dict(d)
    """

    step_run_id: str = field(default_factory=generate_id)
    step_name: str = ""
    job_run_id: str = ""
    status: RunStatus = RunStatus.PENDING
    executor_type: ExecutorType = ExecutorType.LOCAL
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    executor_info: dict[str, Any] = field(default_factory=dict)
    logs: list[StepLog] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def start_execution(self) -> None:
        """Marque le début de l'exécution."""
        self.status = RunStatus.RUNNING
        self.start_time = utc_now()
        self.add_log("INFO", f"Starting execution of step '{self.step_name}'")

    def complete_success(self, output_data: dict[str, Any]) -> None:
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

    def mark_timeout(self) -> None:
        """Marque l'exécution comme timeout."""
        self.status = RunStatus.TIMEOUT
        self.end_time = utc_now()
        self._calculate_duration()
        self.add_log("ERROR", f"Step '{self.step_name}' timed out")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def add_log(
        self, level: str, message: str, data: dict[str, Any] | None = None
    ) -> None:
        """Ajoute un log à l'exécution."""
        self.logs.append(
            StepLog(
                timestamp=utc_now(),
                level=level,
                message=message,
                data=data or {},
                source=f"step:{self.step_name}",
            )
        )

    def _calculate_duration(self) -> None:
        if self.start_time and self.end_time:
            self.duration_ms = int(
                (self.end_time - self.start_time).total_seconds() * 1000
            )

    @property
    def is_terminal(self) -> bool:
        return is_terminal(self.status)

    @property
    def is_suspended(self) -> bool:
        return is_suspended(self.status)

    @property
    def can_resume(self) -> bool:
        return can_resume(self.status)

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible."""
        return {
            "step_run_id": self.step_run_id,
            "job_run_id": self.job_run_id,
            "step_name": self.step_name,
            "status": self.status.value,
            "executor_type": self.executor_type.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error": self.error,
            "start_time": (
                self.start_time.isoformat() if self.start_time is not None else None
            ),
            "end_time": (
                self.end_time.isoformat() if self.end_time is not None else None
            ),
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "executor_info": self.executor_info,
            "logs": [log.to_dict() for log in self.logs],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepRun:
        """Désérialise depuis un dict."""
        return cls(
            step_run_id=data["step_run_id"],
            step_name=data["step_name"],
            job_run_id=data["job_run_id"],
            status=RunStatus(data["status"]),
            executor_type=ExecutorType(
                data.get("executor_type", ExecutorType.LOCAL.value)
            ),
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data", {}),
            error=data.get("error"),
            start_time=(
                datetime.fromisoformat(data["start_time"])
                if data.get("start_time")
                else None
            ),
            end_time=(
                datetime.fromisoformat(data["end_time"])
                if data.get("end_time")
                else None
            ),
            duration_ms=data.get("duration_ms"),
            retry_count=data.get("retry_count", 0),
            executor_info=data.get("executor_info", {}),
            logs=[StepLog.from_dict(log) for log in data.get("logs", [])],
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# JobRun
# ---------------------------------------------------------------------------


@dataclass
class JobRun:
    """Instance d'exécution d'un workflow complet.

    Représente l'exécution actuelle ou passée d'un Job avec toutes ses étapes.
    Mutable pour permettre la mise à jour des états pendant l'exécution.

    Attributes:
        job_run_id: ID unique de cette exécution.
        job: Définition du Job (optionnelle, non sérialisée).
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
        >>> job_run = JobRun(job_name="etl_pipeline")
        >>> job_run.start_execution()
        >>> job_run.complete_success({"processed_records": 1000})
        >>> d = job_run.to_dict()
        >>> restored = JobRun.from_dict(d)
    """

    job_run_id: str = field(default_factory=generate_id)
    job: Any = None  # Job definition — not serialized (callables not portable)
    job_name: str = ""
    job_version: str = "1.0.0"
    status: RunStatus = RunStatus.PENDING
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    step_runs: list[StepRun] = field(default_factory=list)
    error: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    triggered_by: str = "manual"
    trigger_data: dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # Priority.NORMAL.value
    executor_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def start_execution(self) -> None:
        """Marque le début de l'exécution du workflow."""
        self.status = RunStatus.RUNNING
        self.start_time = utc_now()
        self.updated_at = utc_now()

    def complete_success(self, output_data: dict[str, Any] | None = None) -> None:
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
        """Suspend l'exécution."""
        self.status = RunStatus.SUSPENDED
        self.updated_at = utc_now()
        self.metadata["suspend_reason"] = reason

    def cancel(self) -> None:
        """Annule l'exécution."""
        self.status = RunStatus.CANCELLED
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    def mark_timeout(self) -> None:
        """Marque l'exécution comme timeout."""
        self.status = RunStatus.TIMEOUT
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    # ------------------------------------------------------------------
    # Step run management
    # ------------------------------------------------------------------

    def add_step_run(self, step_run: StepRun) -> None:
        """Ajoute une exécution d'étape."""
        step_run.job_run_id = self.job_run_id
        self.step_runs.append(step_run)
        self.updated_at = utc_now()

    def get_step_run(self, step_name: str) -> StepRun | None:
        """Récupère une exécution d'étape par nom."""
        for sr in self.step_runs:
            if sr.step_name == step_name:
                return sr
        return None

    def get_step_runs_by_status(self, status: RunStatus) -> list[StepRun]:
        """Récupère les exécutions d'étapes par statut."""
        return [sr for sr in self.step_runs if sr.status == status]

    def get_completed_step_runs(self) -> list[StepRun]:
        return self.get_step_runs_by_status(RunStatus.SUCCESS)

    def get_failed_step_runs(self) -> list[StepRun]:
        return self.get_step_runs_by_status(RunStatus.FAILED)

    def update_context(self, step_name: str, output_data: dict[str, Any]) -> None:
        """Met à jour le contexte avec les sorties d'une étape."""
        self.context[step_name] = output_data
        self.updated_at = utc_now()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        """Alias for job_run_id."""
        return self.job_run_id

    @property
    def is_terminal(self) -> bool:
        return is_terminal(self.status)

    @property
    def is_suspended(self) -> bool:
        return is_suspended(self.status)

    @property
    def can_resume(self) -> bool:
        return can_resume(self.status)

    @property
    def progress_percentage(self) -> float:
        """Pourcentage de progression basé sur les étapes terminées."""
        if not self.step_runs:
            return 0.0
        completed = sum(1 for sr in self.step_runs if sr.is_terminal)
        return (completed / len(self.step_runs)) * 100.0

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible.

        Note : ``job`` (la définition Job) n'est pas sérialisé
        (callables non portables).
        """
        return {
            "job_run_id": self.job_run_id,
            "job_name": self.job_name,
            "job_version": self.job_version,
            "status": self.status.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "context": self.context,
            "error": self.error,
            "start_time": (
                self.start_time.isoformat() if self.start_time is not None else None
            ),
            "end_time": (
                self.end_time.isoformat() if self.end_time is not None else None
            ),
            "duration_ms": self.duration_ms,
            "triggered_by": self.triggered_by,
            "trigger_data": self.trigger_data,
            "priority": self.priority,
            "executor_config": self.executor_config,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "step_runs": [sr.to_dict() for sr in self.step_runs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobRun:
        """Désérialise depuis un dict. ``job`` sera ``None``."""
        return cls(
            job_run_id=data["job_run_id"],
            job_name=data["job_name"],
            job_version=data.get("job_version", "1.0.0"),
            status=RunStatus(data["status"]),
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data", {}),
            context=data.get("context", {}),
            error=data.get("error"),
            start_time=(
                datetime.fromisoformat(data["start_time"])
                if data.get("start_time")
                else None
            ),
            end_time=(
                datetime.fromisoformat(data["end_time"])
                if data.get("end_time")
                else None
            ),
            duration_ms=data.get("duration_ms"),
            triggered_by=data.get("triggered_by", "manual"),
            trigger_data=data.get("trigger_data", {}),
            priority=data.get("priority", 5),
            executor_config=data.get("executor_config", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            step_runs=[StepRun.from_dict(sr) for sr in data.get("step_runs", [])],
        )

    def _calculate_duration(self) -> None:
        if self.start_time and self.end_time:
            self.duration_ms = int(
                (self.end_time - self.start_time).total_seconds() * 1000
            )
