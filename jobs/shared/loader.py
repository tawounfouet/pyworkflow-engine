"""
jobs.shared.loader — Chargement dynamique des jobs depuis le manifest.

Charge ``jobs/manifest.yaml`` et résout les instances ``Job``
par import dynamique (même pattern que ``agents.shared.loader``).

Deux conventions pour l'attribut exporté :
  - **API impérative** : le module exporte ``job = Job(...)``
    → attribut par défaut ``"job"``
  - **API décorateurs** : le module exporte ``@job(...) def ingest_xxx()``
    → attribut = nom de la fonction (``JobBuilder``), converti via ``.build()``

Architecture : ADR-018 — Phase catalogue jobs
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import yaml

from pyworkflow_engine.decorators.job_decorator import JobBuilder
from pyworkflow_engine.models.workflow.job import Job

# Racine du projet : deux niveaux au-dessus de jobs/shared/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Chemin par défaut du manifest (jobs/manifest.yaml)
_DEFAULT_MANIFEST = _PROJECT_ROOT / "jobs" / "manifest.yaml"


def _ensure_project_root_in_path() -> None:
    """Ajoute la racine du projet à sys.path si elle n'y est pas déjà."""
    root_str = str(_PROJECT_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


class JobLoadError(Exception):
    """Erreur lors du chargement d'un job depuis le manifest."""


# ── Manifest ──────────────────────────────────────────────────────────────────


def load_manifest(
    manifest_path: Path | str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Lit et parse le fichier ``manifest.yaml``.

    Args:
        manifest_path: Chemin vers le manifest. Si ``None``, utilise
            ``jobs/manifest.yaml`` à la racine du projet.

    Returns:
        Dictionnaire brut du manifest (clés ``jobs`` et ``pipelines``).

    Raises:
        FileNotFoundError: Manifest introuvable.
        JobLoadError: YAML invalide ou structure inattendue.
    """
    path = Path(manifest_path) if manifest_path else _DEFAULT_MANIFEST

    if not path.exists():
        raise FileNotFoundError(f"Manifest introuvable : {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise JobLoadError(f"YAML invalide dans {path} : {exc}") from exc

    if not isinstance(raw, dict) or "jobs" not in raw:
        raise JobLoadError(f"Structure inattendue dans {path} : clé 'jobs' manquante.")

    return raw


def load_manifest_entries(
    manifest_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retourne uniquement les entrées de la section ``jobs``."""
    raw = load_manifest(manifest_path)
    entries: list[dict[str, Any]] = raw["jobs"]
    if not isinstance(entries, list):
        raise JobLoadError("La clé 'jobs' doit être une liste.")
    return entries


# ── Chargement d'un job individuel ────────────────────────────────────────────


def load_job(entry: dict[str, Any]) -> Job:
    """Résout une entrée du manifest en instance ``Job``.

    Stratégie de résolution :
      1. Si ``attr`` est spécifié dans l'entrée, on l'utilise.
      2. Sinon, on cherche l'attribut ``"job"`` (convention API impérative).
      3. Si l'attribut trouvé est un ``JobBuilder`` (API décorateurs),
         on appelle ``.build()`` pour obtenir l'objet ``Job``.

    Args:
        entry: Dict avec au minimum ``module`` et ``name``.

    Returns:
        Instance ``Job`` importée dynamiquement.

    Raises:
        JobLoadError: Module introuvable, attribut absent, ou type incorrect.
    """
    _ensure_project_root_in_path()

    module_path = entry.get("module")
    attr_name = entry.get("attr", "job")

    if not module_path:
        raise JobLoadError(f"Entrée manifest incomplète — 'module' requis : {entry}")

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        raise JobLoadError(f"Module introuvable : {module_path!r}") from exc

    obj = getattr(module, attr_name, None)

    # Fallback : chercher un attribut de type Job ou JobBuilder dans le module
    if obj is None:
        for name in dir(module):
            candidate = getattr(module, name, None)
            if isinstance(candidate, (Job, JobBuilder)):
                obj = candidate
                break

    if obj is None:
        raise JobLoadError(
            f"Aucun attribut Job/JobBuilder trouvé dans {module_path!r} "
            f"(cherché : {attr_name!r})"
        )

    # Conversion JobBuilder → Job
    if isinstance(obj, JobBuilder):
        return obj.build()

    if isinstance(obj, Job):
        return obj

    raise JobLoadError(
        f"{module_path}:{attr_name} n'est ni un Job ni un JobBuilder "
        f"(type: {type(obj).__name__})"
    )


# ── Chargement groupé ────────────────────────────────────────────────────────


def load_all_jobs(
    manifest_path: Path | str | None = None,
) -> list[Job]:
    """Charge tous les jobs déclarés dans le manifest.

    Args:
        manifest_path: Chemin vers le manifest (optionnel).

    Returns:
        Liste d'instances ``Job``, dans l'ordre du manifest.

    Raises:
        FileNotFoundError: Manifest introuvable.
        JobLoadError: Erreur de chargement sur au moins un job.
    """
    entries = load_manifest_entries(manifest_path)
    return [load_job(entry) for entry in entries]


def load_all_jobs_with_metadata(
    manifest_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Charge tous les jobs et enrichit avec les métadonnées du manifest.

    Retourne une liste de dicts contenant :
      - ``job``: Instance ``Job``
      - ``schedule``: Expression cron du manifest
      - ``owner``: Propriétaire déclaré
      - ``tags``: Tags du manifest
      - ``depends_on``: Dépendances inter-jobs
      - ``description``: Description du manifest

    Args:
        manifest_path: Chemin vers le manifest (optionnel).

    Returns:
        Liste de dicts enrichis.
    """
    entries = load_manifest_entries(manifest_path)
    results: list[dict[str, Any]] = []

    for entry in entries:
        job_instance = load_job(entry)
        results.append(
            {
                "job": job_instance,
                "schedule": entry.get("schedule"),
                "owner": entry.get("owner"),
                "tags": entry.get("tags", []),
                "depends_on": entry.get("depends_on", []),
                "description": entry.get("description", ""),
            }
        )

    return results


def load_job_by_name(
    name: str,
    manifest_path: Path | str | None = None,
) -> Job:
    """Charge un job spécifique par son nom dans le manifest.

    Args:
        name: Nom du job (ex: ``"ingestion-stripe-payments"``).
        manifest_path: Chemin vers le manifest (optionnel).

    Returns:
        Instance ``Job``.

    Raises:
        JobLoadError: Job introuvable dans le manifest.
    """
    entries = load_manifest_entries(manifest_path)

    for entry in entries:
        if entry.get("name") == name:
            return load_job(entry)

    available = [e.get("name", "?") for e in entries]
    raise JobLoadError(
        f"Job '{name}' introuvable dans le manifest. "
        f"Jobs disponibles : {', '.join(available)}"
    )
