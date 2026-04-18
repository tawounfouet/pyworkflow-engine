"""dag_graph — rendu Mermaid du DAG d'un job ou d'une pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

if TYPE_CHECKING:
    from pyworkflow_engine.models.design_time import Job
    from pyworkflow_engine.models.pipeline.pipeline import Pipeline


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


# ── Pipeline-level DAG ────────────────────────────────────────────────────────


def pipeline_dag_graph(pipeline: Pipeline) -> ui.mermaid:
    """Affiche le DAG de séquencement des stages d'une pipeline.

    Représente la chaîne linéaire des stages avec leurs noms de jobs,
    en mettant en évidence les stages désactivés en gris.

    Args:
        pipeline: Instance ``Pipeline`` dont on veut afficher le DAG.

    Returns:
        L'instance ``ui.mermaid`` créée.
    """
    diagram = _build_pipeline_diagram(pipeline)
    return ui.mermaid(diagram).classes("w-full overflow-auto")


def _build_pipeline_diagram(pipeline: Pipeline) -> str:
    lines = ["graph LR"]
    stages = pipeline.stages

    if not stages:
        lines.append("    EMPTY[Aucun stage défini]")
        return "\n".join(lines)

    lines.append("    START(( ))")

    for i, stage in enumerate(stages):
        node_id = f"S{i}_{_mid(stage.job_name)}"
        label = stage.job_name
        if not stage.enabled:
            lines.append(f"    {node_id}[{label}]:::disabled")
        else:
            lines.append(f"    {node_id}[{label}]")

        if i == 0:
            lines.append(f"    START --> {node_id}")
        else:
            prev_id = f"S{i - 1}_{_mid(stages[i - 1].job_name)}"
            lines.append(f"    {prev_id} --> {node_id}")

        if i == len(stages) - 1:
            lines.append(f"    {node_id} --> END(( ))")

    lines.append("    classDef disabled fill:#ccc,color:#666,stroke:#aaa")
    return "\n".join(lines)
