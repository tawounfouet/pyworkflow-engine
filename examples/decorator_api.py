"""
Exemples d'utilisation de l'API déclarative — @step / @job (ADR-005).

Démontre :
  1. Workflow minimal avec @step + @job
  2. Chaîne de dépendances avec injection de paramètres
  3. Injection depuis initial_context
  4. Mode legacy fn(context) dans un @job
  5. Cohabitation API impérative + déclarative
  6. Fonctions décorées testables en isolation (sans moteur)
  7. Mode explicite steps=[...]
  8. Décorateurs + ParallelRunner
"""

from __future__ import annotations

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.decorators import job, step

# ═══════════════════════════════════════════════════════════════════════════
# Exemple 1 — Workflow minimal
# ═══════════════════════════════════════════════════════════════════════════

print("\n── Exemple 1 : Workflow minimal ──────────────────────────")


@step(name="greet")
def greet() -> dict:
    return {"message": "Hello from @step!"}


@job(name="Hello Job")
def hello_job():
    greet()


engine = WorkflowEngine()
result = engine.run(hello_job.build())
print(f"Status : {result.status}")
print(f"Output : {result.get_step_run('greet').output_data}")


# ═══════════════════════════════════════════════════════════════════════════
# Exemple 2 — Chaîne de dépendances + injection de paramètres
# ═══════════════════════════════════════════════════════════════════════════

print("\n── Exemple 2 : Injection depuis les outputs des dépendances ──")


@step(name="fetch_records")
def fetch_records() -> dict:
    """Simule un fetch depuis une base de données."""
    return {"records": [10, 20, 30, 40, 50]}


@step(name="compute_stats", dependencies=["fetch_records"])
def compute_stats(records: list | None = None) -> dict:
    """Reçoit `records` automatiquement depuis l'output de 'fetch_records'."""
    data = records or []
    return {
        "count": len(data),
        "total": sum(data),
        "average": sum(data) / len(data) if data else 0,
    }


@step(name="format_report", dependencies=["compute_stats"])
def format_report(count: int = 0, total: int = 0, average: float = 0.0) -> dict:
    """Reçoit les stats injectées depuis l'output de 'compute_stats'."""
    return {"report": f"{count} records | total={total} | avg={average:.1f}"}


@job(name="Stats Pipeline")
def stats_pipeline():
    fetch_records()
    compute_stats()
    format_report()


result = engine.run(stats_pipeline.build())
print(f"Status : {result.status}")
print(f"Report : {result.get_step_run('format_report').output_data['report']}")


# ═══════════════════════════════════════════════════════════════════════════
# Exemple 3 — Injection depuis initial_context
# ═══════════════════════════════════════════════════════════════════════════

print("\n── Exemple 3 : Injection depuis initial_context ──────────────")


@step(name="use_config")
def use_config(source: str = "default", limit: int = 100) -> dict:
    """Paramètres injectés automatiquement depuis initial_context."""
    return {"source_used": source, "limit_used": limit}


@job(name="Config Job")
def config_job():
    use_config()


result = engine.run(
    config_job.build(),
    initial_context={"source": "production_db", "limit": 500},
)
print(f"Status : {result.status}")
print(f"Config : {result.get_step_run('use_config').output_data}")


# ═══════════════════════════════════════════════════════════════════════════
# Exemple 4 — Mode legacy fn(context) dans un @job
# ═══════════════════════════════════════════════════════════════════════════

print("\n── Exemple 4 : Mode legacy fn(context) ──────────────────────")


@step(name="legacy_step")
def legacy_handler(context) -> dict:
    """Mode rétrocompatible — reçoit le contexte complet."""
    value = context.get("legacy_value", "not_set")
    records_from_fetch = context.get_step_output("fetch_records", {}).get("records", [])
    return {"value": value, "nb_records": len(records_from_fetch)}


@job(name="Mixed Job")
def mixed_job():
    fetch_records()     # step pur (injection)
    legacy_handler()    # step legacy (context)


