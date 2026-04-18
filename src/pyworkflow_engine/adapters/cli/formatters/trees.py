"""
Rich Tree formatter — visualisation DAG d'un Job en terminal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.tree import Tree

if TYPE_CHECKING:
    from pyworkflow_engine.models.workflow.job import Job


def render_job_tree(console: Console, job: Job) -> None:
    """Affiche la structure d'un Job comme un Rich Tree.

    Exemple de sortie::

        🔧 etl-pipeline
        ├── 📌 Metadata
        │   ├── Description : Extract, transform, load
        │   ├── Version     : 1.0.0
        │   ├── Executor    : local
        │   └── Steps       : 3
        └── 📦 Steps (3)
            ├── ▸ extract
            ├── ▸ transform  ← [extract]
            └── ▸ load       ← [transform]
    """
    root = Tree(f"🔧 [bold cyan]{job.name}[/bold cyan]")

    # — Metadata -------------------------------------------------------
    meta = root.add("📌 [bold]Metadata[/bold]")
    if job.description:
        meta.add(f"Description : {job.description}")
    meta.add(f"Version     : {job.version or '—'}")
    meta.add(
        f"Executor    : {job.default_executor.value if job.default_executor else 'local'}"
    )
    if job.tags:
        meta.add(f"Tags        : {', '.join(job.tags)}")
    if job.timeout:
        meta.add(f"Timeout     : {job.timeout}")
    meta.add(f"Steps       : {len(job.steps)}")

    # — Steps DAG -------------------------------------------------------
    steps_node = root.add(f"📦 [bold]Steps[/bold] ({len(job.steps)})")
    for step in job.steps:
        # Dépendances
        if step.dependencies:
            deps = "[dim]← [" + ", ".join(step.dependencies) + "][/dim]"
        else:
            deps = ""

        # Icône selon la configuration
        if step.retry_count and step.retry_count > 0:
            icon = "🔄"
        elif getattr(step, "step_type", None) and str(
            getattr(step, "step_type", "")
        ).endswith("HUMAN_TASK"):
            icon = "👤"
        else:
            icon = "▸"

        parts = [f"{icon} [cyan]{step.name}[/cyan]"]
        if deps:
            parts.append(f"  {deps}")
        if step.timeout:
            parts.append(f"  [dim](timeout: {step.timeout}s)[/dim]")

        steps_node.add("".join(parts))

    console.print(root)
    console.print()
