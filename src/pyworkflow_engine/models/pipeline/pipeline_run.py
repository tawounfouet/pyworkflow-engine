"""
Modèles runtime de la pipeline — PipelineRun et StageRun.

``PipelineRun`` et ``StageRun`` représentent l'*exécution* d'une pipeline.
Ces objets sont mutables (mise à jour des états en cours d'exécution)
et auto-sérialisables via ``to_dict()`` / ``from_dict()``.

Migration D2 (vague 2) — ADR-018 :
    - StageRun    → PersistableModel (table pl_stage_runs)
    - PipelineRun → PersistableModel (table pl_pipeline_runs)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import Field

from pyworkflow_engine.models.enums import (
    RunStatus,
    is_suspended,
    is_terminal,
)
from pyworkflow_engine.models.workflow.run import JobRun, generate_id, utc_now
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)

# ---------------------------------------------------------------------------
# StageRun  (vague 2 — PersistableModel, table pl_stage_runs)
# ---------------------------------------------------------------------------


@ModelRegistry.register
class StageRun(PersistableModel):
    """Instance d'exécution d'un stage = un Job dans la pipeline.

    Mutable : les transitions d'état, timestamps et le ``job_run`` sous-jacent
    sont mis à jour pendant l'exécution.

    Attributes:
        stage_run_id: Identifiant unique de cette exécution de stage (UUID4).
        pipeline_run_id: Identifiant du ``PipelineRun`` parent.
        job_name: Nom du Job correspondant au stage.
        stage_index: Position dans la pipeline (0-based).
        status: État actuel de l'exécution du stage.
        job_run: ``JobRun`` sous-jacent créé lors de l'exécution (non sérialisé
            directement — sérialisé via ``job_run.to_dict()``).
        skipped: ``True`` si le stage a été sauté (condition ``False`` ou
            ``enabled=False``).
        skip_reason: Raison du skip.
        error: Information d'erreur en cas d'échec.
        start_time: Heure de début d'exécution.
        end_time: Heure de fin d'exécution.
        duration_ms: Durée d'exécution en millisecondes.
        metadata: Métadonnées additionnelles.

    Examples:
        >>> stage_run = StageRun(job_name="ingestion", stage_index=0)
        >>> stage_run.start_execution()
        >>> stage_run.complete_success()
        >>> d = stage_run.to_dict()
        >>> restored = StageRun.from_dict(d)
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="pl_stage_runs",
        columns=[
            ColumnDef("stage_run_id", ColumnType.TEXT, primary_key=True),
            ColumnDef(
                "pipeline_run_id",
                ColumnType.TEXT,
                nullable=False,
                foreign_key="pl_pipeline_runs.pipeline_run_id",
            ),
            ColumnDef("job_name", ColumnType.TEXT, nullable=False),
            ColumnDef("stage_index", ColumnType.INTEGER, nullable=False),
            ColumnDef("status", ColumnType.TEXT, nullable=False),
            ColumnDef("skipped", ColumnType.BOOLEAN),
            ColumnDef("skip_reason", ColumnType.TEXT),
            ColumnDef("error", ColumnType.TEXT),
            ColumnDef("start_time", ColumnType.TIMESTAMP),
            ColumnDef("end_time", ColumnType.TIMESTAMP),
            ColumnDef("duration_ms", ColumnType.INTEGER),
            ColumnDef("metadata", ColumnType.JSON),
        ],
        indexes=[
            ("pipeline_run_id",),
            ("status",),
            ("pipeline_run_id", "stage_index"),
        ],
    )

    stage_run_id: str = Field(default_factory=generate_id)
    pipeline_run_id: str = ""
    job_name: str = ""
    stage_index: int = 0
    status: RunStatus = RunStatus.PENDING
    job_run: JobRun | None = Field(
        default=None, exclude=True
    )  # Not persisted in this table
    skipped: bool = False
    skip_reason: str = ""
    error: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def start_execution(self) -> None:
        """Marque le début de l'exécution du stage."""
        self.status = RunStatus.RUNNING
        self.start_time = utc_now()

    def complete_success(self) -> None:
        """Marque le stage comme terminé avec succès."""
        self.status = RunStatus.SUCCESS
        self.end_time = utc_now()
        self._calculate_duration()

    def complete_failure(self, error: str) -> None:
        """Marque le stage comme échoué."""
        self.status = RunStatus.FAILED
        self.error = error
        self.end_time = utc_now()
        self._calculate_duration()

    def mark_skipped(self, reason: str = "") -> None:
        """Marque le stage comme sauté (condition non remplie ou disabled)."""
        self.status = RunStatus.CANCELLED
        self.skipped = True
        self.skip_reason = reason
        self.end_time = utc_now()
        self._calculate_duration()

    def cancel(self) -> None:
        """Annule l'exécution du stage."""
        self.status = RunStatus.CANCELLED
        self.end_time = utc_now()
        self._calculate_duration()

    def mark_timeout(self) -> None:
        """Marque le stage comme timeout."""
        self.status = RunStatus.TIMEOUT
        self.end_time = utc_now()
        self._calculate_duration()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _calculate_duration(self) -> None:
        if self.start_time and self.end_time:
            self.duration_ms = int(
                (self.end_time - self.start_time).total_seconds() * 1000
            )

    @property
    def is_terminal(self) -> bool:
        """Vérifie si le stage est dans un état terminal."""
        return is_terminal(self.status)

    @property
    def is_suspended(self) -> bool:
        """Vérifie si le stage est suspendu."""
        return is_suspended(self.status)

    @property
    def duration_s(self) -> float:
        """Durée en secondes (0.0 si non calculée)."""
        return (self.duration_ms or 0) / 1000.0

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible."""
        return {
            "stage_run_id": self.stage_run_id,
            "pipeline_run_id": self.pipeline_run_id,
            "job_name": self.job_name,
            "stage_index": self.stage_index,
            "status": self.status.value,
            "job_run": self.job_run.to_dict() if self.job_run is not None else None,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "error": self.error,
            "start_time": (
                self.start_time.isoformat() if self.start_time is not None else None
            ),
            "end_time": (
                self.end_time.isoformat() if self.end_time is not None else None
            ),
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageRun:
        """Désérialise depuis un dict."""
        job_run_data = data.get("job_run")
        return cls(
            stage_run_id=data["stage_run_id"],
            pipeline_run_id=data.get("pipeline_run_id", ""),
            job_name=data.get("job_name", ""),
            stage_index=data.get("stage_index", 0),
            status=RunStatus(data["status"]),
            job_run=JobRun.from_dict(job_run_data) if job_run_data else None,
            skipped=data.get("skipped", False),
            skip_reason=data.get("skip_reason", ""),
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
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# PipelineRun  (vague 2 — PersistableModel, table pl_pipeline_runs)
# ---------------------------------------------------------------------------


@ModelRegistry.register
class PipelineRun(PersistableModel):
    """Instance d'exécution d'une pipeline complète.

    Mutable : les transitions d'état, timestamps et la liste de ``StageRun``
    sont mis à jour pendant l'exécution.

    Attributes:
        pipeline_run_id: Identifiant unique de cette exécution (UUID4).
        pipeline_name: Nom de la pipeline correspondante.
        pipeline_version: Version de la pipeline au moment de l'exécution.
        status: État global de la pipeline.
        stage_runs: Liste des exécutions de stages (ordonnée).
        context: Contexte accumulé, propagé entre stages.
        error: Information d'erreur globale.
        start_time: Heure de début de la pipeline.
        end_time: Heure de fin de la pipeline.
        duration_ms: Durée totale en millisecondes.
        triggered_by: Source du déclenchement.
        trigger_data: Données du déclenchement.
        metadata: Métadonnées additionnelles.
        created_at: Heure de création du run.
        updated_at: Heure de dernière mise à jour.

    Examples:
        >>> pipeline_run = PipelineRun(pipeline_name="weekly-etl")
        >>> pipeline_run.start_execution()
        >>> pipeline_run.add_stage_run(StageRun(job_name="ingest", stage_index=0))
        >>> pipeline_run.complete_success()
        >>> d = pipeline_run.to_dict()
        >>> restored = PipelineRun.from_dict(d)
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="pl_pipeline_runs",
        columns=[
            ColumnDef("pipeline_run_id", ColumnType.TEXT, primary_key=True),
            ColumnDef("pipeline_name", ColumnType.TEXT, nullable=False),
            ColumnDef("pipeline_version", ColumnType.TEXT),
            ColumnDef("status", ColumnType.TEXT, nullable=False),
            ColumnDef("context", ColumnType.JSON),
            ColumnDef("error", ColumnType.TEXT),
            ColumnDef("start_time", ColumnType.TIMESTAMP),
            ColumnDef("end_time", ColumnType.TIMESTAMP),
            ColumnDef("duration_ms", ColumnType.INTEGER),
            ColumnDef("triggered_by", ColumnType.TEXT),
            ColumnDef("trigger_data", ColumnType.JSON),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP, nullable=False),
            ColumnDef("updated_at", ColumnType.TIMESTAMP, nullable=False),
        ],
        indexes=[
            ("pipeline_name",),
            ("status",),
            ("created_at",),
            ("pipeline_name", "status"),
        ],
    )

    pipeline_run_id: str = Field(default_factory=generate_id)
    pipeline_name: str = ""
    pipeline_version: str = "1.0.0"
    status: RunStatus = RunStatus.PENDING
    stage_runs: list[StageRun] = Field(default_factory=list, exclude=True)
    context: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    triggered_by: str = "manual"
    trigger_data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def start_execution(self) -> None:
        """Marque le début de l'exécution de la pipeline."""
        self.status = RunStatus.RUNNING
        self.start_time = utc_now()
        self.updated_at = utc_now()

    def complete_success(self) -> None:
        """Marque la pipeline comme terminée avec succès."""
        self.status = RunStatus.SUCCESS
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    def complete_failure(self, error: str) -> None:
        """Marque la pipeline comme échouée."""
        self.status = RunStatus.FAILED
        self.error = error
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    def cancel(self) -> None:
        """Annule l'exécution de la pipeline."""
        self.status = RunStatus.CANCELLED
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    def mark_timeout(self) -> None:
        """Marque la pipeline comme timeout."""
        self.status = RunStatus.TIMEOUT
        self.end_time = utc_now()
        self.updated_at = utc_now()
        self._calculate_duration()

    # ------------------------------------------------------------------
    # Stage run management
    # ------------------------------------------------------------------

    def add_stage_run(self, stage_run: StageRun) -> None:
        """Ajoute un StageRun et lie le pipeline_run_id."""
        stage_run.pipeline_run_id = self.pipeline_run_id
        self.stage_runs.append(stage_run)
        self.updated_at = utc_now()

    def get_stage_run(self, job_name: str) -> StageRun | None:
        """Récupère un StageRun par nom de job."""
        for sr in self.stage_runs:
            if sr.job_name == job_name:
                return sr
        return None

    def get_stage_runs_by_status(self, status: RunStatus) -> list[StageRun]:
        """Récupère les StageRuns par statut."""
        return [sr for sr in self.stage_runs if sr.status == status]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def success(self) -> bool:
        """True si la pipeline est en SUCCESS."""
        return self.status == RunStatus.SUCCESS

    @property
    def is_terminal(self) -> bool:
        """Vérifie si la pipeline est dans un état terminal."""
        return is_terminal(self.status)

    @property
    def is_suspended(self) -> bool:
        """Vérifie si la pipeline est suspendue."""
        return is_suspended(self.status)

    @property
    def duration_s(self) -> float:
        """Durée en secondes (0.0 si non calculée)."""
        return (self.duration_ms or 0) / 1000.0

    @property
    def progress_percentage(self) -> float:
        """Pourcentage de progression basé sur les stages terminaux."""
        if not self.stage_runs:
            return 0.0
        completed = sum(1 for sr in self.stage_runs if sr.is_terminal)
        return (completed / len(self.stage_runs)) * 100.0

    @property
    def summary(self) -> str:
        """Résumé textuel multi-ligne avec icônes."""
        status_icon = "✓" if self.status == RunStatus.SUCCESS else "✗"
        duration = f"{self.duration_s:.2f}s" if self.duration_ms else "N/A"
        header = (
            f"Pipeline '{self.pipeline_name}' — "
            f"{status_icon} {self.status.value.upper()} ({duration})"
        )
        lines = [header]
        for sr in self.stage_runs:
            if sr.skipped:
                icon = "⊘"
                detail = f"skipped ({sr.skip_reason or 'no reason'})"
            elif sr.status == RunStatus.SUCCESS:
                icon = "✓"
                detail = f"success ({sr.duration_s:.2f}s)"
            elif sr.status == RunStatus.FAILED:
                icon = "✗"
                raw_err = sr.error or "unknown"
                # Keep the first sentence / 120 chars so the summary stays readable
                short_err = raw_err.split(" | ")[0]
                if len(short_err) > 120:
                    short_err = short_err[:120] + "…"
                detail = f"failed: {short_err}"
            else:
                icon = "…"
                detail = sr.status.value
            lines.append(f"  {icon} {sr.job_name}: {detail}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _calculate_duration(self) -> None:
        if self.start_time and self.end_time:
            self.duration_ms = int(
                (self.end_time - self.start_time).total_seconds() * 1000
            )

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible."""
        return {
            "pipeline_run_id": self.pipeline_run_id,
            "pipeline_name": self.pipeline_name,
            "pipeline_version": self.pipeline_version,
            "status": self.status.value,
            "stage_runs": [sr.to_dict() for sr in self.stage_runs],
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
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineRun:
        """Désérialise depuis un dict."""
        return cls(
            pipeline_run_id=data["pipeline_run_id"],
            pipeline_name=data.get("pipeline_name", ""),
            pipeline_version=data.get("pipeline_version", "1.0.0"),
            status=RunStatus(data["status"]),
            stage_runs=[StageRun.from_dict(sr) for sr in data.get("stage_runs", [])],
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
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    def __repr__(self) -> str:
        return (
            f"PipelineRun({self.pipeline_name!r}, "
            f"status={self.status.value!r}, "
            f"stages={len(self.stage_runs)})"
        )
