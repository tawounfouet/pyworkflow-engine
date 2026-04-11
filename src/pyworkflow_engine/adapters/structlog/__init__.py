"""
Adapter structlog — pip install pyworkflow-engine[structlog]

Bridge entre le stdlib logging du core et structlog pour les utilisateurs
qui veulent un logging structuré avancé (processors, contextvars, etc.).

Usage :
    from pyworkflow_engine.adapters.structlog import configure_structlog

    configure_structlog()  # Branche structlog sur le logging du core

    # À partir de là, tous les logs du core passent par structlog
    from pyworkflow_engine.logging import get_logger
    logger = get_logger("engine.facade")
    logger.info("workflow started", job_id="abc-123")
    # → Formaté par structlog avec couleurs, contexte, etc.
"""

from .setup import configure_structlog

__all__ = ["configure_structlog"]
