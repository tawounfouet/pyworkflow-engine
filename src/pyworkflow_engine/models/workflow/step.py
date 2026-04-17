"""
Modèles design-time des étapes — Step et SubJob.

Ces modèles représentent la *définition* des étapes d'un workflow avant
son exécution. Ils sont immuables (frozen) et auto-sérialisables.

Migration D2 (vague 3) — ADR-018 :
    Convertis de ``dataclass(frozen=True)`` en Pydantic ``BaseModel``
    (``model_config = {"frozen": True}``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from pyworkflow_engine.models.workflow.connector import ConnectorRef
from pyworkflow_engine.models.enums import ExecutorType, StepType


class Step(BaseModel):
    """Définition d'une étape de workflow.

    Une Step représente une unité d'exécution dans un workflow.
    Elle peut être une fonction Python, un appel HTTP, une tâche humaine, etc.

    Attributes:
        name: Nom unique de l'étape dans le workflow.
        step_type: Type d'étape déterminant le comportement d'exécution.
        handler: Fonction Python à exécuter (pour StepType.FUNCTION).
        config: Configuration spécifique au type d'étape.
        dependencies: Noms des étapes dont celle-ci dépend.
        executor_type: Type d'executor à utiliser pour l'exécution.
        timeout: Timeout d'exécution (None = pas de timeout).
        retry_count: Nombre de tentatives en cas d'échec.
        retry_delay: Délai entre les tentatives.
        condition: Fonction de condition pour exécution conditionnelle.
        metadata: Métadonnées additionnelles.
        connector_ref: Référence au connecteur pyconnectors (uniquement si
            ``step_type == StepType.CONNECTOR``). Voir ADR-016.

    Examples:
        >>> def hello():
        ...     return {"message": "Hello World!"}
        >>>
        >>> step = Step(name="say_hello", step_type=StepType.FUNCTION, handler=hello)
        >>> d = step.to_dict()
        >>> restored = Step.from_dict(d)  # handler=None après désérialisation
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    name: str
    step_type: StepType
    handler: Callable | None = Field(default=None, exclude=True)
    config: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    executor_type: ExecutorType = ExecutorType.LOCAL
    timeout: timedelta | None = None
    retry_count: int = 0
    retry_delay: timedelta = Field(default_factory=lambda: timedelta(seconds=1))
    condition: Callable[[dict[str, Any]], bool] | None = Field(
        default=None, exclude=True
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    connector_ref: ConnectorRef | None = None

    @model_validator(mode="after")
    def _validate(self) -> Step:
        """Validation après initialisation."""
        if self.retry_count < 0:
            raise ValueError(f"Step '{self.name}': retry_count must be >= 0")
        if self.name in self.dependencies:
            raise ValueError(f"Step '{self.name}': cannot depend on itself")
        return self

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible.

        Le handler est stocké sous forme de nom qualifié importable
        (``"module.qualname"``) quand c'est possible, ``None`` sinon
        (lambdas, fonctions ``__main__``, closures).
        """
        handler_ref: str | None = None
        if self.handler is not None:
            module = getattr(self.handler, "__module__", None)
            qualname = getattr(self.handler, "__qualname__", None)
            if (
                module
                and qualname
                and module != "__main__"
                and "<" not in module
                and "<" not in qualname
            ):
                handler_ref = f"{module}.{qualname}"
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "handler": handler_ref,
            "config": dict(self.config),
            "dependencies": list(self.dependencies),
            "executor_type": self.executor_type.value,
            "timeout": (
                self.timeout.total_seconds() if self.timeout is not None else None
            ),
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay.total_seconds(),
            "metadata": dict(self.metadata),
            "connector_ref": (
                self.connector_ref.to_dict() if self.connector_ref is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        """Désérialise depuis un dict.

        Tente de restaurer ``handler`` via son nom qualifié importable.
        Retombe sur ``None`` si le module n'est pas importable (ex. script
        ``__main__``, lambda, fonction locale).
        """
        timeout_secs = data.get("timeout")
        retry_delay_secs = data.get("retry_delay", 1.0)
        handler = _restore_handler(data.get("handler"))
        connector_ref_data = data.get("connector_ref")
        connector_ref = (
            ConnectorRef.from_dict(connector_ref_data) if connector_ref_data else None
        )
        return cls(
            name=data["name"],
            step_type=StepType(data["step_type"]),
            handler=handler,
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
            connector_ref=connector_ref,
        )


def _restore_handler(handler_ref: str | None) -> Callable | None:
    """Restaure un handler depuis son nom qualifié importable.

    Parcourt le chemin ``"a.b.c.fn"`` en testant progressivement les préfixes
    de module (``a.b.c`` → ``a.b`` → ``a``) jusqu'à un import réussi, puis
    résout les attributs restants.

    Si la fonction importée est décorée par ``@step`` (présence de
    ``__step_spec__``), reconstruit le context-adapter via
    ``_make_context_adapter`` (import lazy pour éviter la dépendance
    circulaire ``models.step`` → ``decorators.job_decorator``).

    Returns:
        Le callable restauré, ou ``None`` si l'import échoue (module non
        importable, lambda, script ``__main__``, etc.).
    """
    if (
        not handler_ref
        or not isinstance(handler_ref, str)
        or handler_ref.startswith("<")
    ):
        return None

    import importlib

    parts = handler_ref.split(".")
    # Teste les points de coupure de droite à gauche :
    # "a.b.c.fn" → module="a.b.c", attrs=["fn"]
    #            → module="a.b",   attrs=["c", "fn"]  …
    for split in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:split])
        attr_path = parts[split:]
        try:
            obj: Any = importlib.import_module(module_name)
            for attr in attr_path:
                obj = getattr(obj, attr)
        except (ImportError, AttributeError):
            continue

        # Détecte les fonctions décorées par @step et reconstruit l'adapter
        step_spec = getattr(obj, "__step_spec__", None)
        if step_spec is not None:
            # Import lazy — évite la circularité models.step → decorators
            from pyworkflow_engine.decorators.job_decorator import (  # noqa: PLC0415
                _make_context_adapter,
            )

            wrapped = getattr(obj, "__wrapped_fn__", obj)
            return _make_context_adapter(wrapped, step_spec)

        return obj  # fonction ordinaire (context: WorkflowContext)

    return None


class SubJob(BaseModel):
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

    model_config = {"frozen": True}

    job_name: str
    input_mapping: dict[str, str] = Field(default_factory=dict)
    output_mapping: dict[str, str] = Field(default_factory=dict)
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
