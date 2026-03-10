"""
Résolution de graphe de dépendances — DAGResolver pour workflows.

Le DAGResolver analyse les dépendances entre steps d'un workflow et
fournit l'ordre d'exécution optimal, la détection de cycles, et
la résolution des points d'entrée/sortie.

Utilise des algorithmes stdlib standard — zero dépendance externe.
"""

from __future__ import annotations

from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, deque

from .models import Job, Step
from .exceptions import DAGValidationError


class DAGResolver:
    """Résolveur de graphe de dépendances pour workflows.

    Le DAGResolver analyse un Job et ses Steps pour:
    - Détecter les cycles dans le graphe de dépendances
    - Calculer l'ordre topologique d'exécution
    - Identifier les points d'entrée et de sortie
    - Valider la cohérence du graphe

    Utilise l'algorithme de Kahn pour le tri topologique et DFS
    pour la détection de cycles.

    Attributes:
        job: Job analysé.
        _steps_by_name: Mapping nom -> Step pour accès rapide.
        _dependencies: Graphe des dépendances (nom -> [noms des dépendances]).
        _dependents: Graphe inverse (nom -> [noms des dépendants]).

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
        """Initialise le resolver avec un Job.

        Args:
            job: Job à analyser.

        Raises:
            DAGValidationError: Si le graphe contient des erreurs.
        """
        self.job = job
        self._steps_by_name: Dict[str, Step] = {}
        self._dependencies: Dict[str, List[str]] = {}
        self._dependents: Dict[str, List[str]] = defaultdict(list)

        self._build_graph()
        self._validate_graph()

    def _build_graph(self) -> None:
        """Construit les structures de données du graphe."""
        # Index des steps par nom
        for step in self.job.steps:
            if step.name in self._steps_by_name:
                raise DAGValidationError(
                    f"Duplicate step name: '{step.name}'",
                    details={"job_name": self.job.name, "step_name": step.name},
                )
            self._steps_by_name[step.name] = step
            self._dependencies[step.name] = step.dependencies.copy()

        # Construit le graphe inverse (dependents)
        for step_name, deps in self._dependencies.items():
            for dep in deps:
                self._dependents[dep].append(step_name)

    def _validate_graph(self) -> None:
        """Valide la cohérence du graphe.

        Raises:
            DAGValidationError: Si des erreurs sont détectées.
        """
        # Vérifier que toutes les dépendances existent
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

        # Détecter les cycles
        cycles = self._detect_cycles()
        if cycles:
            raise DAGValidationError(
                f"Circular dependencies detected: {' -> '.join(cycles)}",
                details={"job_name": self.job.name, "cycle": cycles},
            )

    def _detect_cycles(self) -> List[str]:
        """Détecte les cycles dans le graphe avec DFS.

        Returns:
            Liste des noms de steps formant un cycle, ou liste vide.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        colors = {step: WHITE for step in self._steps_by_name}
        path: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            if colors[node] == GRAY:
                # Cycle détecté - retourne le chemin du cycle
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]

            if colors[node] == BLACK:
                return None

            colors[node] = GRAY
            path.append(node)

            for dep in self._dependencies.get(node, []):
                cycle = dfs(dep)
                if cycle:
                    return cycle

            colors[node] = BLACK
            path.pop()
            return None

        # Parcourt tous les noeuds pour détecter les cycles
        for step in self._steps_by_name:
            if colors[step] == WHITE:
                cycle = dfs(step)
                if cycle:
                    return cycle

        return []

    def get_execution_order(self) -> List[str]:
        """Calcule l'ordre d'exécution topologique.

        Utilise l'algorithme de Kahn pour le tri topologique.

        Returns:
            Liste ordonnée des noms de steps à exécuter.

        Raises:
            DAGValidationError: Si le graphe n'est pas un DAG valide.
        """
        # Copie des dépendances pour modification
        in_degree = {step: len(deps) for step, deps in self._dependencies.items()}

        # Queue des steps sans dépendances
        queue = deque([step for step, degree in in_degree.items() if degree == 0])

        result: List[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)

            # Réduit le degré d'entrée des dépendants
            for dependent in self._dependents.get(current, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Vérification finale - tous les steps doivent être traités
        if len(result) != len(self._steps_by_name):
            # Il reste des cycles non détectés (ne devrait pas arriver)
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

    def get_entry_points(self) -> List[str]:
        """Retourne les points d'entrée du graphe.

        Les points d'entrée sont les steps sans dépendances.

        Returns:
            Liste des noms de steps sans dépendances.
        """
        return [step for step, deps in self._dependencies.items() if not deps]

    def get_exit_points(self) -> List[str]:
        """Retourne les points de sortie du graphe.

        Les points de sortie sont les steps dont personne ne dépend.

        Returns:
            Liste des noms de steps qui ne sont dépendances d'aucun autre.
        """
        return [step for step in self._steps_by_name if not self._dependents.get(step)]

    def get_dependencies(self, step_name: str) -> List[str]:
        """Retourne les dépendances directes d'un step.

        Args:
            step_name: Nom du step.

        Returns:
            Liste des noms des steps dont dépend le step donné.

        Raises:
            DAGValidationError: Si le step n'existe pas.
        """
        if step_name not in self._steps_by_name:
            raise DAGValidationError(
                f"Unknown step: '{step_name}'",
                details={
                    "job_name": self.job.name,
                    "available_steps": list(self._steps_by_name.keys()),
                },
            )

        return self._dependencies[step_name].copy()

    def get_dependents(self, step_name: str) -> List[str]:
        """Retourne les steps qui dépendent d'un step donné.

        Args:
            step_name: Nom du step.

        Returns:
            Liste des noms des steps qui dépendent du step donné.

        Raises:
            DAGValidationError: Si le step n'existe pas.
        """
        if step_name not in self._steps_by_name:
            raise DAGValidationError(
                f"Unknown step: '{step_name}'",
                details={
                    "job_name": self.job.name,
                    "available_steps": list(self._steps_by_name.keys()),
                },
            )

        return self._dependents.get(step_name, []).copy()

    def can_execute(self, step_name: str, completed_steps: Set[str]) -> bool:
        """Vérifie si un step peut être exécuté.

        Un step peut être exécuté si toutes ses dépendances sont complétées.

        Args:
            step_name: Nom du step à vérifier.
            completed_steps: Ensemble des steps déjà complétés.

        Returns:
            True si le step peut être exécuté.

        Raises:
            DAGValidationError: Si le step n'existe pas.
        """
        dependencies = self.get_dependencies(step_name)
        return all(dep in completed_steps for dep in dependencies)

    def get_ready_steps(self, completed_steps: Set[str]) -> List[str]:
        """Retourne les steps prêts à être exécutés.

        Args:
            completed_steps: Ensemble des steps déjà complétés.

        Returns:
            Liste des steps dont toutes les dépendances sont satisfaites.
        """
        ready = []
        for step_name in self._steps_by_name:
            if step_name not in completed_steps and self.can_execute(
                step_name, completed_steps
            ):
                ready.append(step_name)

        return ready

    def get_parallel_groups(self) -> List[List[str]]:
        """Retourne les groupes de steps pouvant s'exécuter en parallèle.

        Analyse le graphe pour identifier les steps qui peuvent s'exécuter
        simultanément à chaque niveau.

        Returns:
            Liste de listes, chaque sous-liste contient les steps
            pouvant s'exécuter en parallèle à ce niveau.
        """
        groups: List[List[str]] = []
        completed: Set[str] = set()
        remaining = set(self._steps_by_name.keys())

        while remaining:
            # Trouve tous les steps prêts à ce niveau
            ready = [step for step in remaining if self.can_execute(step, completed)]

            if not ready:
                # Ne devrait pas arriver si le graphe est valide
                raise DAGValidationError(
                    f"No ready steps found but {len(remaining)} remain",
                    details={
                        "job_name": self.job.name,
                        "remaining_steps": list(remaining),
                        "completed_steps": list(completed),
                    },
                )

            groups.append(ready)
            completed.update(ready)
            remaining -= set(ready)

        return groups

    def get_critical_path(self) -> Tuple[List[str], int]:
        """Calcule le chemin critique du workflow.

        Le chemin critique est la séquence de steps qui détermine
        la durée minimale d'exécution du workflow.

        Note: Cette implémentation simple compte le nombre de steps.
        Une version plus avancée pourrait utiliser les durées estimées.

        Returns:
            Tuple (chemin, longueur) où chemin est la liste des steps
            du chemin critique et longueur sa taille.
        """
        # Calcul des distances les plus longues (chemin critique)
        distances: Dict[str, int] = {}
        paths: Dict[str, List[str]] = {}

        # Tri topologique pour traiter les noeuds dans l'ordre
        order = self.get_execution_order()

        # Initialise les distances
        for step in order:
            distances[step] = 0
            paths[step] = [step]

        # Calcul du chemin le plus long
        for step in order:
            for dependent in self._dependents.get(step, []):
                new_distance = distances[step] + 1
                if new_distance > distances[dependent]:
                    distances[dependent] = new_distance
                    paths[dependent] = paths[step] + [dependent]

        # Trouve le chemin le plus long
        max_step = max(distances.items(), key=lambda x: x[1])
        critical_path = paths[max_step[0]]
        critical_length = max_step[1]

        return critical_path, critical_length

    def get_graph_stats(self) -> Dict[str, int]:
        """Retourne des statistiques sur le graphe.

        Returns:
            Dictionnaire avec les statistiques du graphe.
        """
        parallel_groups = self.get_parallel_groups()
        max_parallel = (
            max(len(group) for group in parallel_groups) if parallel_groups else 0
        )

        critical_path_length = 0
        if self._steps_by_name:
            critical_path_length = self.get_critical_path()[1]

        return {
            "total_steps": len(self._steps_by_name),
            "entry_points": len(self.get_entry_points()),
            "exit_points": len(self.get_exit_points()),
            "max_parallel": max_parallel,
            "critical_path_length": critical_path_length,
            "total_dependencies": sum(
                len(deps) for deps in self._dependencies.values()
            ),
        }
