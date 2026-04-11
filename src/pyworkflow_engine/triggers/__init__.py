"""
PyWorkflow Engine — couche triggers (déclencheurs de workflows).

Ce package contient les déclencheurs de workflows :

- ``base``     : BaseTrigger (ABC) — contrat commun à tous les triggers
- ``manual``   : ManualTrigger — déclenchement explicite par code
- ``schedule`` : ScheduleTrigger — déclenchement cron (stdlib, sans Celery)
"""

from __future__ import annotations

from .base import BaseTrigger, TriggerState
from .manual import ManualTrigger
from .schedule import ScheduleTrigger

__all__ = [
    "BaseTrigger",
    "TriggerState",
    "ManualTrigger",
    "ScheduleTrigger",
]
