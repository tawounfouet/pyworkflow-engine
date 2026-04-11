"""dag_graph — rendu Mermaid du DAG d'un job."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

if TYPE_CHECKING:
    from pyworkflow_engine.models.design_time import Job


def dag_graph(job: Job) -> ui.mermaid:
    """Affiche le DAG d'un job sous forme de diagramme Mermaid.

    Met en évidence le chemin critique (si calculable) en orange,
    et connecte explicitement les points d'entrée/sortie.

    Args:
        job: Instance ``Job`` dont on veut afficher le DAG.

    Returns:
        L'instance ``ui.mermaid`` créée.
    """
    diagram = _build_diagram(job)
    return ui.mermaid(diagram).classes("w-full overflow-auto")


def _build_diagram(job: Job) -> str:
    lines = ["graph LR"]

    for step in job.steps:
        if not step.dependencies:
            lines.append(f"    START(( )) --> {_mid(step.name)}[{step.name}]")
        for dep in step.dependencies:
            lines.append(f"    {_mid(dep)}[{dep}] --> {_mid(step.name)}[{step.name}]")

    # Exit points + critical path via DAGResolver
    try:
        from pyworkflow_engine.engine.dag import DAGResolver

        resolver = DAGResolver(job)
        for ep in resolver.get_exit_points():
            lines.append(f"    {_mid(ep)}[{ep}] --> END(( ))")
        critical, _ = resolver.get_critical_path()
        for step_name in critical:
            lines.append(
                f"    style {_mid(step_name)} fill:#f90,color:#000,stroke:#c60"
            )
    except Exception:
        pass

    return "\n".join(lines)


def _mid(name: str) -> str:
    """Sanitise un nom de step pour Mermaid."""
    return name.replace("-", "_").replace(" ", "_").replace(".", "_")
