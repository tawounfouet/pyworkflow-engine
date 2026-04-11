"""Schemas Pydantic — DTOs pour les executors."""

from __future__ import annotations

from pydantic import BaseModel


class ExecutorInfo(BaseModel):
    """Information sur un executor enregistré."""

    name: str
    executor_type: str
