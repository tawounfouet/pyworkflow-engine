"""
Modèles connector — vue workflow (design-time + runtime).

Ces modèles décrivent la **référence** à un connecteur externe et le
**résultat** de son exécution dans le contexte d'un workflow.

⚠️ Ces modèles NE DUPLIQUENT PAS ``pyconnectors``.
    - ``ConnectorRef``     = "quel connecteur utiliser"   (design-time, frozen)
    - ``ConnectorOutcome`` = "qu'a retourné le connecteur" (runtime, mutable)

``pyconnectors`` reste le package qui gère la connexion, l'auth, l'exécution.
Ces modèles sont le **contrat d'interface** côté workflow.

Migration D2 (vague 1) — ADR-018 :
    Convertis de ``dataclass`` en Pydantic ``BaseModel``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def _utc_now() -> datetime:
    """Retourne l'heure UTC actuelle."""
    return datetime.now(UTC)


def _generate_id() -> str:
    """Génère un identifiant UUID4 unique."""
    return str(uuid4())


# ---------------------------------------------------------------------------
# Design-time : référence à un connecteur
# ---------------------------------------------------------------------------


class ConnectorRef(BaseModel):
    """Référence à un connecteur ``pyconnectors`` dans un Step.

    Décrit *quel* connecteur utiliser et *avec quelle configuration*,
    sans importer ni dépendre de ``pyconnectors``.

    Attributes:
        connector_name: Nom du connecteur dans le registre ``pyconnectors``
            (ex: ``"database.postgresql"``, ``"http.rest"``, ``"social.slack"``).
        connector_type: Catégorie du connecteur (ex: ``"database"``, ``"http"``,
            ``"storage"``, ``"social"``, ``"email"``).  Optionnel — déduit du
            nom si non fourni.
        config: Configuration à passer à ``ConnectorConfig.from_dict()``.
            Ne contient jamais de secrets en clair — utiliser des références
            ``${ENV_VAR}`` ou un secret manager.
        action: Méthode à appeler sur le connecteur (défaut: ``"execute"``).
        description: Description lisible pour la documentation / GUI.

    Examples:
        >>> ref = ConnectorRef(
        ...     connector_name="database.postgresql",
        ...     config={"params": {"dsn": "${POSTGRES_DSN}"}},
        ...     action="execute",
        ...     description="Extraction des utilisateurs actifs",
        ... )
        >>> ref.connector_type
        'database'
        >>> d = ref.to_dict()
        >>> restored = ConnectorRef.from_dict(d)
        >>> restored == ref
        True
    """

    model_config = {"frozen": True}

    connector_name: str
    connector_type: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    action: str = "execute"
    description: str = ""

    @model_validator(mode="after")
    def _derive_connector_type(self) -> ConnectorRef:
        """Déduit ``connector_type`` depuis ``connector_name`` si non fourni."""
        if not self.connector_type and "." in self.connector_name:
            object.__setattr__(
                self, "connector_type", self.connector_name.split(".")[0]
            )
        return self

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible."""
        return {
            "connector_name": self.connector_name,
            "connector_type": self.connector_type,
            "config": dict(self.config),
            "action": self.action,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectorRef:
        """Désérialise depuis un dict."""
        return cls(
            connector_name=data["connector_name"],
            connector_type=data.get("connector_type", ""),
            config=data.get("config", {}),
            action=data.get("action", "execute"),
            description=data.get("description", ""),
        )

    def __repr__(self) -> str:
        return (
            f"ConnectorRef({self.connector_name!r}, "
            f"type={self.connector_type!r}, action={self.action!r})"
        )


# ---------------------------------------------------------------------------
# Runtime : résultat d'exécution d'un connecteur
# ---------------------------------------------------------------------------


class ConnectorOutcome(BaseModel):
    """Résultat de l'exécution d'un connecteur dans un StepRun.

    Capture les métadonnées standardisées retournées par le bridge
    ``adapters/steps/connector_step.py``.  Stocké dans
    ``StepRun.connector_outcome``.

    Attributes:
        id: Identifiant unique de cette exécution connecteur.
        connector_name: Nom du connecteur utilisé.
        connector_type: Catégorie (``"database"``, ``"http"``, etc.).
        success: ``True`` si le connecteur a retourné sans erreur.
        duration: Durée d'exécution en secondes (aligné sur ``ConnectorResult.duration``).
        error: Message d'erreur si ``success=False``, ``None`` sinon.
        records_affected: Nombre de lignes/objets affectés (optionnel).
        data_summary: Résumé des données retournées (pas les données brutes
            — celles-ci restent dans le contexte du workflow).
        metadata: Métadonnées libres retournées par le connecteur.
        executed_at: Timestamp d'exécution.

    Examples:
        >>> outcome = ConnectorOutcome(
        ...     connector_name="database.postgresql",
        ...     connector_type="database",
        ...     success=True,
        ...     duration=1.234,
        ...     records_affected=1500,
        ...     data_summary={"row_count": 1500, "columns": ["id", "name"]},
        ... )
        >>> outcome.success
        True
        >>> d = outcome.to_dict()
        >>> restored = ConnectorOutcome.from_dict(d)
    """

    id: str = Field(default_factory=_generate_id)
    connector_name: str = ""
    connector_type: str = ""
    success: bool = False
    duration: float = 0.0
    error: str | None = None
    records_affected: int | None = None
    data_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    executed_at: datetime = Field(default_factory=_utc_now)

    # ------------------------------------------------------------------
    # Constructeur depuis ConnectorResult (pyconnectors)
    # ------------------------------------------------------------------

    @classmethod
    def from_connector_result(
        cls,
        result: Any,
        *,
        connector_name: str = "",
        connector_type: str = "",
        records_affected: int | None = None,
        data_summary: dict[str, Any] | None = None,
    ) -> ConnectorOutcome:
        """Construit un ``ConnectorOutcome`` depuis un ``pyconnectors.ConnectorResult``.

        Args:
            result: Instance de ``pyconnectors.models.result.ConnectorResult``.
            connector_name: Nom du connecteur (ex: ``"database.postgresql"``).
            connector_type: Catégorie déduite ou fournie.
            records_affected: Nombre de lignes affectées (optionnel).
            data_summary: Résumé des données — si None, construit depuis result.data.
        """
        if data_summary is None:
            data = getattr(result, "data", None)
            if isinstance(data, list):
                data_summary = {"type": "list", "count": len(data)}
            elif isinstance(data, dict):
                data_summary = {"type": "dict", "keys": list(data.keys())[:20]}
            elif data is not None:
                data_summary = {"type": type(data).__name__}
            else:
                data_summary = {}

        # records_affected : priorité à l'argument explicite, sinon depuis metadata
        if records_affected is None:
            records_affected = (getattr(result, "metadata", None) or {}).get(
                "records_affected"
            )

        return cls(
            connector_name=connector_name,
            connector_type=connector_type,
            success=getattr(result, "success", False),
            duration=round(getattr(result, "duration", 0.0), 4),
            error=getattr(result, "error", None) or None,
            records_affected=records_affected,
            data_summary=data_summary,
            metadata=getattr(result, "metadata", None) or {},
        )

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible."""
        return {
            "id": self.id,
            "connector_name": self.connector_name,
            "connector_type": self.connector_type,
            "success": self.success,
            "duration": self.duration,
            "error": self.error,
            "records_affected": self.records_affected,
            "data_summary": self.data_summary,
            "metadata": self.metadata,
            "executed_at": self.executed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectorOutcome:
        """Désérialise depuis un dict."""
        executed_at = data.get("executed_at")
        if isinstance(executed_at, str):
            executed_at = datetime.fromisoformat(executed_at)
        return cls(
            id=data.get("id", _generate_id()),
            connector_name=data.get("connector_name", ""),
            connector_type=data.get("connector_type", ""),
            success=data.get("success", False),
            # rétrocompat : accepte l'ancien nom "duration_seconds"
            duration=data.get("duration", data.get("duration_seconds", 0.0)),
            error=data.get("error") or None,
            records_affected=data.get("records_affected"),
            data_summary=data.get("data_summary", {}),
            metadata=data.get("metadata", {}),
            executed_at=executed_at or _utc_now(),
        )

    def __repr__(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"ConnectorOutcome({status} {self.connector_name!r}, "
            f"{self.duration:.3f}s)"
        )
