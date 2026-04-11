"""JobTable widget — DataTable listant les jobs enregistrés."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import DataTable

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job


class JobTable(DataTable):
    """Table interactive des jobs avec navigation clavier.

    L'appui sur ``Enter`` émet un événement ``RowSelected`` capté
    par le screen parent pour naviguer vers le JobDetailScreen.
    """

    def on_mount(self) -> None:
        self.add_columns("Nom", "Steps", "Version", "Executor", "Description")
        self.cursor_type = "row"

    def load_jobs(self, jobs: list[Job]) -> None:
        self.clear()
        for job in jobs:
            self.add_row(
                job.name,
                str(len(job.steps)),
                job.version if hasattr(job, "version") and job.version else "—",
                job.default_executor.value if job.default_executor else "local",
                job.description or "—",
                key=job.name,
            )
