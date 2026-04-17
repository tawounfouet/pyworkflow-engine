"""
pyworkflow_engine.models.ai.provider — Configuration fournisseur LLM.

Adapté de ai_engine/models/provider.py (ADR-013).
Les imports proviennent désormais de pyworkflow_engine.models.ai.types.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr

from pyworkflow_engine.models.ai.types import ProviderType
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


class ProviderCapabilities(BaseModel):
    """Capacités techniques d'un provider LLM."""

    vision: bool = False
    function_calling: bool = True
    streaming: bool = True
    context_window: int = 4096


class PricingConfig(BaseModel):
    """Configuration tarifaire d'un provider."""

    input_per_1k_tokens: float = 0.0
    output_per_1k_tokens: float = 0.0
    currency: str = "USD"


class ProviderSettings(BaseModel):
    """Paramètres de configuration d'un provider LLM."""

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = None
    max_retries: int = 2
    timeout: int = 30
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None


@ModelRegistry.register
class LLMProviderConfig(PersistableModel):
    """Configuration d'un fournisseur LLM/AI.

    Usage:
        provider = LLMProviderConfig(
            name="OpenAI GPT-4o",
            provider_type=ProviderType.OPENAI,
            default_model="gpt-4o",
            api_key="sk-...",
        )
    """

    __table_meta__: ClassVar[TableMeta] = TableMeta(
        table_name="ai_providers",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("provider_type", ColumnType.TEXT, nullable=False),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("default_model", ColumnType.TEXT, nullable=False),
            ColumnDef("api_key", ColumnType.TEXT),
            ColumnDef("api_base_url", ColumnType.TEXT),
            ColumnDef("extra_secrets", ColumnType.JSON),
            ColumnDef("settings", ColumnType.JSON),
            ColumnDef("capabilities", ColumnType.JSON),
            ColumnDef("pricing", ColumnType.JSON),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("is_default", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("provider_type",), ("is_active",)],
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    provider_type: ProviderType
    description: str = ""

    default_model: str = Field(
        ...,
        description="Nom du modèle (ex: gpt-4o, claude-3-opus, llama3)",
    )

    api_key: SecretStr | None = None
    api_base_url: str | None = None
    extra_secrets: dict[str, str] = Field(default_factory=dict)

    settings: ProviderSettings = Field(default_factory=ProviderSettings)
    capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    pricing: PricingConfig = Field(default_factory=PricingConfig)

    is_active: bool = True
    is_default: bool = False

    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_api_key_value(self) -> str | None:
        """Retourne la valeur de la clé API (déchiffrée)."""
        if self.api_key is None:
            return None
        return self.api_key.get_secret_value()

    def get_secret(self, key: str, default: str = "") -> str:
        """Récupère une valeur depuis extra_secrets."""
        return self.extra_secrets.get(key, default)
