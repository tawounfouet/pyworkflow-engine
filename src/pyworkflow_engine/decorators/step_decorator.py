"""
Décorateur ``@step`` — transforme une fonction Python en step de workflow.

La fonction décorée reste une fonction Python normale, appelable directement
(pour les tests unitaires). Les métadonnées d'orchestration sont stockées dans
l'attribut ``__step_spec__`` (un ``StepSpec`` frozen dataclass).

Utilise uniquement ``functools``, ``inspect``, ``dataclasses`` (stdlib).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from pyworkflow_engine.models.enums import StepType


@dataclass(frozen=True)
class StepSpec:
    """Métadonnées d'orchestration attachées à une fonction décorée par ``@step``.

    Stockées dans ``fn.__step_spec__``. Ne contient aucune logique d'exécution —
    c'est un descripteur pur qui sera lu par ``JobBuilder`` pour construire un
    objet ``Step`` standard.

    Attributes:
        name: Nom du step tel qu'il apparaîtra dans le ``Job``.
        step_type: Type d'exécution (FUNCTION, HUMAN_TASK, etc.).
        dependencies: Noms des steps dont celui-ci dépend.
        retry_count: Nombre de tentatives en cas d'échec (0 = pas de retry).
        retry_delay: Délai en secondes entre les tentatives.
        timeout: Timeout d'exécution en secondes (None = pas de timeout).
        executor_type: Nom de l'executor à utiliser (None = executor par défaut).
        tags: Métadonnées arbitraires (labels, équipe, etc.).
    """

    name: str
    step_type: StepType = StepType.FUNCTION
    dependencies: list[str] = field(default_factory=list)
    retry_count: int = 0
    retry_delay: float = 1.0
    timeout: float | None = None
    executor_type: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


def step(
    name: str | None = None,
    *,
    dependencies: list[str] | None = None,
    step_type: StepType = StepType.FUNCTION,
    retry_count: int = 0,
    retry_delay: float = 1.0,
    timeout: float | None = None,
    executor_type: str | None = None,
    tags: dict[str, str] | None = None,
) -> Callable:
    """Décorateur qui marque une fonction comme step de workflow.

    La fonction décorée reste **appelable normalement** — aucun comportement
    runtime n'est ajouté. Les métadonnées d'orchestration sont stockées dans
    ``fn.__step_spec__`` et lues plus tard par ``JobBuilder.build()``.

    Args:
        name: Nom du step. Par défaut : nom de la fonction.
        dependencies: Noms des steps dont celui-ci dépend.
        step_type: Type d'exécution. Par défaut : ``StepType.FUNCTION``.
        retry_count: Nombre de tentatives en cas d'échec. Par défaut : 0.
        retry_delay: Délai entre les tentatives (secondes). Par défaut : 1.0.
        timeout: Timeout d'exécution (secondes). Par défaut : None.
        executor_type: Nom de l'executor personnalisé. Par défaut : None.
        tags: Métadonnées arbitraires. Par défaut : {}.

    Returns:
        La fonction originale, inchangée fonctionnellement, avec ``__step_spec__``
        et ``__wrapped_fn__`` attachés.

    Examples:
        >>> @step(name="fetch", timeout=30.0)
        ... def fetch_data(source: str = "default") -> dict:
        ...     return {"records": [1, 2, 3], "source": source}
        >>>
        >>> # Attributs d'orchestration
        >>> fetch_data.__step_spec__.name
        'fetch'
        >>> fetch_data.__step_spec__.timeout
        30.0
        >>>
        >>> # Appelable normalement — aucun mock nécessaire
        >>> fetch_data(source="api")
        {'records': [1, 2, 3], 'source': 'api'}

        >>> # Décorateur sans parenthèses (nom par défaut = nom de la fonction)
        >>> @step
        ... def process(data: list) -> dict:
        ...     return {"count": len(data)}
        >>>
        >>> process.__step_spec__.name
        'process'
    """

    # Permet l'usage sans parenthèses : @step (sans arguments)
    # Dans ce cas, `name` reçoit directement la fonction décorée.
    if callable(name):
        fn = name
        spec = StepSpec(name=fn.__name__)
        return _attach_spec(fn, spec)

    def decorator(fn: Callable) -> Callable:
        spec = StepSpec(
            name=name or fn.__name__,
            step_type=step_type,
            dependencies=list(dependencies or []),
            retry_count=retry_count,
            retry_delay=retry_delay,
            timeout=timeout,
            executor_type=executor_type,
            tags=dict(tags or {}),
        )
        return _attach_spec(fn, spec)

    return decorator


def _attach_spec(fn: Callable, spec: StepSpec) -> Callable:
    """Attache un ``StepSpec`` à une fonction via ``functools.wraps``."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    # Métadonnées d'orchestration
    wrapper.__step_spec__ = spec  # type: ignore[attr-defined]
    # Référence à la fonction originale (utile pour l'introspection / les tests)
    wrapper.__wrapped_fn__ = fn  # type: ignore[attr-defined]
    return wrapper
