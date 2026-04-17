"""
Événements du workflow engine — dataclasses stdlib.

Tous les événements circulant dans l'``EventBus`` héritent de
``BaseEvent``. Chaque événement est un dataclass (non frozen pour la
compatibilité avec ``field(default_factory=...)`` et la post-initialisation).

Catégories :
  - **Pipeline** : ``pipeline.started``, ``pipeline.completed``,
    ``pipeline.failed``
  - **Stage** : ``stage.started``, ``stage.completed``, ``stage.failed``,
    ``stage.skipped``
  - **Job** : ``job.started``, ``job.completed``, ``job.failed``
  - **Step** : ``step.started``, ``step.completed``, ``step.failed``
  - **Connector** : ``connector.executed``, ``connector.failed``
  - **Custom** : événement libre

Voir ADR-013 / ADR-014 / ADR-016.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    """Retourne l'horodatage UTC courant."""
    return datetime.now(UTC)


def _generate_id() -> str:
    """Génère un identifiant unique (UUID4)."""
    return str(uuid4())


# ---------------------------------------------------------------------------
# BaseEvent
# ---------------------------------------------------------------------------


@dataclass
class BaseEvent:
    """Événement de base dont tous les événements héritent.

    Attributes:
        event_type: Clé de routage (ex. ``"pipeline.started"``).
        event_id: Identifiant unique de l'événement (UUID4).
        timestamp: Horodatage UTC de création.
        metadata: Données libres supplémentaires.
    """

    event_type: str
    event_id: str = field(default_factory=_generate_id)
    timestamp: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Sérialise l'événement en dict JSON-compatible."""
        d: dict[str, Any] = {}
        for f in self.__dataclass_fields__:
            val = getattr(self, f)
            if isinstance(val, datetime):
                d[f] = val.isoformat()
            else:
                d[f] = val
        return d


# ======================================================================
# Pipeline Events
# ======================================================================


@dataclass
class PipelineStartedEvent(BaseEvent):
    """Émis au démarrage d'une pipeline.

    Attributes:
        pipeline_name: Nom de la pipeline.
        pipeline_run_id: Identifiant de l'exécution.
        pipeline_version: Version de la définition.
        triggered_by: Source du déclenchement.
    """

    event_type: str = "pipeline.started"
    pipeline_name: str = ""
    pipeline_run_id: str = ""
    pipeline_version: str = ""
    triggered_by: str = "manual"


@dataclass
class PipelineCompletedEvent(BaseEvent):
    """Émis à la fin d'une pipeline réussie.

    Attributes:
        pipeline_name: Nom de la pipeline.
        pipeline_run_id: Identifiant de l'exécution.
        duration_ms: Durée totale en millisecondes.
        stage_count: Nombre de stages exécutés.
    """

    event_type: str = "pipeline.completed"
    pipeline_name: str = ""
    pipeline_run_id: str = ""
    duration_ms: int | None = None
    stage_count: int = 0


@dataclass
class PipelineFailedEvent(BaseEvent):
    """Émis si une pipeline échoue.

    Attributes:
        pipeline_name: Nom de la pipeline.
        pipeline_run_id: Identifiant de l'exécution.
        error: Message d'erreur.
        failed_stage: Nom du stage qui a échoué.
        duration_ms: Durée en millisecondes.
    """

    event_type: str = "pipeline.failed"
    pipeline_name: str = ""
    pipeline_run_id: str = ""
    error: str = ""
    failed_stage: str = ""
    duration_ms: int | None = None


# ======================================================================
# Stage Events
# ======================================================================


@dataclass
class StageStartedEvent(BaseEvent):
    """Émis au démarrage d'un stage.

    Attributes:
        pipeline_run_id: Identifiant de l'exécution pipeline parente.
        stage_run_id: Identifiant de l'exécution du stage.
        job_name: Nom du Job exécuté.
        stage_index: Position du stage dans la pipeline (0-based).
    """

    event_type: str = "stage.started"
    pipeline_run_id: str = ""
    stage_run_id: str = ""
    job_name: str = ""
    stage_index: int = 0


@dataclass
class StageCompletedEvent(BaseEvent):
    """Émis à la fin d'un stage réussi.

    Attributes:
        pipeline_run_id: Identifiant de l'exécution pipeline.
        stage_run_id: Identifiant de l'exécution du stage.
        job_name: Nom du Job.
        stage_index: Position du stage.
        duration_ms: Durée en millisecondes.
    """

    event_type: str = "stage.completed"
    pipeline_run_id: str = ""
    stage_run_id: str = ""
    job_name: str = ""
    stage_index: int = 0
    duration_ms: int | None = None


@dataclass
class StageFailedEvent(BaseEvent):
    """Émis si un stage échoue.

    Attributes:
        pipeline_run_id: Identifiant de l'exécution pipeline.
        stage_run_id: Identifiant de l'exécution du stage.
        job_name: Nom du Job.
        stage_index: Position du stage.
        error: Message d'erreur.
        duration_ms: Durée en millisecondes.
    """

    event_type: str = "stage.failed"
    pipeline_run_id: str = ""
    stage_run_id: str = ""
    job_name: str = ""
    stage_index: int = 0
    error: str = ""
    duration_ms: int | None = None


