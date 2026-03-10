"""
API publique des modèles core — exposition clean des types principaux.

Ce module expose l'API publique pour les modèles de workflow,
organisée selon les besoins des utilisateurs du package.

Import hierarchy:
    - Enums (types de base)
    - Design-time models (définitions)
    - Runtime models (exécutions)
    - Helper functions (utilitaires)
"""

from __future__ import annotations

# Enums - Types de base
from .enums import (
    TriggerType,
    StepType,
    ExecutorType,
    RunStatus,
    Priority,
    TERMINAL_STATUSES,
    SUSPENDED_STATUSES,
    ACTIVE_STATUSES,
    is_terminal,
    is_suspended,
    is_active,
    can_resume,
    can_cancel,
)

# Design-time models - Définitions de workflows
from .design_time import (
    Step,
    SubJob,
    Job,
)

# Runtime models - Instances d'exécution
from .runtime import (
    StepLog,
    StepRun,
    JobRun,
    utc_now,
    generate_id,
)

# API publique organisée par usage
__all__ = [
    # === ENUMS ===
    "TriggerType",
    "StepType",
    "ExecutorType",
    "RunStatus",
    "Priority",
    # === STATUS HELPERS ===
    "TERMINAL_STATUSES",
    "SUSPENDED_STATUSES",
    "ACTIVE_STATUSES",
    "is_terminal",
    "is_suspended",
    "is_active",
    "can_resume",
    "can_cancel",
    # === DESIGN-TIME MODELS ===
    "Step",
    "SubJob",
    "Job",
    # === RUNTIME MODELS ===
    "StepLog",
    "StepRun",
    "JobRun",
    # === UTILITIES ===
    "utc_now",
    "generate_id",
]


# Version des modèles pour compatibilité
__version__ = "1.0.0"
