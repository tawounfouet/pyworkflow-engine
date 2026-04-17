"""
``JobBuilder`` et décorateur ``@job`` — composition de ``@step`` en ``Job``.

``@job`` retourne un ``JobBuilder`` au lieu d'une fonction ordinaire.
``JobBuilder.build()`` inspecte les fonctions ``@step`` référencées dans
le corps du ``@job`` pour construire un objet ``Job`` standard, exécutable
par ``WorkflowEngine.run()``.

Deux modes de collecte des steps :

* **Mode implicite** (par défaut) — introspection via ``co_names`` + ``__globals__``.
  Couvre tous les cas courants (steps définis au module-level).
* **Mode explicite** — ``@job(steps=[fn1, fn2])`` — robuste pour les steps
  importés dynamiquement ou définis en dehors du module courant.
"""

from __future__ import annotations

import functools
import inspect
from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from pyworkflow_engine.decorators.step_decorator import StepSpec
from pyworkflow_engine.models.enums import StepType
from pyworkflow_engine.models.workflow.job import Job
from pyworkflow_engine.models.workflow.step import Step


def job(
    name: str | None = None,
    *,
    version: str = "1.0.0",
    description: str = "",
    steps: list[Callable] | None = None,
    tags: list[str] | None = None,
) -> Callable:
    """Décorateur qui compose des fonctions ``@step`` en un ``Job``.

    La fonction décorée sert de **déclaration** (son corps n'est pas exécuté
    par ``build()``). Le décorateur analyse les fonctions ``@step`` référencées
    — soit par introspection du bytecode, soit via ``steps=[...]`` — pour
    construire un ``Job`` standard.

    Args:
        name: Nom du job. Par défaut : nom de la fonction.
        version: Version sémantique du job. Par défaut : ``"1.0.0"``.
        description: Description textuelle. Par défaut : docstring de la fonction.
        steps: Liste explicite de fonctions ``@step``. Si fourni, l'introspection
            bytecode est ignorée. Recommandé pour les steps importés dynamiquement.
        tags: Tags pour catégorisation et recherche.

    Returns:
        Un ``JobBuilder`` — appelable comme la fonction originale, mais enrichi
        d'une méthode ``build()`` pour produire l'objet ``Job``.

    Examples:
        >>> from pyworkflow_engine.decorators import step, job

        >>> @step(name="fetch")
        ... def fetch_data(source: str = "api") -> dict:
        ...     return {"records": [1, 2, 3]}

        >>> @step(name="transform", dependencies=["fetch"])
        ... def transform_data(records: list | None = None) -> dict:
        ...     return {"out": [r * 10 for r in (records or [])]}

        >>> @job(name="ETL Pipeline")
        ... def etl():
        ...     data = fetch_data()
        ...     transform_data(records=data["records"])

        >>> etl_job = etl.build()
        >>> etl_job.name
        'ETL Pipeline'
        >>> [s.name for s in etl_job.steps]
        ['fetch', 'transform']

        >>> # Mode explicite (steps importés depuis d'autres modules)
        >>> @job(name="ETL Pipeline", steps=[fetch_data, transform_data])
        ... def etl_explicit(): ...
    """

    def decorator(fn: Callable) -> JobBuilder:
        _name = name or fn.__name__
        _description = description or (fn.__doc__ or "").strip()
        builder = JobBuilder(
            fn=fn,
            job_name=_name,
            version=version,
            description=_description,
            explicit_steps=steps,
            tags=list(tags or []),
        )
        functools.update_wrapper(builder, fn)
        return builder

    return decorator


