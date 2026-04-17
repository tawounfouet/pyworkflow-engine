"""
Modèle persistable — WorkflowLog (ADR-018, décision 4).

Représente une entrée de log corrélée à une exécution de workflow.
Remplace le SQL brut dans ``SQLiteLogHandler`` par le pattern
``PersistableModel`` + ``Repository[T]`` (ADR-017).

Chaque log entry peut être corrélée à :
    - Un job_run (exécution d'un Job)
    - Un step_run (exécution d'un Step)
    - Une execution AI (exécution d'un Agent/Graph)
    - Une pipeline_run (exécution d'une Pipeline)
    - Un agent AI

Ces FK sont toutes optionnelles — un log peut exister sans corrélation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import Field

from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


@ModelRegistry.register
class WorkflowLog(PersistableModel):
    """Entrée de log persistée avec corrélation d'exécution.

    Champs de corrélation (tous optionnels) :
        - ``correlation_id`` → ID libre pour regrouper des logs transversaux
        - ``job_run_id``     → lien vers un JobRun
        - ``step_run_id``    → lien vers un StepRun
        - ``execution_id``   → lien vers une Execution AI
        - ``pipeline_run_id``→ lien vers un PipelineRun
        - ``agent_id``       → lien vers un Agent AI

    Champs techniques :
        - ``logger_name``    → nom du logger stdlib
        - ``module``         → module Python source
        - ``func_name``      → fonction source
        - ``line_no``        → numéro de ligne source
        - ``exception``      → traceback complet si applicable
        - ``extra``          → JSON des champs extra du LogRecord

    Usage::

        log = WorkflowLog(
            message="Step started",
            level="INFO",
            logger_name="pyworkflow_engine.engine.runner",
            job_run_id="run-123",
            step_run_id="step-456",
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="log_entries",
        columns=[
            # ── Identité ──────────────────────────────────────────────
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("timestamp", ColumnType.TIMESTAMP, nullable=False),
            ColumnDef("level", ColumnType.TEXT, nullable=False),
            ColumnDef("logger_name", ColumnType.TEXT, nullable=False),
            ColumnDef("message", ColumnType.TEXT, nullable=False),
            # ── Corrélation (toutes optionnelles) ─────────────────────
            ColumnDef("correlation_id", ColumnType.TEXT),
            ColumnDef("job_run_id", ColumnType.TEXT),
            ColumnDef("step_run_id", ColumnType.TEXT),
            ColumnDef("execution_id", ColumnType.TEXT),
            ColumnDef("pipeline_run_id", ColumnType.TEXT),
            ColumnDef("agent_id", ColumnType.TEXT),
            # ── Technique ─────────────────────────────────────────────
            ColumnDef("module", ColumnType.TEXT),
            ColumnDef("func_name", ColumnType.TEXT),
            ColumnDef("line_no", ColumnType.INTEGER),
            ColumnDef("exception", ColumnType.TEXT),
            ColumnDef("extra", ColumnType.JSON),
            # ── Metadata ──────────────────────────────────────────────
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[
            ("timestamp",),
            ("level",),
            ("logger_name",),
            ("correlation_id",),
            ("job_run_id",),
            ("step_run_id",),
            ("execution_id",),
            ("pipeline_run_id",),
            ("agent_id",),
            ("level", "timestamp"),
        ],
    )

    # ── Identité ──────────────────────────────────────────────────────────
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    level: str = "INFO"
    logger_name: str = ""
    message: str = ""

    # ── Corrélation ───────────────────────────────────────────────────────
    correlation_id: str | None = None
    job_run_id: str | None = None
    step_run_id: str | None = None
    execution_id: str | None = None
    pipeline_run_id: str | None = None
    agent_id: str | None = None

    # ── Technique ─────────────────────────────────────────────────────────
    module: str | None = None
    func_name: str | None = None
    line_no: int | None = None
    exception: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    # ── Metadata ──────────────────────────────────────────────────────────
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowLogQuery:
    """Paramètres de requête pour filtrer les logs.

    Read-model pur — pas persisté, juste un DTO pour construire
    des requêtes ``Repository.filter()`` de manière type-safe.

    Usage::

        query = WorkflowLogQuery(
            level="ERROR",
            job_run_id="run-123",
            since=datetime(2026, 4, 12),
            limit=50,
        )
        logs = log_repo.filter(**query.to_filter_kwargs())
    """

    def __init__(
        self,
        *,
        level: str | None = None,
        logger_name: str | None = None,
        correlation_id: str | None = None,
        job_run_id: str | None = None,
        step_run_id: str | None = None,
        execution_id: str | None = None,
        pipeline_run_id: str | None = None,
        agent_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        message_like: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "-timestamp",
    ) -> None:
        self.level = level
        self.logger_name = logger_name
        self.correlation_id = correlation_id
        self.job_run_id = job_run_id
        self.step_run_id = step_run_id
        self.execution_id = execution_id
        self.pipeline_run_id = pipeline_run_id
        self.agent_id = agent_id
        self.since = since
        self.until = until
        self.message_like = message_like
        self.limit = limit
        self.offset = offset
        self.order_by = order_by

    def to_filter_kwargs(self) -> dict[str, Any]:
        """Convertit en kwargs pour ``Repository.filter()``.

        Returns:
            Dict filtrable directement par le Repository CRUD.
        """
        kwargs: dict[str, Any] = {}

        if self.level is not None:
            kwargs["level"] = self.level.upper()
        if self.logger_name is not None:
            kwargs["logger_name__like"] = f"%{self.logger_name}%"
        if self.correlation_id is not None:
            kwargs["correlation_id"] = self.correlation_id
        if self.job_run_id is not None:
            kwargs["job_run_id"] = self.job_run_id
        if self.step_run_id is not None:
            kwargs["step_run_id"] = self.step_run_id
        if self.execution_id is not None:
            kwargs["execution_id"] = self.execution_id
        if self.pipeline_run_id is not None:
            kwargs["pipeline_run_id"] = self.pipeline_run_id
        if self.agent_id is not None:
            kwargs["agent_id"] = self.agent_id
        if self.since is not None:
            kwargs["timestamp__gte"] = self.since.isoformat()
        if self.until is not None:
            kwargs["timestamp__lte"] = self.until.isoformat()
        if self.message_like is not None:
            kwargs["message__like"] = f"%{self.message_like}%"

        # Pagination & ordering
        kwargs["limit"] = self.limit
        kwargs["offset"] = self.offset
        kwargs["order_by"] = self.order_by

        return kwargs
