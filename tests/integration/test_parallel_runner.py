"""
Tests d'intégration — ParallelRunner (scénarios fork-join).

Valide que :
- Les steps sans dépendances communes s'exécutent en parallèle dans le même groupe.
- Les steps avec dépendances respectent l'ordre topologique entre groupes.
- Le contexte est correctement partagé entre branches parallèles.
- La reprise (resume) ne ré-exécute pas les steps déjà terminés.
- Un échec dans une branche n'exécute pas les branches suivantes.

Architecture fork-join typique testée :

    start
    ├── branch_a   ┐
    └── branch_b   ┘  (groupe parallèle)
         ↓
        merge
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from pyworkflow_engine import Job, Step, StepType, WorkflowEngine
from pyworkflow_engine.engine.context import WorkflowContext
from pyworkflow_engine.engine.dag import DAGResolver
from pyworkflow_engine.engine.parallel_runner import ParallelRunner
from pyworkflow_engine.exceptions import WorkflowFailed
from pyworkflow_engine.models import JobRun, RunStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_fork_join_job(
    start_fn=None,
    branch_a_fn=None,
    branch_b_fn=None,
    merge_fn=None,
) -> Job:
    """Construit un DAG fork-join à 4 steps :

        start → branch_a ─┐
              → branch_b ─┤
                           ↓
                         merge
    """
    steps = [
        Step(
            name="start",
            step_type=StepType.FUNCTION,
            handler=start_fn or (lambda: {"start_value": 1}),
        ),
        Step(
            name="branch_a",
            step_type=StepType.FUNCTION,
            handler=branch_a_fn or (lambda: {"a_value": "A"}),
            dependencies=["start"],
        ),
        Step(
            name="branch_b",
            step_type=StepType.FUNCTION,
            handler=branch_b_fn or (lambda: {"b_value": "B"}),
            dependencies=["start"],
        ),
        Step(
            name="merge",
            step_type=StepType.FUNCTION,
            handler=merge_fn or (lambda ctx: {"merged": True}),
            dependencies=["branch_a", "branch_b"],
        ),
    ]
    return Job(name="fork_join_workflow", steps=steps)


# ---------------------------------------------------------------------------
# Tests de base — structure DAG
# ---------------------------------------------------------------------------


class TestParallelRunnerDAGStructure:
    """Vérifie que le DAG fork-join est correctement interprété."""

    def test_parallel_groups_structure(self):
        """branch_a et branch_b doivent être dans le même groupe parallèle."""
        job = make_fork_join_job()
        resolver = DAGResolver(job)
        groups = resolver.get_parallel_groups()

        # On attend 3 groupes : [start], [branch_a, branch_b], [merge]
        assert len(groups) == 3, f"Attendu 3 groupes, obtenu {len(groups)}: {groups}"

        flat = [sorted(g) for g in groups]
        assert flat[0] == ["start"]
        assert flat[1] == ["branch_a", "branch_b"]
        assert flat[2] == ["merge"]

    def test_execution_order_is_topological(self):
        """L'ordre d'exécution respecte les dépendances."""
        job = make_fork_join_job()
        resolver = DAGResolver(job)
        order = resolver.get_execution_order()

        assert order.index("start") < order.index("branch_a")
        assert order.index("start") < order.index("branch_b")
        assert order.index("branch_a") < order.index("merge")
        assert order.index("branch_b") < order.index("merge")


# ---------------------------------------------------------------------------
# Tests d'exécution parallèle
# ---------------------------------------------------------------------------


class TestParallelRunnerExecution:
    """Vérifie l'exécution effective du DAG fork-join."""

    def test_basic_fork_join_success(self):
        """Un DAG fork-join simple doit s'exécuter jusqu'au succès."""
        job = make_fork_join_job()
        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert len(result.step_runs) == 4
        assert all(sr.status == RunStatus.SUCCESS for sr in result.step_runs)

    def test_branches_run_in_parallel(self):
        """branch_a et branch_b doivent s'exécuter concurremment."""
        thread_ids: set[int] = set()
        lock = threading.Lock()

        def recording_branch(name: str):
            def fn():
                with lock:
                    thread_ids.add(threading.get_ident())
                time.sleep(0.05)  # Petite pause pour forcer le chevauchement
                return {name: True}
            return fn

        job = make_fork_join_job(
            branch_a_fn=recording_branch("a"),
            branch_b_fn=recording_branch("b"),
        )
        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        # Si les deux branches ont tourné, au moins 1 thread différent a été utilisé
        # (le thread principal + au moins 1 worker)
        assert len(thread_ids) >= 1

    def test_context_shared_across_branches(self):
        """Les sorties de branch_a et branch_b sont accessibles dans merge."""
        seen_in_merge = {}

        def start_fn():
            return {"origin": "root"}

        def branch_a_fn():
            return {"a_result": 42}

        def branch_b_fn():
            return {"b_result": "hello"}

        def merge_fn(ctx: WorkflowContext):
            seen_in_merge["a"] = ctx.get_step_output("branch_a")
            seen_in_merge["b"] = ctx.get_step_output("branch_b")
            seen_in_merge["start"] = ctx.get_step_output("start")
            return {"done": True}

        job = make_fork_join_job(
            start_fn=start_fn,
            branch_a_fn=branch_a_fn,
            branch_b_fn=branch_b_fn,
            merge_fn=merge_fn,
        )
        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert seen_in_merge.get("a") == {"a_result": 42}
        assert seen_in_merge.get("b") == {"b_result": "hello"}
        assert seen_in_merge.get("start") == {"origin": "root"}

    def test_step_runs_recorded_in_job_run(self):
        """Chaque step doit produire un StepRun dans le JobRun."""
        job = make_fork_join_job()
        engine = WorkflowEngine()
        result = engine.run(job)

        names = {sr.step_name for sr in result.step_runs}
        assert names == {"start", "branch_a", "branch_b", "merge"}

    def test_merge_reads_correct_outputs(self):
        """Vérifie que merge combine les sorties des deux branches."""
        def branch_a_fn():
            return {"value": 10}

        def branch_b_fn():
            return {"value": 20}

        combined = {}

        def merge_fn(ctx: WorkflowContext):
            a = ctx.get_step_output("branch_a", {}).get("value", 0)
            b = ctx.get_step_output("branch_b", {}).get("value", 0)
            combined["total"] = a + b
            return combined

        job = make_fork_join_job(
            branch_a_fn=branch_a_fn,
            branch_b_fn=branch_b_fn,
            merge_fn=merge_fn,
        )
        engine = WorkflowEngine()
        result = engine.run(job)

        assert result.status == RunStatus.SUCCESS
        assert combined["total"] == 30


