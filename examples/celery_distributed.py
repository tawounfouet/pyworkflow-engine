"""Exemple — Exécution distribuée d'un workflow via Celery (ADR-007).

Prérequis :
    pip install pyworkflow-engine[celery]

    # Démarrer Redis (Docker)
    docker run -d -p 6379:6379 redis:alpine

    # Démarrer un worker Celery (dans un terminal séparé)
    celery -A pyworkflow_engine.adapters.celery.tasks worker --loglevel=info

Ce script peut ensuite être exécuté depuis un troisième terminal :
    python examples/celery_distributed.py

Architecture :
    Client (ce script) → broker Redis → Celery worker → résultat → client

Contrainte de sérialisation :
    Les handlers de steps DOIVENT être des fonctions top-level importables.
    Les lambdas et closures ne fonctionnent pas avec Celery (non sérialisables).
"""

from __future__ import annotations

# ── Handlers — fonctions top-level importables ───────────────────────────────
# IMPORTANT : ces fonctions doivent être définies au top-level du module
# (pas dans une classe, pas de lambda) pour être sérialisables par Celery.


def extract_data() -> dict:
    """Simule l'extraction de données depuis une source externe."""
    print("[worker] Extraction des données...")
    return {
        "records": [
            {"id": 1, "value": 100},
            {"id": 2, "value": 200},
            {"id": 3, "value": 300},
        ],
        "count": 3,
    }


def transform_data(context: dict) -> dict:
    """Transforme les données extraites par le step précédent."""
    step_outputs = context.get("step_outputs", {})
    records = step_outputs.get("extract", {}).get("records", [])
    print(f"[worker] Transformation de {len(records)} enregistrements...")
    transformed = [{"id": r["id"], "value": r["value"] * 2} for r in records]
    return {"transformed": transformed, "total": sum(r["value"] for r in transformed)}


def load_data(context: dict) -> dict:
    """Charge les données transformées dans la destination."""
    step_outputs = context.get("step_outputs", {})
    total = step_outputs.get("transform", {}).get("total", 0)
    count = step_outputs.get("transform", {}).get("transformed", [])
    print(f"[worker] Chargement — total={total}, {len(count)} enregistrements")
    return {"loaded": True, "total": total, "record_count": len(count)}


# ── Workflow ETL distribué ───────────────────────────────────────────────────


def run_distributed_etl() -> None:
    """Lance un pipeline ETL distribué sur des workers Celery."""
    from pyworkflow_engine import Job, Step, StepType, WorkflowEngine
    from pyworkflow_engine.adapters.celery import CeleryConfig, CeleryExecutor
    from pyworkflow_engine.models.enums import ExecutorType

    # ── Configuration Celery ─────────────────────────────────────────────────
    config = CeleryConfig(
        broker_url="redis://localhost:6379/0",
        result_backend="redis://localhost:6379/1",
        task_timeout=30.0,
        task_default_queue="etl_pipeline",
    )
    executor = CeleryExecutor(config=config)

    # ── Moteur de workflow ───────────────────────────────────────────────────
    engine = WorkflowEngine()
    engine.register_executor("celery", executor)

    # ── Définition du job ETL ─────────────────────────────────────────────────
    # Voie 1 (recommandée) : executor_name="celery" → ExecutorRegistry lookup
    job = Job(
        name="etl_distributed",
        description="Pipeline ETL distribué sur workers Celery",
        steps=[
            Step(
                name="extract",
                step_type=StepType.FUNCTION,
                handler=extract_data,
                # executor_type=ExecutorType.CELERY  ← Voie 2 (auto-discovery)
                # executor_name="celery"              ← Voie 1 (recommandée)
                metadata={"description": "Extraction depuis la source"},
            ),
            Step(
                name="transform",
                step_type=StepType.FUNCTION,
                handler=transform_data,
                dependencies=["extract"],
                metadata={"description": "Transformation des données"},
            ),
            Step(
                name="load",
                step_type=StepType.FUNCTION,
                handler=load_data,
                dependencies=["transform"],
                metadata={"description": "Chargement vers la destination"},
            ),
        ],
    )

    print("Lancement du pipeline ETL distribué...")
    print(f"Broker : {config.broker_url}")
    print(f"Queue  : {config.task_default_queue}")
    print()

    try:
        result = engine.run(job, executor_name="celery")
        print(f"\nStatut : {result.status.value}")
        for step_run in result.step_runs:
            print(f"  {step_run.step_name}: {step_run.status.value} → {step_run.output_data}")
    finally:
        engine.shutdown_executors()


# ── Exemple avec ExecutorType.CELERY (auto-discovery, voie 2) ────────────────


def run_with_executor_type() -> None:
    """Démontre le routing automatique via ExecutorType.CELERY.

    Dans ce mode, le step déclare executor_type=CELERY.
    Le WorkflowRunner instancie automatiquement un CeleryExecutor
    avec la configuration par défaut.
    """
    from pyworkflow_engine import Job, Step, StepType, WorkflowEngine
    from pyworkflow_engine.models.enums import ExecutorType

    engine = WorkflowEngine()

    job = Job(
        name="celery_autodiscovery",
        steps=[
            Step(
                name="distributed_step",
                step_type=StepType.FUNCTION,
                handler=extract_data,
                executor_type=ExecutorType.CELERY,
            ),
        ],
    )

    print("Lancement avec ExecutorType.CELERY (auto-discovery)...")
    result = engine.run(job)
    print(f"Statut : {result.status.value}")


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "etl"

    if mode == "auto":
        run_with_executor_type()
    else:
        run_distributed_etl()
