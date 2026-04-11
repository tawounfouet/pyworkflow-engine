"""log_viewer — panneau de logs avec rendu coloré et auto-scroll."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

if TYPE_CHECKING:
    from pyworkflow_engine.models.runtime import StepRun

# Mapping niveau de log → couleur Tailwind/Quasar
_LEVEL_COLOR = {
    "ERROR": "text-negative",
    "WARNING": "text-warning",
    "INFO": "text-positive",
    "DEBUG": "text-grey-5",
}


def log_viewer(step_runs: list[StepRun]) -> ui.log:
    """Crée un panneau de logs scrollable pour un run.

    Affiche tous les logs de tous les steps dans l'ordre chronologique,
    chaque ligne préfixée de l'horodatage, du nom du step et du niveau.

    Args:
        step_runs: Liste de ``StepRun`` dont on veut afficher les logs.

    Returns:
        L'instance ``ui.log`` créée.
    """
    log = (
        ui.log(max_lines=500)
        .classes("w-full font-mono text-xs bg-grey-10 text-grey-2 rounded")
        .style("height: 320px")
    )

    _populate_log(log, step_runs)
    return log


def refresh_log_viewer(log: ui.log, step_runs: list[StepRun]) -> None:
    """Vide et re-remplit un log_viewer existant."""
    log.clear()
    _populate_log(log, step_runs)


def _populate_log(log: ui.log, step_runs: list[StepRun]) -> None:
    """Remplit le log avec les entrées de tous les step_runs."""
    all_entries = []
    for sr in step_runs:
        for entry in sr.logs:
            all_entries.append(
                (entry.timestamp, sr.step_name, entry.level, entry.message)
            )

    # Tri chronologique
    all_entries.sort(key=lambda x: x[0])

    for ts, step_name, level, message in all_entries:
        ts_str = ts.strftime("%H:%M:%S") if ts else "??:??:??"
        line = f"[{ts_str}] [{step_name}] [{level}] {message}"
        log.push(line)
