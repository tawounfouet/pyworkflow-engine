"""Schemas Pydantic — types communs (erreurs, health, pagination)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Format d'erreur standardisé."""

    error: str
    message: str
    detail: dict[str, Any] | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "JOB_NOT_FOUND",
                "message": "Job 'etl_v2' not found",
                "detail": {"job_name": "etl_v2"},
            }
        }
    }


class HealthResponse(BaseModel):
    """Réponse du health check."""

    status: str = "healthy"
    version: str
    storage_backend: str
    storage_status: str
    timestamp: datetime
    stats: dict[str, Any] | None = None


class PaginationParams(BaseModel):
    """Paramètres de pagination extraits des query strings."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        """Convertit page/page_size en offset pour la persistence."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias pour page_size (compatibilité persistence)."""
        return self.page_size
