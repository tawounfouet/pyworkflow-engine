"""Custom Textual messages pour la communication inter-widgets."""

from __future__ import annotations

from textual.message import Message


class RunUpdated(Message):
    """Émis quand un run change de statut (polling ou push)."""

    def __init__(self, run_id: str, new_status: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.new_status = new_status


class StepCompleted(Message):
    """Émis quand un step termine son exécution."""

    def __init__(self, run_id: str, step_name: str, status: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.step_name = step_name
        self.status = status


class RefreshRequested(Message):
    """Émis pour demander un rafraîchissement global des données."""

    pass
