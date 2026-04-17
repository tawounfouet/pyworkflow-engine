"""
adapters/ai/skills — Skills concrets + SkillRegistry.
"""

from __future__ import annotations

from pyworkflow_engine.adapters.ai.skills.registry import SkillRegistry
from pyworkflow_engine.ports.ai.skill import BaseSkill

__all__ = [
    "BaseSkill",
    "SkillRegistry",
]
