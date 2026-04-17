"""
Bridge adapter : exécute un connecteur ``pyconnectors`` comme step de workflow.

Ce module est le **seul point de contact** entre ``pyworkflow_engine`` et
``pyconnectors``.  Il utilise un lazy import pour que le core ne dépende
jamais statiquement de ``pyconnectors``.

Usage typique dans un step décoré ::

    from pyworkflow_engine.decorators import step
    from pyworkflow_engine.models.enums import StepType
    from pyworkflow_engine.models.workflow.connector import ConnectorRef
    from pyworkflow_engine.adapters.steps.connector_step import execute_connector

    pg_ref = ConnectorRef(
        connector_name="database.postgresql",
        config={"params": {"dsn": "${POSTGRES_DSN}"}},
    )

    @step(name="extract_users", step_type=StepType.CONNECTOR)
    def extract_users() -> dict:
        outcome = execute_connector(ref=pg_ref, query="SELECT * FROM users")
        return {"users": outcome.metadata.get("rows", []), "count": outcome.records_affected}

Voir ADR-016 pour la conception complète.
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.exceptions import StepExecutionError
from pyworkflow_engine.models.workflow.connector import ConnectorOutcome, ConnectorRef


def execute_connector(
    ref: ConnectorRef,
    **execute_kwargs: Any,
) -> ConnectorOutcome:
    """Exécute un connecteur ``pyconnectors`` et retourne un ``ConnectorOutcome`` typé.

    Le bridge :

    1. Lazy-importe ``pyconnectors``
    2. Crée le connecteur via ``ConnectorFactory``
    3. Appelle l'action demandée (``ref.action``, défaut ``"execute"``)
    4. Traduit ``ConnectorResult`` → ``ConnectorOutcome``
    5. Lève ``StepExecutionError`` si échec

    Args:
        ref: Référence au connecteur (nom, config, action).
        **execute_kwargs: Arguments passés à la méthode du connecteur.

    Returns:
        ``ConnectorOutcome`` avec le statut, la durée, les métadonnées.

    Raises:
        StepExecutionError: Si ``pyconnectors`` n'est pas installé, si
            l'action n'existe pas, ou si l'exécution échoue.
    """
    # ── 1. Lazy import ─────────────────────────────────────────────────
    try:
        from pyconnectors.config import ConnectorConfig  # noqa: PLC0415
        from pyconnectors.services.factory import ConnectorFactory  # noqa: PLC0415
    except ImportError as exc:
        raise StepExecutionError(
            "pyconnectors is not installed. "
            "Install with: pip install 'pyworkflow-engine[connectors]'",
            step_name=ref.connector_name,
        ) from exc

    # ── 2. Création du connecteur ──────────────────────────────────────
    config = ConnectorConfig.from_dict(ref.config)
    connector = ConnectorFactory.create(ref.connector_name, config=config)

    # ── 3. Résolution de l'action ──────────────────────────────────────
    # On préfère safe_execute (action="execute") ou la méthode explicite
    if ref.action == "execute":
        method = getattr(connector, "safe_execute", None)
    else:
        method = getattr(connector, ref.action, None)

    if method is None:
        raise StepExecutionError(
            f"Connector '{ref.connector_name}' has no action '{ref.action}'",
            step_name=ref.connector_name,
        )

    # ── 4. Exécution ───────────────────────────────────────────────────
    try:
        result = method(**execute_kwargs)
    except Exception as exc:
        outcome = ConnectorOutcome(
            connector_name=ref.connector_name,
            connector_type=ref.connector_type,
            success=False,
            error=str(exc),
        )
        raise StepExecutionError(
            f"Connector '{ref.connector_name}' raised: {exc}",
            step_name=ref.connector_name,
            details=outcome.to_dict(),
        ) from exc

    # ── 5. Traduction ConnectorResult → ConnectorOutcome ───────────────
    outcome = ConnectorOutcome.from_connector_result(
        result,
        connector_name=ref.connector_name,
        connector_type=ref.connector_type,
    )

    if not outcome.success:
        raise StepExecutionError(
            f"Connector '{ref.connector_name}' failed: {outcome.error}",
            step_name=ref.connector_name,
            details=outcome.to_dict(),
        )

    return outcome


# ---------------------------------------------------------------------------
# Helpers privés
# ---------------------------------------------------------------------------


def _build_summary(data: Any) -> dict[str, Any]:
    """Construit un résumé léger des données retournées par le connecteur.

    Seul le *type* et la *taille* sont conservés — les données brutes
    restent dans le contexte du workflow, pas dans le ``ConnectorOutcome``.
    """
    if data is None:
        return {}
    if isinstance(data, list):
        return {"type": "list", "count": len(data)}
    if isinstance(data, dict):
        return {"type": "dict", "keys": list(data.keys())[:20]}
    return {"type": type(data).__name__}
