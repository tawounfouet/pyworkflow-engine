"""
adapters/ai/skills/registry — Registre central des Skills IA.

Centralise l'enregistrement et la résolution des skills disponibles.
"""

from __future__ import annotations

import logging
from typing import Any

from pyworkflow_engine.exceptions import SkillNotFoundError
from pyworkflow_engine.ports.ai.skill import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registre de Skills : enregistrement, résolution et introspection."""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    # ── Enregistrement ─────────────────────────────────────────────────

    def register(self, skill: BaseSkill) -> None:
        """Enregistre un skill dans le registre.

        Raises:
            ValueError: Si la clé du skill est vide.
        """
        if not skill.key:
            raise ValueError(f"Skill '{skill.__class__.__name__}' has an empty key.")
        self._skills[skill.key] = skill
        logger.debug("Registered skill: '%s' (%s)", skill.key, skill.__class__.__name__)

    def register_many(self, skills: list[BaseSkill]) -> None:
        """Enregistre plusieurs skills à la fois."""
        for skill in skills:
            self.register(skill)

    def unregister(self, key: str) -> bool:
        """Retire un skill du registre. Retourne True si trouvé et supprimé."""
        if key in self._skills:
            del self._skills[key]
            logger.debug("Unregistered skill: '%s'", key)
            return True
        return False

    # ── Résolution ─────────────────────────────────────────────────────

    def get(self, key: str) -> BaseSkill:
        """Récupère un skill par sa clé.

        Raises:
            SkillNotFoundError: Si la clé n'est pas enregistrée.
        """
        skill = self._skills.get(key)
        if skill is None:
            raise SkillNotFoundError(f"Skill '{key}' not found in registry.")
        return skill

    def has(self, key: str) -> bool:
        """True si un skill est enregistré sous cette clé."""
        return key in self._skills

    def keys(self) -> list[str]:
        """Liste toutes les clés enregistrées."""
        return list(self._skills.keys())

    def list_skills(self, *, active_only: bool = False) -> list[BaseSkill]:
        """Retourne la liste des skills enregistrés."""
        skills = list(self._skills.values())
        if active_only:
            skills = [s for s in skills if s.is_active]
        return skills

    def get_missing_tools(
        self, key: str, *, available_tool_keys: set[str]
    ) -> list[str]:
        """Retourne les clés de tools requis par un skill qui ne sont pas disponibles.

        Args:
            key: Clé du skill.
            available_tool_keys: Ensemble des clés de tools disponibles.

        Returns:
            Liste des clés manquantes (vide si tout est disponible).
        """
        skill = self.get(key)
        return [k for k in skill.required_tool_keys if k not in available_tool_keys]

    # ── Exécution directe ─────────────────────────────────────────────

    def execute(self, key: str, *, llm_client: Any, **kwargs: Any) -> Any:
        """Exécute un skill enregistré de manière synchrone."""
        skill = self.get(key)
        return skill.run(llm_client=llm_client, **kwargs)

    async def aexecute(self, key: str, *, llm_client: Any, **kwargs: Any) -> Any:
        """Exécute un skill enregistré de manière asynchrone."""
        skill = self.get(key)
        return await skill.arun(llm_client=llm_client, **kwargs)

    # ── Dunder ────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Supprime tous les skills enregistrés."""
        self._skills.clear()

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.has(key)

    def __repr__(self) -> str:
        return f"<SkillRegistry skills={self.keys()!r}>"
