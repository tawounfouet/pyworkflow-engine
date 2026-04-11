"""LogPanel widget — RichLog pour les logs en temps réel."""

from __future__ import annotations

from textual.widgets import RichLog


class LogPanel(RichLog):
    """Panel de logs scrollable avec auto-scroll.

    En Phase 1, les logs sont poussés manuellement par le screen.
    En Phase 2, un EventBus pourra alimenter le panel en push.
    """

    def on_mount(self) -> None:
        self.auto_scroll = True

    def append_log(self, message: str, style: str = "") -> None:
        if style:
            self.write(f"[{style}]{message}[/]")
        else:
            self.write(message)
