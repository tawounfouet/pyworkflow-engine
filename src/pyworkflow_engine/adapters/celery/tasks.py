"""Celery tasks — wrappers pour l'exécution sérialisée des steps.

Ce module définit les tasks Celery qui s'exécutent côté worker.
Il utilise ``@shared_task`` pour ne pas être lié à une instance Celery
spécifique, conformément aux bonnes pratiques pour les bibliothèques.

Les workers doivent importer ce module pour enregistrer les tasks :

    celery -A pyworkflow_engine.adapters.celery.tasks worker --loglevel=info

Contrainte critique : les handlers de steps doivent être des **fonctions
top-level importables** (pas de lambdas, closures, ou méthodes d'instance).
Le handler est transmis via son nom qualifié (``module.func_name``).
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_handler(handler_ref: str) -> Any:
    """Résout une référence qualifiée en callable.

    Args:
        handler_ref: Référence sous forme ``"module.path.function_name"``.

    Returns:
        Le callable correspondant.

    Raises:
        ImportError: Si le module n'existe pas.
        AttributeError: Si la fonction n'existe pas dans le module.
        ValueError: Si la référence n'est pas un chemin qualifié valide.
    """
    if "." not in handler_ref:
        raise ValueError(
            f"Handler ref '{handler_ref}' invalide. "
            "Le handler doit être une fonction top-level importable "
            "sous la forme 'module.function_name'."
        )
    module_path, _, func_name = handler_ref.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def execute_step_task(
    handler_ref: str,
    context_dict: dict[str, Any],
    step_name: str = "",
) -> dict[str, Any]:
    """Exécute un step sur un worker Celery.

    Cette fonction est enregistrée comme Celery task via ``register_task``
    sur l'app Celery du CeleryExecutor (via ``app.task``).

    Args:
        handler_ref: Référence qualifiée du handler (``"module.func"``).
        context_dict: Contexte sérialisé (sortie de ``WorkflowContext.to_dict()``).
        step_name: Nom du step (pour les logs).

    Returns:
        Résultat du handler sous forme de dict. Si le handler retourne
        une valeur non-dict, elle est encapsulée dans ``{"result": value}``.

    Raises:
        ImportError: Si le handler n'est pas importable.
        Exception: Toute exception levée par le handler est propagée
            (Celery la capture et marque la task comme FAILED).
    """
    logger.debug("Celery: exécution step '%s' via handler '%s'", step_name, handler_ref)

    handler = _resolve_handler(handler_ref)

    # Inspecter la signature pour décider si on passe le contexte
    import inspect

    try:
        sig = inspect.signature(handler)
        params = [
            p
            for p in sig.parameters.values()
            if p.name not in ("self", "cls")
            and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        ]
        if params:
            result = handler(context_dict)
        else:
            result = handler()
    except Exception:
        logger.exception("Celery: échec step '%s'", step_name)
        raise

    if result is None:
        return {}
    if not isinstance(result, dict):
        return {"result": result}
    return result


def make_celery_task(celery_app: Any) -> Any:
    """Enregistre ``execute_step_task`` comme task Celery sur une app donnée.

    Retourne la task enregistrée, prête à être appelée via ``.delay()``
    ou ``.apply_async()``.

    Args:
        celery_app: Instance Celery sur laquelle enregistrer la task.

    Returns:
        La task Celery enregistrée.
    """
    return celery_app.task(
        name="pyworkflow_engine.execute_step",
        bind=False,
        serializer="json",
        acks_late=True,
        reject_on_worker_lost=True,
    )(execute_step_task)