result = engine.run(
    mixed_job.build(),
    initial_context={"legacy_value": "hello"},
)
print(f"Status : {result.status}")
print(f"Legacy output : {result.get_step_run('legacy_step').output_data}")


# ═══════════════════════════════════════════════════════════════════════════
# Exemple 5 — Cohabitation API impérative + déclarative
# ═══════════════════════════════════════════════════════════════════════════

print("\n── Exemple 5 : Cohabitation impérative + déclarative ─────────")

from pyworkflow_engine import Job, Step, StepType  # noqa: E402


# API impérative (inchangée)
def fetch_imperative(context):
    return {"records": [1, 2, 3]}


imperative_job = Job(
    name="Imperative ETL",
    steps=[
        Step(name="fetch", step_type=StepType.FUNCTION, handler=fetch_imperative)
    ],
)

# API déclarative (nouvelle)
@step(name="fetch")
def fetch_declarative() -> dict:
    return {"records": [1, 2, 3]}


@job(name="Declarative ETL")
def declarative_etl():
    fetch_declarative()


r1 = engine.run(imperative_job)
r2 = engine.run(declarative_etl.build())
print(f"Imperative : {r1.status}")
print(f"Declarative: {r2.status}")


# ═══════════════════════════════════════════════════════════════════════════
# Exemple 6 — Fonctions pures testables sans moteur
# ═══════════════════════════════════════════════════════════════════════════

print("\n── Exemple 6 : Fonctions décorées testables en isolation ──────")

# Les fonctions décorées restent appelables normalement
assert greet() == {"message": "Hello from @step!"}
assert fetch_records() == {"records": [10, 20, 30, 40, 50]}
assert compute_stats(records=[1, 2, 3]) == {"count": 3, "total": 6, "average": 2.0}
assert format_report(count=3, total=6, average=2.0) == {
    "report": "3 records | total=6 | avg=2.0"
}
print("✅ Toutes les assertions passent — aucun mock nécessaire !")

# Les métadonnées d'orchestration sont accessibles via __step_spec__
print(f"fetch_records spec : name={fetch_records.__step_spec__.name}")
print(f"compute_stats deps : {compute_stats.__step_spec__.dependencies}")


# ═══════════════════════════════════════════════════════════════════════════
# Exemple 7 — Mode explicite steps=[...]
# ═══════════════════════════════════════════════════════════════════════════

print("\n── Exemple 7 : Mode explicite steps=[...] ────────────────────")


@step(name="step_a")
def step_a() -> dict:
    return {"x": 42}


@step(name="step_b", dependencies=["step_a"])
def step_b(x: int = 0) -> dict:
    return {"doubled": x * 2}


# Mode explicite — robuste pour les steps importés dynamiquement
@job(name="Explicit Job", steps=[step_a, step_b])
def explicit_job(): ...


result = engine.run(explicit_job.build())
print(f"Status : {result.status}")
print(f"Output : {result.get_step_run('step_b').output_data}")


# ═══════════════════════════════════════════════════════════════════════════
# Exemple 8 — @step + ParallelRunner
# ═══════════════════════════════════════════════════════════════════════════

print("\n── Exemple 8 : Décorateurs + ParallelRunner ──────────────────")


@step(name="task_x")
def task_x() -> dict:
    return {"x": 1}


@step(name="task_y")
def task_y() -> dict:
    return {"y": 2}


@step(name="task_z")
def task_z() -> dict:
    return {"z": 3}


@step(name="aggregate", dependencies=["task_x", "task_y", "task_z"])
def aggregate(x: int = 0, y: int = 0, z: int = 0) -> dict:
    return {"sum": x + y + z}


@job(name="Parallel Job")
def parallel_job():
    task_x()
    task_y()
    task_z()
    aggregate()


parallel_engine = WorkflowEngine(parallel=True, max_workers=3)
result = parallel_engine.run(parallel_job.build())
print(f"Status : {result.status}")
print(f"Sum    : {result.get_step_run('aggregate').output_data}")

print("\n✅ Tous les exemples ont réussi.")
