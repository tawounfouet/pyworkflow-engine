"""
``PipelineBuilder`` et décorateurs ``@pipeline`` / ``@stage``.

``@stage`` marque une fonction comme étape de pipeline et stocke les
métadonnées d'orchestration dans ``fn.__stage_spec__`` (un ``StageSpec``
frozen dataclass).

``@pipeline`` compose des fonctions ``@stage`` en un ``PipelineBuilder``.
``PipelineBuilder.build()`` inspecte les fonctions ``@stage`` référencées
dans le corps du ``@pipeline`` pour construire un objet ``Pipeline``
standard.

Deux modes de collecte des stages :

* **Mode implicite** (par défaut) — introspection via ``co_names`` +
  ``__globals__``.
* **Mode explicite** — ``@pipeline(stages=[fn1, fn2])`` — robuste pour
  les stages importés dynamiquement ou définis en dehors du module courant.

Symétrique à l'API ``@step`` / ``@job`` (ADR-005). Voir ADR-014 / ADR-016.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from pyworkflow_engine.models.enums import Priority, TriggerType
from pyworkflow_engine.models.pipeline.pipeline import Pipeline, PipelineStage

# ---------------------------------------------------------------------------
# StageSpec — métadonnées attachées par @stage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageSpec:
    """Métadonnées d'orchestration attachées à une fonction décorée par ``@stage``.

    Stockées dans ``fn.__stage_spec__``. Ne contient aucune logique
    d'exécution — c'est un descripteur pur lu par ``PipelineBuilder``
    pour construire un ``PipelineStage``.

    Attributes:
        job_ref: Référence au Job (``Job``, ``JobBuilder`` ou ``None``).
        initial_context: Contexte statique injecté dans le Job au
            démarrage du stage.
        context_mapping: Mapping ``{clé_job: clé_pipeline}`` pour
            propager des valeurs du contexte pipeline vers le Job.
        continue_on_failure: Si ``True``, la pipeline continue après
            un échec de ce stage.
        condition: Prédicat ``(ctx: dict) → bool`` — le stage est
            skippé si elle retourne ``False``.
        enabled: Si ``False``, le stage est toujours skippé.
        metadata: Métadonnées libres.
    """

    job_ref: Any = None  # Job | JobBuilder | None
    initial_context: dict[str, Any] = field(default_factory=dict)
    context_mapping: dict[str, str] = field(default_factory=dict)
    continue_on_failure: bool = False
    condition: Callable[[dict[str, Any]], bool] | None = field(
        default=None,
        compare=False,
        hash=False,
    )
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# @stage decorator
# ---------------------------------------------------------------------------


def stage(
    job: Any | None = None,
    *,
    initial_context: dict[str, Any] | None = None,
    context_mapping: dict[str, str] | None = None,
    continue_on_failure: bool = False,
    condition: Callable[[dict[str, Any]], bool] | None = None,
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
) -> Callable:
    """Décorateur qui marque une fonction comme stage de pipeline.

    La fonction décorée reste **appelable normalement** — aucun
    comportement runtime n'est ajouté. Les métadonnées d'orchestration
    sont stockées dans ``fn.__stage_spec__`` et lues plus tard par
    ``PipelineBuilder.build()``.

    Args:
        job: Référence au Job (``Job``, ``JobBuilder`` ou ``None``).
            Si ``None``, le nom du stage est déduit du nom de la fonction.
        initial_context: Contexte statique injecté dans le Job.
        context_mapping: Mapping ``{clé_job: clé_pipeline}``.
        continue_on_failure: La pipeline continue après échec.
        condition: ``(ctx) → bool`` — skip si ``False``.
        enabled: Si ``False``, toujours skippé.
        metadata: Métadonnées libres.

    Returns:
        La fonction originale enrichie d'un attribut ``__stage_spec__``.

    Examples:
        >>> from pyworkflow_engine.decorators import stage
        >>> @stage(continue_on_failure=True)
        ... def quality_check():
        ...     '''Vérification post-pipeline.'''
        >>> quality_check.__stage_spec__.continue_on_failure
        True
    """

    def decorator(fn: Callable) -> Callable:
        spec = StageSpec(
            job_ref=job,
            initial_context=dict(initial_context or {}),
            context_mapping=dict(context_mapping or {}),
            continue_on_failure=continue_on_failure,
            condition=condition,
            enabled=enabled,
            metadata=dict(metadata or {}),
        )
        return _attach_stage_spec(fn, spec)

    return decorator


def _attach_stage_spec(fn: Callable, spec: StageSpec) -> Callable:
    """Attache un ``StageSpec`` à une fonction via ``functools.wraps``."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    wrapper.__stage_spec__ = spec  # type: ignore[attr-defined]
    wrapper.__wrapped_fn__ = fn  # type: ignore[attr-defined]
    return wrapper


# ---------------------------------------------------------------------------
# @pipeline decorator
# ---------------------------------------------------------------------------


