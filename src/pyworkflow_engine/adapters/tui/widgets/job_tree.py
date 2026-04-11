"""JobTree widget — Tree widget pour visualiser le DAG d'un job."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Tree

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job


class JobTree(Tree[str]):
    """Arbre interactif représentant le DAG d'un job.

    Chaque step est un nœud. Les dépendances sont représentées
    comme des sous-nœuds (expand/collapse natif Textual).
    """

    def load_job(self, job: Job) -> None:
        self.clear()
        self.root.set_label(f"📋 {job.name}")
        for step in job.steps:
            node = self.root.add(f"⚙️  {step.name}", expand=True)
            if step.dependencies:
                deps_node = node.add("⤷ dépendances", expand=False)
                for dep in step.dependencies:
                    deps_node.add_leaf(f"← {dep}")
            if step.step_type:
                node.add_leaf(f"type: {step.step_type.value}")
        self.root.expand()
