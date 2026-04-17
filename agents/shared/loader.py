"""
agents.shared.loader — Chargement dynamique des agents depuis le manifest.

Charge ``agents/manifest.yaml`` et résout les instances ``Agent``
par import dynamique (même pattern que ``pyworkflow_engine.adapters.cli.loader``).

Architecture : ADR-019 (Phase 3)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import yaml

from pyworkflow_engine.models.ai.agent import Agent

# Racine du projet : deux niveaux au-dessus de agents/shared/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Chemin par défaut du manifest (agents/manifest.yaml)
_DEFAULT_MANIFEST = _PROJECT_ROOT / "agents" / "manifest.yaml"


def _ensure_project_root_in_path() -> None:
    """Ajoute la racine du projet à sys.path si elle n'y est pas déjà.

    Nécessaire quand la CLI est lancée via le point d'entrée installé
    (``pyworkflow``) plutôt que depuis le répertoire du projet, car le
    catalogue ``agents/`` n'est pas un package installé.
    """
    root_str = str(_PROJECT_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


class AgentLoadError(Exception):
    """Erreur lors du chargement d'un agent depuis le manifest."""


def load_manifest(manifest_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Lit et parse le fichier ``manifest.yaml``.

    Args:
        manifest_path: Chemin vers le manifest. Si ``None``, utilise
            ``agents/manifest.yaml`` à la racine du projet.

    Returns:
        Liste des entrées du manifest (dicts bruts).

    Raises:
        FileNotFoundError: Manifest introuvable.
        AgentLoadError: YAML invalide ou structure inattendue.
    """
    path = Path(manifest_path) if manifest_path else _DEFAULT_MANIFEST

    if not path.exists():
        raise FileNotFoundError(f"Manifest introuvable : {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AgentLoadError(f"YAML invalide dans {path} : {exc}") from exc

    if not isinstance(raw, dict) or "agents" not in raw:
        raise AgentLoadError(
            f"Structure inattendue dans {path} : clé 'agents' manquante."
        )

    entries: list[dict[str, Any]] = raw["agents"]
    if not isinstance(entries, list):
        raise AgentLoadError(
            f"Structure inattendue dans {path} : 'agents' doit être une liste."
        )

    return entries


def load_agent(entry: dict[str, Any]) -> Agent:
    """Résout une entrée du manifest en instance ``Agent``.

    Args:
        entry: Dict avec au minimum ``module`` et ``attr``.

    Returns:
        Instance ``Agent`` importée dynamiquement.

    Raises:
        AgentLoadError: Module introuvable, attribut absent, ou type incorrect.
    """
    _ensure_project_root_in_path()

    module_path = entry.get("module")
    attr_name = entry.get("attr")

    if not module_path or not attr_name:
        raise AgentLoadError(
            f"Entrée manifest incomplète — 'module' et 'attr' requis : {entry}"
        )

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        raise AgentLoadError(f"Module introuvable : {module_path!r}") from exc

    agent = getattr(module, attr_name, None)
    if agent is None:
        raise AgentLoadError(f"Attribut {attr_name!r} introuvable dans {module_path!r}")

    if not isinstance(agent, Agent):
        raise AgentLoadError(
            f"{module_path}:{attr_name} n'est pas un Agent "
            f"(type: {type(agent).__name__})"
        )

    return agent


def load_all_agents(
    manifest_path: Path | str | None = None,
) -> list[Agent]:
    """Charge tous les agents déclarés dans le manifest.

    Args:
        manifest_path: Chemin vers le manifest (optionnel).

    Returns:
        Liste d'instances ``Agent``, dans l'ordre du manifest.

    Raises:
        FileNotFoundError: Manifest introuvable.
        AgentLoadError: Erreur de chargement sur au moins un agent.
    """
    entries = load_manifest(manifest_path)
    return [load_agent(entry) for entry in entries]


def load_agent_by_slug(
    slug: str,
    manifest_path: Path | str | None = None,
) -> Agent:
    """Charge un agent spécifique par son slug.

    Args:
        slug: Slug de l'agent (ex: ``"general-assistant"``).
        manifest_path: Chemin vers le manifest (optionnel).

    Returns:
        Instance ``Agent``.

    Raises:
        AgentLoadError: Agent introuvable dans le manifest.
    """
    entries = load_manifest(manifest_path)

    for entry in entries:
        if entry.get("name") == slug:
            return load_agent(entry)

    available = [e.get("name", "?") for e in entries]
    raise AgentLoadError(
        f"Agent '{slug}' introuvable dans le manifest. "
        f"Agents disponibles : {', '.join(available)}"
    )
