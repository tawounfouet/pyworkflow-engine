"""
Adapter triggers — implémentations concrètes du port BaseTrigger.

Chaque trigger implémente le contrat défini dans
``pyworkflow_engine.ports.trigger.BaseTrigger``.

Triggers disponibles (stdlib uniquement) :
    - :class:`ManualTrigger`   — déclenchement explicite par le code
    - :class:`ScheduleTrigger` — déclenchement planifié par expression cron
"""

from __future__ import annotations

from pyworkflow_engine.adapters.triggers.manual import ManualTrigger
from pyworkflow_engine.adapters.triggers.schedule import CronExpression, ScheduleTrigger

__all__ = [
    "ManualTrigger",
    "ScheduleTrigger",
    "CronExpression",
]
