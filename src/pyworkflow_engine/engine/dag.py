"""
DAGResolver — résolution du graphe de dépendances pour workflows.

Analyse les dépendances entre steps, fournit l'ordre d'exécution optimal,
la détection de cycles, et la résolution des points d'entrée/sortie.

Utilise des algorithmes stdlib standard — zero dépendance externe.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyworkflow_engine.models import Job, Step

from pyworkflow_engine.exceptions import DAGValidationError


class DAGResolver:
    """Résolveur de graphe de dépendances pour workflows.

    Le DAGResolver analyse un Job et ses Steps pour:
    - Détecter les cycles dans le graphe de dépendances
    - Calculer l'ordre topologique d'exécution
    - Identifier les points d'entrée et de sortie
    - Valider la cohérence du graphe

    Utilise l'algorithme de Kahn pour le tri topologique et DFS
    pour la détection de cycles.

    Examples:
        >>> job = Job(name="Pipeline", steps=[
        ...     Step(name="extract", ...),
        ...     Step(name="transform", dependencies=["extract"]),
        ...     Step(name="load", dependencies=["transform"])
        ... ])
        >>> resolver = DAGResolver(job)
        >>> order = resolver.get_execution_order()
        >>> print(order)  # ["extract", "transform", "load"]
    """

    def __init__(self, job: Job):
        self.job = job
        self._steps_by_name: dict[str, Step] = {}
        self._dependencies: dict[str, list[str]] = {}
        self._dependents: dict[str, list[str]] = defaultdict(list)
        self._build_graph()
        self._validate_graph()

    def _build_graph(self) -> None:
        for step in self.job.steps:
            if step.name in self._steps_by_name:
                raise DAGValidationError(
                    f"Duplicate step name: '{step.name}'",
                    details={"job_name": self.job.name, "step_name": step.name},
                )
            self._steps_by_name[step.name] = step
            self._dependencies[step.name] = step.dependencies.copy()

        for step_name, deps in self._dependencies.items():
            for dep in deps:
                self._dependents[dep].append(step_name)

    def _validate_graph(self) -> None:
        for step_name, deps in self._dependencies.items():
            for dep in deps:
                if dep not in self._steps_by_name:
                    raise DAGValidationError(
                        f"Step '{step_name}' depends on unknown step '{dep}'",
                        details={
                            "job_name": self.job.name,
                            "step_name": step_name,
                            "missing_dependency": dep,
                            "available_steps": list(self._steps_by_name.keys()),
                        },
                    )
        cycles = self._detect_cycles()
        if cycles:
            raise DAGValidationError(
                f"Circular dependencies detected: {' -> '.join(cycles)}",
                details={"job_name": self.job.name, "cycle": cycles},
            )

    def _detect_cycles(self) -> list[str]:
        """Détecte les cycles via DFS itérative (pas de risque de RecursionError).

        Algorithme : coloration 3-états (WHITE/GRAY/BLACK) sur une pile
        explicite.  GRAY = nœud en cours de traitement sur le chemin courant ;
        BLACK = nœud entièrement traité.  Un arc vers un nœud GRAY indique un
        cycle.

        Returns:
            Liste de noms de steps formant le premier cycle trouvé,
            ou liste vide s'il n'y en a pas.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        colors: dict[str, int] = dict.fromkeys(self._steps_by_name, WHITE)
        # parent[node] permet de reconstruire le chemin du cycle
        parent: dict[str, str | None] = {n: None for n in self._steps_by_name}

        for start in self._steps_by_name:
            if colors[start] != WHITE:
                continue

            # Pile d'items (node, iterator_over_deps, entering)
            # entering=True  → première visite du nœud (marquer GRAY)
            # entering=False → retour de tous les enfants (marquer BLACK)
            stack: list[tuple[str, bool]] = [(start, True)]

            while stack:
                node, entering = stack.pop()

                if entering:
                    if colors[node] == GRAY:
                        # Cycle détecté — reconstruire le chemin
                        cycle: list[str] = [node]
                        cur: str | None = parent[node]
                        while cur is not None and cur != node:
                            cycle.append(cur)
                            cur = parent[cur]
                        cycle.append(node)
                        cycle.reverse()
                        return cycle

                    if colors[node] == BLACK:
                        continue

                    colors[node] = GRAY
                    # Planifier le marquage BLACK au retour
                    stack.append((node, False))

                    for dep in self._dependencies.get(node, []):
                        if colors[dep] != BLACK:
                            parent[dep] = node
                            stack.append((dep, True))
                else:
                    colors[node] = BLACK

        return []

    def get_execution_order(self) -> list[str]:
        in_degree = {step: len(deps) for step, deps in self._dependencies.items()}
        queue = deque([step for step, degree in in_degree.items() if degree == 0])
        result: list[str] = []
        while queue:
            current = queue.popleft()
            result.append(current)
            for dependent in self._dependents.get(current, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        if len(result) != len(self._steps_by_name):
            remaining = set(self._steps_by_name) - set(result)
            raise DAGValidationError(
                f"Unable to resolve execution order. Remaining steps: {remaining}",
                details={
                    "job_name": self.job.name,
                    "processed_steps": result,
                    "remaining_steps": list(remaining),
                },
            )
        return result

    def get_entry_points(self) -> list[str]:
        return [step for step, deps in self._dependencies.items() if not deps]

    def get_exit_points(self) -> list[str]:
        return [step for step in self._steps_by_name if not self._dependents.get(step)]

    def get_dependencies(self, step_name: str) -> list[str]:
        if step_name not in self._steps_by_name:
            raise DAGValidationError(
                f"Unknown step: '{step_name}'",
                details={
                    "job_name": self.job.name,
                    "available_steps": list(self._steps_by_name.keys()),
                },
            )
        return self._dependencies[step_name].copy()

    def get_dependents(self, step_name: str) -> list[str]:
        if step_name not in self._steps_by_name:
            raise DAGValidationError(
                f"Unknown step: '{step_name}'",
                details={
                    "job_name": self.job.name,
                    "available_steps": list(self._steps_by_name.keys()),
                },
            )
        return self._dependents.get(step_name, []).copy()

    def can_execute(self, step_name: str, completed_steps: set[str]) -> bool:
        return all(dep in completed_steps for dep in self.get_dependencies(step_name))

    def get_ready_steps(self, completed_steps: set[str]) -> list[str]:
        return [
            s
            for s in self._steps_by_name
            if s not in completed_steps and self.can_execute(s, completed_steps)
        ]

    def get_parallel_groups(self) -> list[list[str]]:
        groups: list[list[str]] = []
        completed: set[str] = set()
        remaining = set(self._steps_by_name.keys())
        while remaining:
            ready = [step for step in remaining if self.can_execute(step, completed)]
            if not ready:
                raise DAGValidationError(
                    f"No ready steps found but {len(remaining)} remain",
                    details={
                        "job_name": self.job.name,
                        "remaining_steps": list(remaining),
                    },
                )
            groups.append(ready)
            completed.update(ready)
            remaining -= set(ready)
        return groups

    def get_critical_path(self) -> tuple[list[str], int]:
        distances: dict[str, int] = {}
        paths: dict[str, list[str]] = {}
        order = self.get_execution_order()
        for step in order:
            distances[step] = 0
            paths[step] = [step]
        for step in order:
            for dependent in self._dependents.get(step, []):
                new_distance = distances[step] + 1
                if new_distance > distances[dependent]:
                    distances[dependent] = new_distance
                    paths[dependent] = paths[step] + [dependent]
        max_step = max(distances.items(), key=lambda x: x[1])
        return paths[max_step[0]], max_step[1]

    def get_graph_stats(self) -> dict[str, int]:
        parallel_groups = self.get_parallel_groups()
        max_parallel = max(len(g) for g in parallel_groups) if parallel_groups else 0
        critical_path_length = self.get_critical_path()[1] if self._steps_by_name else 0
        return {
            "total_steps": len(self._steps_by_name),
            "entry_points": len(self.get_entry_points()),
            "exit_points": len(self.get_exit_points()),
            "max_parallel": max_parallel,
            "critical_path_length": critical_path_length,
            "total_dependencies": sum(len(d) for d in self._dependencies.values()),
        }
