"""
Modèle design-time de la pipeline — Pipeline et PipelineStage.

Une ``Pipeline`` est une **composition séquentielle de Jobs** (stages).
Chaque ``PipelineStage`` pointe vers un ``Job`` par nom et configure la
propagation du contexte, le comportement en cas d'échec, et les conditions
de skip.

Ces modèles sont immuables (frozen PersistableModel Pydantic) et auto-sérialisables
via ``to_dict()`` / ``from_dict()``.

Migration D2 (vague 3) — ADR-018 :
    Converti de ``dataclass(frozen=True)`` en PersistableModel Pydantic
    (tables ``pl_pipeline_stages`` / ``pl_pipelines``).

Voir ADR-014 pour la conception complète.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import Field, model_validator

from pyworkflow_engine.models.enums import Priority, TriggerType
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)

# ---------------------------------------------------------------------------
# PipelineStage — un Job dans une Pipeline
# ---------------------------------------------------------------------------


@ModelRegistry.register
class PipelineStage(PersistableModel):
    """Définition d'un stage dans une Pipeline = un Job à exécuter.

    Un stage encapsule la référence à un Job et sa configuration
    d'orchestration au sein de la pipeline (contexte, condition de skip,
    comportement en cas d'échec).

    Attributes:
        job_name: Nom du Job à résoudre (clé de registre ou attribut ``Job.name``).
        pipeline_name: Nom de la Pipeline parente (FK).
        job: Référence directe au ``Job`` (non sérialisée, optionnelle).
        initial_context: Contexte statique injecté dans le Job au démarrage
            du stage.
        context_mapping: Mapping ``{clé_job: clé_pipeline}`` pour propager des
            valeurs du contexte pipeline vers le contexte du Job.
        continue_on_failure: Si ``True``, la pipeline continue l'exécution
            des stages suivants même si ce stage échoue.
        condition: Fonction ``(ctx: dict) → bool`` — le stage est skippé si
            elle retourne ``False``.  Non sérialisée.
        enabled: Si ``False``, le stage est toujours skippé.
        metadata: Métadonnées libres (tags, documentation, etc.).

    Examples:
        >>> stage = PipelineStage(
        ...     job_name="ingestion-restcountries",
        ...     pipeline_name="weekly-countries-to-dwh",
        ...     initial_context={"source": "https://restcountries.com/v3.1/all"},
        ...     continue_on_failure=False,
        ... )
        >>> d = stage.to_dict()
        >>> restored = PipelineStage.from_dict(d)
        >>> restored.job_name
        'ingestion-restcountries'
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="pl_pipeline_stages",
        columns=[
            ColumnDef("job_name", ColumnType.TEXT, primary_key=True),
            ColumnDef(
                "pipeline_name",
                ColumnType.TEXT,
                primary_key=True,
                foreign_key="pl_pipelines.name",
            ),
            ColumnDef("initial_context", ColumnType.JSON),
            ColumnDef("context_mapping", ColumnType.JSON),
            ColumnDef("continue_on_failure", ColumnType.BOOLEAN),
            ColumnDef("enabled", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
        ],
        indexes=[("pipeline_name",), ("enabled",)],
    )

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    job_name: str
    pipeline_name: str = ""
    job: Any = Field(default=None, exclude=True)  # Job | None — non sérialisé
    initial_context: dict[str, Any] = Field(default_factory=dict)
    context_mapping: dict[str, str] = Field(default_factory=dict)
    continue_on_failure: bool = False
    condition: Callable[[dict[str, Any]], bool] | None = Field(
        default=None, exclude=True
    )
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> PipelineStage:
        """Validation après initialisation."""
        if not self.job_name:
            raise ValueError("PipelineStage: job_name cannot be empty")
        return self

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible.

        Les champs ``job`` et ``condition`` (callables) sont exclus.
        """
        return {
            "job_name": self.job_name,
            "initial_context": dict(self.initial_context),
            "context_mapping": dict(self.context_mapping),
            "continue_on_failure": self.continue_on_failure,
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineStage:
        """Désérialise depuis un dict.

        ``job`` et ``condition`` seront ``None`` après désérialisation.
        """
        return cls(
            job_name=data["job_name"],
            initial_context=data.get("initial_context", {}),
            context_mapping=data.get("context_mapping", {}),
            continue_on_failure=data.get("continue_on_failure", False),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Pipeline — composition séquentielle de Jobs
# ---------------------------------------------------------------------------


@ModelRegistry.register
class Pipeline(PersistableModel):
    """Définition d'une pipeline complète — composition séquentielle de Jobs.

    Une Pipeline orchestre une liste ordonnée de ``PipelineStage``, chacun
    contenant un Job. L'exécution est séquentielle : stage *n* termine
    avant que stage *n+1* ne démarre. Le contexte peut être propagé entre
    stages via ``context_mapping``.

    Attributes:
        name: Nom unique de la pipeline.
        description: Description textuelle de la pipeline.
        stages: Séquence ordonnée de ``PipelineStage``.
        triggers: Types de déclencheurs acceptés.
        schedule: Expression cron (optionnelle, pour ``TriggerType.SCHEDULE``).
        priority: Priorité d'exécution.
        tags: Tags pour catégorisation et recherche.
        metadata: Métadonnées additionnelles.
        version: Version de la définition de la pipeline.
        enabled: Si ``False``, la pipeline ne peut pas être exécutée.
        owner: Propriétaire / équipe responsable (email, nom, etc.).
        on_success: Callback appelé en cas de succès (non sérialisé).
        on_failure: Callback appelé en cas d'échec (non sérialisé).

    Examples:
        >>> from pyworkflow_engine.models.enums import TriggerType
        >>> pipeline = Pipeline(
        ...     name="weekly-countries-to-dwh",
        ...     stages=[
        ...         PipelineStage(job_name="ingestion-restcountries"),
        ...         PipelineStage(job_name="transform-stg-restcountries"),
        ...     ],
        ...     schedule="0 1 * * 0",
        ...     owner="data-team@company.com",
        ... )
        >>> pipeline.stage_count
        2
        >>> d = pipeline.to_dict()
        >>> restored = Pipeline.from_dict(d)
        >>> restored.name
        'weekly-countries-to-dwh'
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="pl_pipelines",
        columns=[
            ColumnDef("name", ColumnType.TEXT, primary_key=True),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("stages", ColumnType.JSON),
            ColumnDef("triggers", ColumnType.JSON),
            ColumnDef("schedule", ColumnType.TEXT),
            ColumnDef("priority", ColumnType.TEXT),
            ColumnDef("tags", ColumnType.JSON),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("version", ColumnType.TEXT),
            ColumnDef("enabled", ColumnType.BOOLEAN),
            ColumnDef("owner", ColumnType.TEXT),
        ],
        indexes=[("enabled",), ("tags",), ("owner",)],
    )

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    name: str
    description: str = ""
    stages: list[PipelineStage] = Field(default_factory=list)
    triggers: list[TriggerType] = Field(
        default_factory=lambda: [TriggerType.MANUAL],
    )
    schedule: str | None = None
    priority: Priority = Priority.NORMAL
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0.0"
    enabled: bool = True
    owner: str = ""
    on_success: Callable[..., Any] | None = Field(default=None, exclude=True)
    on_failure: Callable[..., Any] | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _validate(self) -> Pipeline:
        """Validation après initialisation."""
        if not self.name:
            raise ValueError("Pipeline name cannot be empty")
        job_names = [stage.job_name for stage in self.stages]
        if len(job_names) != len(set(job_names)):
            raise ValueError(f"Pipeline '{self.name}': stage job_names must be unique")
        return self

    # ------------------------------------------------------------------
    # Propriétés utilitaires
    # ------------------------------------------------------------------

    @property
    def stage_count(self) -> int:
        """Nombre de stages dans la pipeline."""
        return len(self.stages)

    @property
    def job_names(self) -> list[str]:
        """Liste ordonnée des noms de jobs des stages."""
        return [stage.job_name for stage in self.stages]

    def get_stage(self, job_name: str) -> PipelineStage | None:
        """Récupère un stage par nom de job."""
        for stage in self.stages:
            if stage.job_name == job_name:
                return stage
        return None

    def get_stage_index(self, job_name: str) -> int | None:
        """Récupère l'index d'un stage par nom de job."""
        for i, stage in enumerate(self.stages):
            if stage.job_name == job_name:
                return i
        return None

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible.

        Les champs ``on_success`` et ``on_failure`` (callables) sont exclus.
        """
        return {
            "name": self.name,
            "description": self.description,
            "stages": [s.to_dict() for s in self.stages],
            "triggers": [t.value for t in self.triggers],
            "schedule": self.schedule,
            "priority": self.priority.value,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "version": self.version,
            "enabled": self.enabled,
            "owner": self.owner,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pipeline:
        """Désérialise depuis un dict.

        ``on_success`` et ``on_failure`` seront ``None``.
        """
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            stages=[PipelineStage.from_dict(s) for s in data.get("stages", [])],
            triggers=[
                TriggerType(t) for t in data.get("triggers", [TriggerType.MANUAL.value])
            ],
            schedule=data.get("schedule"),
            priority=Priority(data.get("priority", Priority.NORMAL.value)),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            version=data.get("version", "1.0.0"),
            enabled=data.get("enabled", True),
            owner=data.get("owner", ""),
        )

    def __repr__(self) -> str:
        return (
            f"Pipeline({self.name!r}, stages={self.stage_count}, "
            f"version={self.version!r})"
        )
