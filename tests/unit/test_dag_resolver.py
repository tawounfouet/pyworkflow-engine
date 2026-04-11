"""
Tests unitaires pour le DAGResolver — résolution de graphe de dépendances.

Test la logique de résolution des dépendances, détection de cycles,
tri topologique et analyse du graphe de workflow.
"""

import pytest

from pyworkflow_engine.engine.dag import DAGResolver
from pyworkflow_engine.exceptions import DAGValidationError
from pyworkflow_engine.models import Job, Step, StepType


class TestDAGResolver:
    """Tests du DAGResolver."""

    def test_simple_linear_workflow(self):
        """Test avec un workflow linéaire simple."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Linear Workflow",
            steps=[
                Step(name="step1", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(
                    name="step2",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["step1"],
                ),
                Step(
                    name="step3",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["step2"],
                ),
            ],
        )

        resolver = DAGResolver(job)

        # Test ordre d'exécution
        order = resolver.get_execution_order()
        assert order == ["step1", "step2", "step3"]

        # Test points d'entrée et sortie
        assert resolver.get_entry_points() == ["step1"]
        assert resolver.get_exit_points() == ["step3"]

        # Test groupes parallèles
        groups = resolver.get_parallel_groups()
        assert groups == [["step1"], ["step2"], ["step3"]]

    def test_parallel_workflow(self):
        """Test avec un workflow parallèle."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Parallel Workflow",
            steps=[
                Step(name="start", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(
                    name="parallel1",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["start"],
                ),
                Step(
                    name="parallel2",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["start"],
                ),
                Step(
                    name="end",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["parallel1", "parallel2"],
                ),
            ],
        )

        resolver = DAGResolver(job)

        # Test ordre d'exécution (peut varier pour les steps parallèles)
        order = resolver.get_execution_order()
        assert order[0] == "start"
        assert order[3] == "end"
        assert set(order[1:3]) == {"parallel1", "parallel2"}

        # Test groupes parallèles
        groups = resolver.get_parallel_groups()
        assert len(groups) == 3
        assert groups[0] == ["start"]
        assert set(groups[1]) == {"parallel1", "parallel2"}
        assert groups[2] == ["end"]

    def test_diamond_dependency(self):
        """Test avec dépendances en diamant."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Diamond Workflow",
            steps=[
                Step(name="A", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(
                    name="B",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A"],
                ),
                Step(
                    name="C",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A"],
                ),
                Step(
                    name="D",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["B", "C"],
                ),
            ],
        )

        resolver = DAGResolver(job)

        order = resolver.get_execution_order()
        assert order[0] == "A"
        assert order[3] == "D"
        assert set(order[1:3]) == {"B", "C"}

        # Test chemin critique
        critical_path, length = resolver.get_critical_path()
        assert length == 2  # A -> B -> D ou A -> C -> D
        assert critical_path[0] == "A"
        assert critical_path[-1] == "D"

    def test_cycle_detection(self):
        """Test de détection de cycle."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Cyclic Workflow",
            steps=[
                Step(
                    name="A",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["C"],
                ),
                Step(
                    name="B",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A"],
                ),
                Step(
                    name="C",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["B"],
                ),
            ],
        )

        with pytest.raises(DAGValidationError) as exc_info:
            DAGResolver(job)

        assert "Circular dependencies detected" in str(exc_info.value)

    def test_self_dependency(self):
        """Test de détection d'auto-dépendance."""

        def dummy_func():
            return {"result": "ok"}

        with pytest.raises(ValueError) as exc_info:
            Step(
                name="self",
                step_type=StepType.FUNCTION,
                handler=dummy_func,
                dependencies=["self"],
            )

        assert "cannot depend on itself" in str(exc_info.value)

    def test_missing_dependency(self):
        """Test avec dépendance inexistante."""

        def dummy_func():
            return {"result": "ok"}

        # Job model validates dependencies at creation time,
        # so we expect ValueError when creating invalid job
        with pytest.raises(ValueError) as exc_info:
            Job(
                name="Missing Dependency",
                steps=[
                    Step(name="A", step_type=StepType.FUNCTION, handler=dummy_func),
                    Step(
                        name="B",
                        step_type=StepType.FUNCTION,
                        handler=dummy_func,
                        dependencies=["nonexistent"],
                    ),
                ],
            )

        assert "dependency 'nonexistent' not found" in str(exc_info.value)

    def test_duplicate_step_names(self):
        """Test avec noms de steps dupliqués."""

        def dummy_func():
            return {"result": "ok"}

        # Job model validates step name uniqueness at creation time,
        # so we expect ValueError when creating invalid job
        with pytest.raises(ValueError) as exc_info:
            Job(
                name="Duplicate Names",
                steps=[
                    Step(
                        name="duplicate",
                        step_type=StepType.FUNCTION,
                        handler=dummy_func,
                    ),
                    Step(
                        name="duplicate",
                        step_type=StepType.FUNCTION,
                        handler=dummy_func,
                    ),
                ],
            )

        assert "Step names must be unique" in str(exc_info.value)

    def test_complex_workflow(self):
        """Test avec un workflow complexe."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Complex Workflow",
            steps=[
                Step(name="extract1", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(name="extract2", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(
                    name="transform1",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["extract1"],
                ),
                Step(
                    name="transform2",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["extract2"],
                ),
                Step(
                    name="merge",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["transform1", "transform2"],
                ),
                Step(
                    name="validate",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["merge"],
                ),
                Step(
                    name="load",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["validate"],
                ),
            ],
        )

        resolver = DAGResolver(job)

        # Test statistiques
        stats = resolver.get_graph_stats()
        assert stats["total_steps"] == 7
        assert stats["entry_points"] == 2
        assert stats["exit_points"] == 1
        assert stats["max_parallel"] == 2
        assert (
            stats["critical_path_length"] == 4
        )  # extract -> transform -> merge -> validate -> load

    def test_can_execute_logic(self):
        """Test de la logique can_execute."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Can Execute Test",
            steps=[
                Step(name="A", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(
                    name="B",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A"],
                ),
                Step(
                    name="C",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A", "B"],
                ),
            ],
        )

        resolver = DAGResolver(job)

        # État initial
        completed = set()
        assert resolver.can_execute("A", completed) is True
        assert resolver.can_execute("B", completed) is False
        assert resolver.can_execute("C", completed) is False

        # A complété
        completed.add("A")
        assert resolver.can_execute("A", completed) is True  # Déjà complété
        assert resolver.can_execute("B", completed) is True
        assert resolver.can_execute("C", completed) is False

        # A et B complétés
        completed.add("B")
        assert resolver.can_execute("C", completed) is True

    def test_get_ready_steps(self):
        """Test de get_ready_steps."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Ready Steps Test",
            steps=[
                Step(name="A", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(name="B", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(
                    name="C",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A"],
                ),
                Step(
                    name="D",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A", "B"],
                ),
            ],
        )

        resolver = DAGResolver(job)

        # État initial - A et B sont prêts
        ready = resolver.get_ready_steps(set())
        assert set(ready) == {"A", "B"}

        # A complété - C devient prêt
        ready = resolver.get_ready_steps({"A"})
        assert set(ready) == {"B", "C"}

        # A et B complétés - D devient prêt
        ready = resolver.get_ready_steps({"A", "B"})
        assert set(ready) == {"C", "D"}

    def test_dependencies_and_dependents(self):
        """Test des méthodes get_dependencies et get_dependents."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Dependencies Test",
            steps=[
                Step(name="A", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(
                    name="B",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A"],
                ),
                Step(
                    name="C",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["A"],
                ),
                Step(
                    name="D",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["B", "C"],
                ),
            ],
        )

        resolver = DAGResolver(job)

        # Test dépendances
        assert resolver.get_dependencies("A") == []
        assert resolver.get_dependencies("B") == ["A"]
        assert set(resolver.get_dependencies("D")) == {"B", "C"}

        # Test dépendants
        assert set(resolver.get_dependents("A")) == {"B", "C"}
        assert resolver.get_dependents("B") == ["D"]
        assert resolver.get_dependents("D") == []

        # Test step inexistant
        with pytest.raises(DAGValidationError):
            resolver.get_dependencies("nonexistent")

    def test_empty_workflow(self):
        """Test avec workflow vide."""
        job = Job(name="Empty", steps=[])
        resolver = DAGResolver(job)

        assert resolver.get_execution_order() == []
        assert resolver.get_entry_points() == []
        assert resolver.get_exit_points() == []
        assert resolver.get_parallel_groups() == []

        stats = resolver.get_graph_stats()
        assert stats["total_steps"] == 0

    def test_single_step_workflow(self):
        """Test avec workflow à un seul step."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Single Step",
            steps=[Step(name="only", step_type=StepType.FUNCTION, handler=dummy_func)],
        )

        resolver = DAGResolver(job)

        assert resolver.get_execution_order() == ["only"]
        assert resolver.get_entry_points() == ["only"]
        assert resolver.get_exit_points() == ["only"]
        assert resolver.get_parallel_groups() == [["only"]]

        # Test critique path
        critical_path, length = resolver.get_critical_path()
        assert critical_path == ["only"]
        assert length == 0

    def test_critical_path_complex(self):
        """Test du chemin critique avec workflow complexe."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Critical Path Test",
            steps=[
                Step(name="start", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(
                    name="short",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["start"],
                ),
                Step(
                    name="long1",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["start"],
                ),
                Step(
                    name="long2",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["long1"],
                ),
                Step(
                    name="long3",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["long2"],
                ),
                Step(
                    name="end",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["short", "long3"],
                ),
            ],
        )

        resolver = DAGResolver(job)

        # Le chemin critique devrait être: start -> long1 -> long2 -> long3 -> end
        critical_path, length = resolver.get_critical_path()
        assert length == 4  # start -> long1 -> long2 -> long3 -> end
        assert critical_path[-1] == "end"
        assert "long3" in critical_path

    def test_parallel_groups_complex(self):
        """Test des groupes parallèles complexes."""

        def dummy_func():
            return {"result": "ok"}

        job = Job(
            name="Parallel Groups",
            steps=[
                # Niveau 0
                Step(name="init1", step_type=StepType.FUNCTION, handler=dummy_func),
                Step(name="init2", step_type=StepType.FUNCTION, handler=dummy_func),
                # Niveau 1
                Step(
                    name="proc1",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["init1"],
                ),
                Step(
                    name="proc2",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["init2"],
                ),
                Step(
                    name="proc3",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["init1", "init2"],
                ),
                # Niveau 2
                Step(
                    name="final",
                    step_type=StepType.FUNCTION,
                    handler=dummy_func,
                    dependencies=["proc1", "proc2", "proc3"],
                ),
            ],
        )

        resolver = DAGResolver(job)
        groups = resolver.get_parallel_groups()

        assert len(groups) == 3
        assert set(groups[0]) == {"init1", "init2"}
        assert set(groups[1]) == {"proc1", "proc2", "proc3"}
        assert groups[2] == ["final"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