class JobBuilder:
    """Objet retourné par ``@job``.

    Peut être appelé comme la fonction originale (pour le debug ou les tests),
    et expose une méthode ``build()`` pour produire l'objet ``Job`` standard.

    Attributes:
        job_name: Nom du job.
        version: Version du job.
        description: Description du job.
    """

    def __init__(
        self,
        fn: Callable,
        job_name: str,
        version: str,
        description: str,
        explicit_steps: list[Callable] | None,
        tags: list[str],
    ) -> None:
        self._fn = fn
        self.job_name = job_name
        self.version = version
        self.description = description
        self._explicit_steps = explicit_steps
        self._tags = tags

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> Job:
        """Construit un objet ``Job`` à partir des fonctions ``@step`` associées.

        Si ``steps=[...]`` a été fourni au décorateur, ces fonctions sont utilisées
        directement. Sinon, le bytecode de la fonction ``@job`` est inspecté pour
        trouver les fonctions ``@step`` référencées dans le scope global.

        Returns:
            Un ``Job`` valide, exécutable par ``WorkflowEngine.run()``.

        Raises:
            ValueError: Si aucun step décoré par ``@step`` n'est trouvé.
        """
        if self._explicit_steps is not None:
            steps = _steps_from_explicit_list(self._explicit_steps)
        else:
            steps = _steps_from_bytecode(self._fn)

        return Job(
            name=self.job_name,
            version=self.version,
            description=self.description,
            steps=steps,
            tags=self._tags,
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Appelle la fonction originale (utile pour le debug / tests manuels)."""
        return self._fn(*args, **kwargs)

    def __repr__(self) -> str:
        return f"JobBuilder(name={self.job_name!r}, version={self.version!r})"


# ------------------------------------------------------------------
# Collecte des steps — deux stratégies
# ------------------------------------------------------------------


def _steps_from_explicit_list(fns: list[Callable]) -> list[Step]:
    """Construit les ``Step`` depuis une liste explicite de fonctions ``@step``."""
    steps: list[Step] = []
    for fn in fns:
        spec: StepSpec | None = getattr(fn, "__step_spec__", None)
        if spec is None:
            raise ValueError(
                f"La fonction {fn.__name__!r} n'est pas décorée par @step. "
                "Toutes les fonctions dans steps=[...] doivent être décorées par @step."
            )
        wrapped = getattr(fn, "__wrapped_fn__", fn)
        steps.append(_spec_to_step(wrapped, spec))
    return steps


def _steps_from_bytecode(fn: Callable) -> list[Step]:
    """Collecte les ``Step`` en inspectant le bytecode de la fonction ``@job``.

    Stratégie (dans l'ordre) :
    1. ``co_names`` + ``__globals__`` — cas standard : steps définis au module-level.
    2. ``co_freevars`` + ``__closure__`` — cas closures : steps définis dans le
       même scope local que la fonction ``@job`` (ex. méthode de test, factory).

    Les deux sources sont fusionnées et triées par ordre d'apparition.
    """
    co_names_list: list[str] = list(fn.__code__.co_names)
    co_freevars_list: list[str] = list(fn.__code__.co_freevars)

    # name → (order, Step) — dict pour dédupliquer, globals prioritaires
    found: dict[str, tuple[int, Step]] = {}

    _collect_from_globals(fn, co_names_list, found)
    _collect_from_closure(fn, co_names_list, co_freevars_list, found)

    return [s for _, s in sorted(found.values(), key=lambda x: x[0])]


def _collect_from_globals(
    fn: Callable,
    co_names_list: list[str],
    found: dict[str, tuple[int, Step]],
) -> None:
    """Peuple ``found`` depuis ``fn.__globals__`` (steps définis au module-level)."""
    referenced: set[str] = set(co_names_list)
    for var_name, obj in fn.__globals__.items():
        if var_name not in referenced:
            continue
        spec: StepSpec | None = getattr(obj, "__step_spec__", None)
        if spec is None:
            continue
        wrapped = getattr(obj, "__wrapped_fn__", obj)
        try:
            order = co_names_list.index(var_name)
        except ValueError:
            order = 9999
        found[spec.name] = (order, _spec_to_step(wrapped, spec))


def _collect_from_closure(
    fn: Callable,
    co_names_list: list[str],
    co_freevars_list: list[str],
    found: dict[str, tuple[int, Step]],
) -> None:
    """Peuple ``found`` depuis ``fn.__closure__`` (steps en scope englobant)."""
    if not fn.__closure__ or not co_freevars_list:
        return
    for i, cell in enumerate(fn.__closure__):
        if i >= len(co_freevars_list):
            break
        var_name = co_freevars_list[i]
        try:
            obj = cell.cell_contents
        except ValueError:
            continue  # cellule vide
        spec: StepSpec | None = getattr(obj, "__step_spec__", None)
        if spec is None or spec.name in found:
            continue  # pas un step, ou déjà trouvé via globals (prioritaire)
        wrapped = getattr(obj, "__wrapped_fn__", obj)
        order = len(co_names_list) + i
        found[spec.name] = (order, _spec_to_step(wrapped, spec))


def _spec_to_step(fn: Callable, spec: StepSpec) -> Step:
    """Convertit une fonction pure + son ``StepSpec`` en objet ``Step``.

    Crée un context-adapter autour de ``fn`` afin que ``WorkflowRunner``
    puisse l'appeler avec la signature standard ``handler(context)``.
    Les champs ``condition`` et ``metadata`` de ``StepSpec`` sont transmis
    tels quels à ``Step``.
    """
    timeout_td = timedelta(seconds=spec.timeout) if spec.timeout is not None else None
    retry_delay_td = timedelta(seconds=spec.retry_delay)

    return Step(
        name=spec.name,
        step_type=spec.step_type,
        handler=_make_context_adapter(fn, spec),
        dependencies=list(spec.dependencies),
        retry_count=spec.retry_count,
        retry_delay=retry_delay_td,
        timeout=timeout_td,
        condition=spec.condition,
        metadata=dict(spec.metadata),
    )


# ------------------------------------------------------------------
# Context adapter — injection de paramètres
# ------------------------------------------------------------------


def _make_context_adapter(fn: Callable, spec: StepSpec) -> Callable:
    """Crée un wrapper ``handler(context)`` autour d'une fonction pure.

    Résolution des paramètres (dans l'ordre de priorité) :

    1. **Legacy** : si la signature est ``fn(context)`` (un seul paramètre nommé
       exactement ``context``), le handler est passé tel quel — comportement
       identique à l'API impérative existante.

    2. **Injection depuis les outputs des dépendances** : pour chaque paramètre
       de ``fn``, on cherche la clé correspondante dans les dicts de sortie des
       steps déclarés dans ``spec.dependencies`` (premier match gagne).

    3. **Injection depuis le contexte global** : clé recherchée dans
       ``context.get(param_name)``.

    4. **Valeur par défaut** : si le paramètre a une valeur par défaut dans la
       signature, elle est utilisée comme fallback.

    5. **None** : si aucune source ne produit de valeur, le paramètre reçoit
       ``None`` (pour éviter une TypeError silencieuse, un warning sera loggé).

    Args:
        fn: La fonction pure à adapter (``__wrapped_fn__``).
        spec: Le ``StepSpec`` de la fonction, contenant les dépendances.

    Returns:
        Un callable ``handler(context) -> Any`` compatible avec ``WorkflowRunner``.
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.keys())

    # ── Mode legacy : fn(context) ──────────────────────────────────────────
    if len(params) == 1 and params[0] == "context":
        return fn

    # ── Mode injection ─────────────────────────────────────────────────────
    def adapter(context: Any) -> Any:
        kwargs: dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            value: Any = _SENTINEL

            # 1. Outputs des steps dépendants
            for dep_name in spec.dependencies:
                dep_output = context.get_step_output(dep_name, {})
                if isinstance(dep_output, dict) and param_name in dep_output:
                    value = dep_output[param_name]
                    break

            # 2. Contexte global (initial_context + données accumulées)
            if value is _SENTINEL:
                ctx_value = context.get(param_name)
                if ctx_value is not None:
                    value = ctx_value

            # 3. Valeur par défaut de la signature
            if value is _SENTINEL:
                if param.default is not inspect.Parameter.empty:
                    value = param.default
                else:
                    value = None  # dernier recours — None explicite

            kwargs[param_name] = value

        return fn(**kwargs)

    # Copier name/doc/module pour les traces — mais PAS __wrapped__,
    # car inspect.signature() suit __wrapped__ et retournerait la signature
    # de fn (0 params) au lieu de adapter(context) — ce qui tromperait runner.py.
    adapter.__name__ = getattr(fn, "__name__", "step_adapter")  # type: ignore[attr-defined]
    adapter.__qualname__ = getattr(fn, "__qualname__", "step_adapter")  # type: ignore[attr-defined]
    adapter.__doc__ = fn.__doc__
    adapter.__module__ = fn.__module__
    return adapter


# Sentinelle privée — distingue "pas de valeur trouvée" de None explicite
_SENTINEL: object = object()