@dataclass
class StageSkippedEvent(BaseEvent):
    """Émis quand un stage est sauté (condition non remplie ou disabled).

    Attributes:
        pipeline_run_id: Identifiant de l'exécution pipeline.
        stage_run_id: Identifiant de l'exécution du stage.
        job_name: Nom du Job.
        stage_index: Position du stage.
        reason: Raison du skip.
    """

    event_type: str = "stage.skipped"
    pipeline_run_id: str = ""
    stage_run_id: str = ""
    job_name: str = ""
    stage_index: int = 0
    reason: str = ""


# ======================================================================
# Job Events
# ======================================================================


@dataclass
class JobStartedEvent(BaseEvent):
    """Émis au démarrage d'un Job.

    Attributes:
        job_name: Nom du Job.
        job_run_id: Identifiant de l'exécution.
        job_version: Version du Job.
    """

    event_type: str = "job.started"
    job_name: str = ""
    job_run_id: str = ""
    job_version: str = ""


@dataclass
class JobCompletedEvent(BaseEvent):
    """Émis à la fin d'un Job réussi.

    Attributes:
        job_name: Nom du Job.
        job_run_id: Identifiant de l'exécution.
        duration_ms: Durée en millisecondes.
        step_count: Nombre de steps exécutés.
    """

    event_type: str = "job.completed"
    job_name: str = ""
    job_run_id: str = ""
    duration_ms: int | None = None
    step_count: int = 0


@dataclass
class JobFailedEvent(BaseEvent):
    """Émis si un Job échoue.

    Attributes:
        job_name: Nom du Job.
        job_run_id: Identifiant de l'exécution.
        error: Message d'erreur.
        failed_step: Nom du step qui a échoué.
        duration_ms: Durée en millisecondes.
    """

    event_type: str = "job.failed"
    job_name: str = ""
    job_run_id: str = ""
    error: str = ""
    failed_step: str = ""
    duration_ms: int | None = None


# ======================================================================
# Step Events
# ======================================================================


@dataclass
class StepStartedEvent(BaseEvent):
    """Émis au démarrage d'un Step.

    Attributes:
        job_run_id: Identifiant de l'exécution Job parente.
        step_name: Nom du Step.
        step_type: Type du Step (``StepType.value``).
    """

    event_type: str = "step.started"
    job_run_id: str = ""
    step_name: str = ""
    step_type: str = ""


@dataclass
class StepCompletedEvent(BaseEvent):
    """Émis à la fin d'un Step réussi.

    Attributes:
        job_run_id: Identifiant de l'exécution Job.
        step_name: Nom du Step.
        step_type: Type du Step.
        duration_ms: Durée en millisecondes.
    """

    event_type: str = "step.completed"
    job_run_id: str = ""
    step_name: str = ""
    step_type: str = ""
    duration_ms: int | None = None


@dataclass
class StepFailedEvent(BaseEvent):
    """Émis si un Step échoue.

    Attributes:
        job_run_id: Identifiant de l'exécution Job.
        step_name: Nom du Step.
        step_type: Type du Step.
        error: Message d'erreur.
        duration_ms: Durée en millisecondes.
    """

    event_type: str = "step.failed"
    job_run_id: str = ""
    step_name: str = ""
    step_type: str = ""
    error: str = ""
    duration_ms: int | None = None


# ======================================================================
# Connector Events (ADR-016)
# ======================================================================


@dataclass
class ConnectorExecutedEvent(BaseEvent):
    """Émis après l'exécution réussie d'un connecteur via le bridge.

    Attributes:
        connector_name: Nom du connecteur (ex. ``"database.postgresql"``).
        connector_type: Type déduit (ex. ``"database"``).
        action: Action exécutée (ex. ``"query"``, ``"execute"``).
        duration_ms: Durée en millisecondes.
        records_affected: Nombre d'enregistrements affectés.
        step_name: Nom du Step ayant déclenché le connecteur.
        job_run_id: Identifiant de l'exécution Job parente.
    """

    event_type: str = "connector.executed"
    connector_name: str = ""
    connector_type: str = ""
    action: str = ""
    duration_ms: int | None = None
    records_affected: int = 0
    step_name: str = ""
    job_run_id: str = ""


@dataclass
class ConnectorFailedEvent(BaseEvent):
    """Émis après l'échec d'un connecteur via le bridge.

    Attributes:
        connector_name: Nom du connecteur.
        connector_type: Type déduit.
        action: Action tentée.
        error: Message d'erreur.
        duration_ms: Durée en millisecondes.
        step_name: Nom du Step.
        job_run_id: Identifiant de l'exécution Job.
    """

    event_type: str = "connector.failed"
    connector_name: str = ""
    connector_type: str = ""
    action: str = ""
    error: str = ""
    duration_ms: int | None = None
    step_name: str = ""
    job_run_id: str = ""


# ======================================================================
# Custom Event
# ======================================================================


@dataclass
class CustomEvent(BaseEvent):
    """Événement personnalisé libre.

    Attributes:
        name: Nom de l'événement personnalisé.
        data: Données libres.
    """

    event_type: str = "custom"
    name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