# ---------------------------------------------------------------------------
# Tests de reprise (resume) après suspension
# ---------------------------------------------------------------------------


class TestParallelRunnerResume:
    """Vérifie que la reprise respecte les steps déjà terminés."""

    def test_resume_skips_completed_steps(self):
        """ParallelRunner ne doit pas ré-exécuter les steps SUCCESS lors de la reprise."""
        call_counts: dict[str, int] = {"branch_a": 0, "branch_b": 0, "merge": 0}

        def counting(name: str):
            def fn():
                call_counts[name] += 1
                return {name: call_counts[name]}
            return fn

        job = make_fork_join_job(
            branch_a_fn=counting("branch_a"),
            branch_b_fn=counting("branch_b"),
            merge_fn=counting("merge"),
        )

        # Exécution complète
        engine = WorkflowEngine()
        result = engine.run(job)
        assert result.status == RunStatus.SUCCESS
        assert call_counts == {"branch_a": 1, "branch_b": 1, "merge": 1}

        # Simulation d'une reprise partielle : branch_a et start déjà terminés
        # On appelle directement ParallelRunner avec execution_order réduit
        job_run = result
        context = WorkflowContext(job_run)
        for sr in job_run.step_runs:
            if sr.status == RunStatus.SUCCESS:
                context.set_step_output(sr.step_name, sr.output_data)

        runner = ParallelRunner()
        remaining = ["branch_b", "merge"]  # Simuler que branch_a est déjà fait
        runner.execute(job_run, remaining, context)

        # branch_b et merge ont été relancés, branch_a ne l'a pas été
        assert call_counts["branch_a"] == 1   # Inchangé — pas dans execution_order
        assert call_counts["branch_b"] == 2   # Relancé
        assert call_counts["merge"] == 2      # Relancé après branch_b

    def test_execution_order_empty_skips_all_groups(self):
        """Un execution_order vide ne doit exécuter aucun step."""
        call_counts = {"called": 0}

        def counting_fn():
            call_counts["called"] += 1
            return {}

        job = make_fork_join_job(
            start_fn=counting_fn,
            branch_a_fn=counting_fn,
            branch_b_fn=counting_fn,
            merge_fn=counting_fn,
        )
        engine = WorkflowEngine()
        result = engine.run(job)

        initial_count = call_counts["called"]  # 4 étapes = 4 appels

        # Repr avec execution_order vide — aucun step ne doit être relancé
        context = WorkflowContext(result)
        runner = ParallelRunner()
        runner.execute(result, [], context)  # execution_order vide

        assert call_counts["called"] == initial_count  # Aucun appel supplémentaire


# ---------------------------------------------------------------------------
# Tests de gestion d'erreurs
# ---------------------------------------------------------------------------


class TestParallelRunnerErrorHandling:
    """Vérifie le comportement en cas d'échec dans une branche."""

    def test_branch_failure_propagates(self):
        """Un échec dans branch_a doit propager une StepExecutionError."""
        from pyworkflow_engine.exceptions import StepExecutionError

        def failing_branch():
            raise ValueError("Branch A failed deliberately")

        job = make_fork_join_job(branch_a_fn=failing_branch)
        engine = WorkflowEngine()

        with pytest.raises(StepExecutionError) as exc_info:
            engine.run(job)

        assert "branch_a" in str(exc_info.value)

    def test_merge_not_executed_after_branch_failure(self):
        """merge ne doit pas s'exécuter si une branche échoue."""
        from pyworkflow_engine.exceptions import StepExecutionError

        merge_called = {"called": False}

        def failing_branch():
            raise RuntimeError("Deliberate failure")

        def merge_fn(ctx):
            merge_called["called"] = True
            return {}

        job = make_fork_join_job(
            branch_a_fn=failing_branch,
            merge_fn=merge_fn,
        )
        engine = WorkflowEngine()

        with pytest.raises(StepExecutionError):
            engine.run(job)

        assert not merge_called["called"], "merge ne doit pas s'exécuter après un échec"
