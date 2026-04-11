"""StatusBar widget — footer avec stats globales."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Barre de statut affichant les compteurs globaux."""

    def update_stats(
        self,
        total_jobs: int,
        total_runs: int,
        suspended: int,
    ) -> None:
        self.update(
            f"  📋 {total_jobs} jobs  │  "
            f"📊 {total_runs} runs  │  "
            f"⏸ {suspended} suspendus  │  "
            f"[dim]? aide  q quitter[/dim]"
        )
