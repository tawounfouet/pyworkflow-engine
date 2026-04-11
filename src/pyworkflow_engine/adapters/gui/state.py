"""GUIState — état partagé côté serveur pour le GUI NiceGUI.

NiceGUI gère son propre état de session via ``app.storage.user``.
Ce module fournit un conteneur léger pour l'état *serveur* global
(configuration, référence moteur) accessible depuis toutes les pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


@dataclass
class GUIState:
    """État global du serveur GUI.

    Attributes:
        engine: Instance du moteur de workflow.
        config: Configuration NiceGUI chargée au démarrage.
        selected_job: Nom du job actuellement sélectionné (navigation).
        selected_run_id: ID du run actuellement sélectionné.
        notifications: File de messages à afficher (usage interne).
    """

    engine: WorkflowEngine = field(default=None)  # type: ignore[assignment]
    config: GUIConfig = field(default=None)  # type: ignore[assignment]
    selected_job: str | None = None
    selected_run_id: str | None = None
    notifications: list[str] = field(default_factory=list)

    # ── Helpers ──────────────────────────────────────────────────────────

    def select_job(self, job_name: str) -> None:
        """Mémorise le job sélectionné."""
        self.selected_job = job_name

    def select_run(self, run_id: str) -> None:
        """Mémorise le run sélectionné."""
        self.selected_run_id = run_id

    def push_notification(self, message: str) -> None:
        """Enfile un message de notification."""
        self.notifications.append(message)

    def pop_notifications(self) -> list[str]:
        """Vide et retourne la file de notifications."""
        msgs = list(self.notifications)
        self.notifications.clear()
        return msgs