def pipeline(
    name: str | None = None,
    *,
    version: str = "1.0.0",
    description: str = "",
    schedule: str | None = None,
    owner: str = "",
    tags: list[str] | None = None,
    priority: Priority = Priority.NORMAL,
    stages: list[Callable] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Callable:
    """Décorateur qui compose des fonctions ``@stage`` en ``Pipeline``.

    La fonction décorée sert de **déclaration** (son corps n'est pas exécuté
    par ``build()``). Le décorateur analyse les fonctions ``@stage``
    référencées — soit par introspection du bytecode, soit via
    ``stages=[...]`` — pour construire un ``Pipeline`` standard.

    Args:
        name: Nom de la pipeline. Par défaut : nom de la fonction.
        version: Version sémantique. Par défaut ``"1.0.0"``.
        description: Description textuelle. Par défaut : docstring.
        schedule: Expression cron (optionnelle).
        owner: Propriétaire / équipe responsable.
        tags: Tags pour catégorisation.
        priority: Priorité d'exécution.
        stages: Liste explicite de fonctions ``@stage``. Si fourni,
            l'introspection bytecode est ignorée.
        metadata: Métadonnées additionnelles.

    Returns:
        Un ``PipelineBuilder`` — appelable comme la fonction originale,
        mais enrichi d'une méthode ``build()`` pour produire le
        ``Pipeline``.

    Examples:
        >>> @pipeline(name="etl", schedule="0 1 * * 0")
        ... def etl_pipeline():
        ...     ingestion()
        ...     transformation()
        >>> p = etl_pipeline.build()
        >>> p.name
        'etl'
    """

    def decorator(fn: Callable) -> PipelineBuilder:
        _name = name or fn.__name__
        _description = description or (fn.__doc__ or "").strip()
        builder = PipelineBuilder(
            fn=fn,
            pipeline_name=_name,
            version=version,
            description=_description,
            schedule=schedule,
            owner=owner,
            tags=list(tags or []),
            priority=priority,
            explicit_stages=stages,
            metadata=dict(metadata or {}),
        )
        functools.update_wrapper(builder, fn)
        return builder

    return decorator


# ---------------------------------------------------------------------------
# PipelineBuilder — retourné par @pipeline
# ---------------------------------------------------------------------------


class PipelineBuilder:
    """Objet retourné par ``@pipeline``.

    Peut être appelé comme la fonction originale (debug / tests), et
    expose ``build()`` pour produire l'objet ``Pipeline`` standard.

    Attributes:
        pipeline_name: Nom de la pipeline.
        version: Version de la pipeline.
        description: Description textuelle.
    """

    def __init__(
        self,
        fn: Callable,
        pipeline_name: str,
        version: str,
        description: str,
        schedule: str | None,
        owner: str,
        tags: list[str],
        priority: Priority,
        explicit_stages: list[Callable] | None,
        metadata: dict[str, Any],
    ) -> None:
        self._fn = fn
        self.pipeline_name = pipeline_name
        self.version = version
        self.description = description
        self._schedule = schedule
        self._owner = owner
        self._tags = tags
        self._priority = priority
        self._explicit_stages = explicit_stages
        self._metadata = metadata

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> Pipeline:
        """Construit un ``Pipeline`` à partir des fonctions ``@stage``.

        Si ``stages=[...]`` a été fourni au décorateur, ces fonctions
        sont utilisées directement. Sinon, le bytecode de la fonction
        ``@pipeline`` est inspecté pour trouver les fonctions ``@stage``
        référencées dans le scope global.

        Returns:
            Un ``Pipeline`` valide.

        Raises:
            ValueError: Si aucun stage décoré par ``@stage`` n'est trouvé.
        """
        if self._explicit_stages is not None:
            pipeline_stages = _stages_from_explicit_list(self._explicit_stages)
        else:
            pipeline_stages = _stages_from_bytecode(self._fn)

        triggers: list[TriggerType] = [TriggerType.MANUAL]
        if self._schedule:
            triggers.append(TriggerType.SCHEDULE)

        return Pipeline(
            name=self.pipeline_name,
            description=self.description,
            stages=pipeline_stages,
            triggers=triggers,
            schedule=self._schedule,
            priority=self._priority,
            tags=self._tags,
            metadata=self._metadata,
            version=self.version,
            enabled=True,
            owner=self._owner,
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Appelle la fonction originale (utile pour debug / tests)."""
        return self._fn(*args, **kwargs)

    def __repr__(self) -> str:
        return (
            f"PipelineBuilder(name={self.pipeline_name!r}, "
            f"version={self.version!r})"
        )


# ---------------------------------------------------------------------------
# Collecte des stages — deux stratégies (miroir de job_decorator.py)
# ---------------------------------------------------------------------------


def _stages_from_explicit_list(fns: list[Callable]) -> list[PipelineStage]:
    """Construit les ``PipelineStage`` depuis une liste explicite."""
    stages: list[PipelineStage] = []
    for fn in fns:
        spec: StageSpec | None = getattr(fn, "__stage_spec__", None)
        if spec is None:
            raise ValueError(
                f"La fonction {fn.__name__!r} n'est pas décorée par @stage. "
                "Toutes les fonctions dans stages=[...] doivent être "
                "décorées par @stage."
            )
        stages.append(_spec_to_pipeline_stage(fn, spec))
    return stages


def _stages_from_bytecode(fn: Callable) -> list[PipelineStage]:
    """Collecte les ``PipelineStage`` en inspectant le bytecode.

    Stratégie (miroir de ``job_decorator._steps_from_bytecode``) :
    1. ``co_names`` + ``__globals__`` — stages module-level.
    2. ``co_freevars`` + ``__closure__`` — stages en scope englobant.
    """
    co_names_list: list[str] = list(fn.__code__.co_names)
    co_freevars_list: list[str] = list(fn.__code__.co_freevars)

    found: dict[str, tuple[int, PipelineStage]] = {}

    _collect_stages_from_globals(fn, co_names_list, found)
    _collect_stages_from_closure(fn, co_names_list, co_freevars_list, found)

    return [s for _, s in sorted(found.values(), key=lambda x: x[0])]


def _collect_stages_from_globals(
    fn: Callable,
    co_names_list: list[str],
    found: dict[str, tuple[int, PipelineStage]],
) -> None:
    """Peuple ``found`` depuis ``fn.__globals__``."""
    referenced: set[str] = set(co_names_list)
    for var_name, obj in fn.__globals__.items():
        if var_name not in referenced:
            continue
        spec: StageSpec | None = getattr(obj, "__stage_spec__", None)
        if spec is None:
            continue
        wrapped = getattr(obj, "__wrapped_fn__", obj)
        job_name = _resolve_job_name(wrapped, spec)
        try:
            order = co_names_list.index(var_name)
        except ValueError:
            order = 9999
        found[job_name] = (order, _spec_to_pipeline_stage(wrapped, spec))


def _collect_stages_from_closure(
    fn: Callable,
    co_names_list: list[str],
    co_freevars_list: list[str],
    found: dict[str, tuple[int, PipelineStage]],
) -> None:
    """Peuple ``found`` depuis ``fn.__closure__``."""
    if not fn.__closure__ or not co_freevars_list:
        return
    for i, cell in enumerate(fn.__closure__):
        if i >= len(co_freevars_list):
            break
        try:
            obj = cell.cell_contents
        except ValueError:
            continue
        spec: StageSpec | None = getattr(obj, "__stage_spec__", None)
        if spec is None:
            continue
        wrapped = getattr(obj, "__wrapped_fn__", obj)
        job_name = _resolve_job_name(wrapped, spec)
        if job_name in found:
            continue  # déjà trouvé via globals
        order = len(co_names_list) + i
        found[job_name] = (order, _spec_to_pipeline_stage(wrapped, spec))


# ---------------------------------------------------------------------------
# Résolution job_name / job
# ---------------------------------------------------------------------------


def _resolve_job_name(fn: Callable, spec: StageSpec) -> str:
    """Résout le nom du job depuis le ``StageSpec``.

    Priorité :
    1. ``spec.job_ref`` avec ``job_name`` (``JobBuilder``)
    2. ``spec.job_ref`` avec ``name`` (``Job`` model)
    3. Nom de la fonction décorée
    """
    ref = spec.job_ref
    if ref is not None:
        # JobBuilder → .job_name
        if hasattr(ref, "job_name"):
            return ref.job_name  # type: ignore[no-any-return]
        # Job → .name
        if hasattr(ref, "name"):
            return ref.name  # type: ignore[no-any-return]
    return fn.__name__


def _resolve_job(spec: StageSpec) -> Any:
    """Résout le ``Job`` depuis le ``StageSpec``.

    - Si ``job_ref`` est un ``JobBuilder`` → ``job_ref.build()``
    - Si ``job_ref`` est un ``Job`` → retourné tel quel
    - Sinon → ``None``
    """
    ref = spec.job_ref
    if ref is None:
        return None
    # JobBuilder
    if hasattr(ref, "build") and callable(ref.build):
        return ref.build()
    # Job (or any object with .name)
    if hasattr(ref, "name"):
        return ref
    return None


def _spec_to_pipeline_stage(fn: Callable, spec: StageSpec) -> PipelineStage:
    """Convertit une fonction + ``StageSpec`` en ``PipelineStage``."""
    return PipelineStage(
        job_name=_resolve_job_name(fn, spec),
        job=_resolve_job(spec),
        initial_context=dict(spec.initial_context),
        context_mapping=dict(spec.context_mapping),
        continue_on_failure=spec.continue_on_failure,
        condition=spec.condition,
        enabled=spec.enabled,
        metadata=dict(spec.metadata),
    )
