"""
adapters/ai/storage — Backends de persistence IA.

Disponibles :
  - InMemoryAIStorage  : pour les tests et le prototypage (pas de disk).
  - SQLiteAIStorage    : backend SQLite durable (ADR-020 Phase 1a).
"""

from __future__ import annotations

from pyworkflow_engine.adapters.ai.storage.memory import InMemoryAIStorage
from pyworkflow_engine.adapters.ai.storage.sqlite import SQLiteAIStorage

__all__ = ["InMemoryAIStorage", "SQLiteAIStorage"]
