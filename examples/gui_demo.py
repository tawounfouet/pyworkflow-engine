"""Démonstration de l'interface GUI PyWorkflow (NiceGUI).

Ce module remplit automatiquement une base SQLite avec des jobs variés
et plusieurs exécutions (succès, échecs, étapes parallèles…) afin que
le tableau de bord soit immédiatement riche à l'ouverture.

Usage
-----
Mode intégré (engine passé par ``--app``) ::

    pyworkflow --app examples.gui_demo:engine gui

Lancement autonome (lance la GUI directement) ::

    python examples/gui_demo.py

Options utiles ::

    pyworkflow --app examples.gui_demo:engine gui --port 8080 --light
    pyworkflow --app examples.gui_demo:engine gui --port 8080 --refresh 2.0
"""

from __future__ import annotations

import random
import time
from datetime import timedelta
from pathlib import Path

from pyworkflow_engine import WorkflowEngine, WorkflowContext
from pyworkflow_engine.models import Job
from pyworkflow_engine.models.enums import ExecutorType, Priority, StepType
from pyworkflow_engine.models.step import Step
from pyworkflow_engine.adapters.storage import SQLiteStorage

# ---------------------------------------------------------------------------
# Configuration de la base SQLite démo
# ---------------------------------------------------------------------------

#_DB_PATH = str(Path(__file__).parent.parent / "workflow_demo.db")
_DB_PATH = str(Path(__file__).parent.parent / "workflow.db")


# ---------------------------------------------------------------------------
# Fonctions de steps réutilisables
# ---------------------------------------------------------------------------


def _sleep(seconds: float) -> None:
    """Simule un travail I/O-bound."""
    time.sleep(seconds)


# ── ETL pipeline ─────────────────────────────────────────────────────────────


def extract_records(context: WorkflowContext) -> dict:
    """Extrait des données brutes depuis la source (simulé)."""
    _sleep(0.05)
    return {
        "records": [
            {"id": i, "value": round(random.uniform(1.0, 100.0), 2)} for i in range(50)
        ],
        "source": "demo_db",
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def validate_records(context: WorkflowContext) -> dict:
    """Valide le schéma et filtre les doublons."""
    _sleep(0.04)
    records = context.get_step_output("extract")["records"]
    valid = [r for r in records if r["value"] > 0]
    return {"valid_count": len(valid), "dropped": len(records) - len(valid)}


def transform_records(context: WorkflowContext) -> dict:
    """Normalise et enrichit les enregistrements."""
    _sleep(0.06)
    info = context.get_step_output("validate")
    return {
        "transformed": info["valid_count"],
        "schema_version": "v2",
    }


def load_to_warehouse(context: WorkflowContext) -> dict:
    """Charge les données dans l'entrepôt (simulé)."""
    _sleep(0.03)
    info = context.get_step_output("transform")
    return {"loaded": info["transformed"], "warehouse": "demo_warehouse"}


def send_etl_report(context: WorkflowContext) -> dict:
    """Envoie un e-mail de rapport post-ETL."""
    _sleep(0.02)
    loaded = context.get_step_output("load")["loaded"]
    return {"report_sent": True, "rows_reported": loaded}


# ── Health check ──────────────────────────────────────────────────────────────


def check_database(context: WorkflowContext) -> dict:
    _sleep(0.03)
    return {"db_ok": True, "latency_ms": round(random.uniform(1, 15), 1)}


def check_api(context: WorkflowContext) -> dict:
    _sleep(0.04)
    return {"api_ok": True, "status_code": 200}


def check_cache(context: WorkflowContext) -> dict:
    _sleep(0.02)
    return {"cache_ok": True, "hit_rate": round(random.uniform(0.7, 0.99), 3)}


def aggregate_health(context: WorkflowContext) -> dict:
    _sleep(0.01)
    db = context.get_step_output("check_db")
    api = context.get_step_output("check_api")
    cache = context.get_step_output("check_cache")
    all_ok = db["db_ok"] and api["api_ok"] and cache["cache_ok"]
    return {"overall_status": "healthy" if all_ok else "degraded"}


# ── Data science pipeline ─────────────────────────────────────────────────────


def ingest_raw_data(context: WorkflowContext) -> dict:
    _sleep(0.05)
    return {"rows": 1000, "columns": 12, "source": "parquet://demo/dataset.parquet"}


def feature_engineering(context: WorkflowContext) -> dict:
    _sleep(0.08)
    return {"features": 24, "derived_from": "raw_data", "nulls_filled": 37}


def train_model(context: WorkflowContext) -> dict:
    _sleep(0.12)
    return {
        "model": "RandomForest",
        "accuracy": round(random.uniform(0.88, 0.97), 4),
        "n_estimators": 100,
    }


def evaluate_model(context: WorkflowContext) -> dict:
    _sleep(0.05)
    acc = context.get_step_output("train")["accuracy"]
    return {
        "test_accuracy": round(acc - random.uniform(0.01, 0.03), 4),
        "f1_score": round(random.uniform(0.85, 0.95), 4),
    }


def publish_model(context: WorkflowContext) -> dict:
    _sleep(0.03)
    return {"model_id": f"model-{random.randint(1000, 9999)}", "registry": "mlflow"}


# ── Report generation ────────────────────────────────────────────────────────


def query_kpis(context: WorkflowContext) -> dict:
    _sleep(0.04)
    return {
        "revenue": round(random.uniform(10_000, 50_000), 2),
        "orders": random.randint(100, 500),
        "churn_rate": round(random.uniform(0.01, 0.08), 3),
    }


def render_pdf(context: WorkflowContext) -> dict:
    _sleep(0.06)
    kpis = context.get_step_output("query_kpis")
    return {"pages": 5, "size_kb": random.randint(80, 250), "kpis_included": len(kpis)}


def distribute_report(context: WorkflowContext) -> dict:
    _sleep(0.02)
    return {"recipients": ["ceo@demo.com", "cfo@demo.com"], "channel": "email"}


# ── Flaky step (raises on first call, succeeds on retry) ─────────────────────

_flaky_call_counts: dict[str, int] = {}


def flaky_api_call(context: WorkflowContext) -> dict:
    """Simule un appel réseau instable — échoue 1 fois sur 2."""
    key = "flaky_api_call"
    _flaky_call_counts[key] = _flaky_call_counts.get(key, 0) + 1
    if _flaky_call_counts[key] % 2 == 1:  # odd calls fail
        raise ConnectionError("Simulated timeout from upstream API (will retry)")
    return {"response": "ok", "attempt": _flaky_call_counts[key]}


def process_api_result(context: WorkflowContext) -> dict:
    _sleep(0.02)
    result = context.get_step_output("fetch_upstream")
    return {"processed": True, "attempt": result.get("attempt", 1)}


# ── Intentional-failure step ─────────────────────────────────────────────────


def always_fails(context: WorkflowContext) -> dict:
    """Simule une étape vouée à l'échec — illustre le statut FAILED dans la GUI."""
    raise RuntimeError("Simulated downstream service outage (demo)")


def post_failure_cleanup(context: WorkflowContext) -> dict:
    return {"cleanup": "done"}


# ---------------------------------------------------------------------------
# Définition des jobs
# ---------------------------------------------------------------------------

etl_job = Job(
    name="etl_pipeline",
    description=(
        "Pipeline ETL complet : extraction → validation → transformation → "
        "chargement → rapport. Démontre un DAG séquentiel classique."
    ),
    steps=[
        Step(name="extract", step_type=StepType.FUNCTION, handler=extract_records),
        Step(
            name="validate",
            step_type=StepType.FUNCTION,
            handler=validate_records,
            dependencies=["extract"],
        ),
        Step(
            name="transform",
            step_type=StepType.FUNCTION,
            handler=transform_records,
            dependencies=["validate"],
        ),
        Step(
            name="load",
            step_type=StepType.FUNCTION,
            handler=load_to_warehouse,
            dependencies=["transform"],
        ),
        Step(
            name="report",
            step_type=StepType.FUNCTION,
            handler=send_etl_report,
            dependencies=["load"],
        ),
    ],
    default_executor=ExecutorType.LOCAL,
    priority=Priority.HIGH,
    metadata={"team": "data-engineering", "schedule": "daily@02:00", "sla_minutes": 30},
    tags=["etl", "daily", "data"],
)

health_check_job = Job(
    name="health_check",
    description=(
        "Vérifie la santé des services critiques (DB, API, cache) en parallèle "
        "puis consolide un statut global."
    ),
    steps=[
        Step(name="check_db", step_type=StepType.FUNCTION, handler=check_database),
        Step(name="check_api", step_type=StepType.FUNCTION, handler=check_api),
        Step(name="check_cache", step_type=StepType.FUNCTION, handler=check_cache),
        Step(
            name="aggregate",
            step_type=StepType.FUNCTION,
            handler=aggregate_health,
            dependencies=["check_db", "check_api", "check_cache"],
        ),
    ],
    default_executor=ExecutorType.LOCAL,
    priority=Priority.CRITICAL,
    metadata={"team": "platform", "schedule": "*/5 * * * *", "alert_channel": "#ops"},
    tags=["monitoring", "infra"],
)

ml_pipeline_job = Job(
    name="ml_training_pipeline",
    description=(
        "Pipeline de ML : ingestion → feature engineering → entraînement → "
        "évaluation → publication du modèle."
    ),
    steps=[
        Step(name="ingest", step_type=StepType.FUNCTION, handler=ingest_raw_data),
        Step(
            name="features",
            step_type=StepType.FUNCTION,
            handler=feature_engineering,
            dependencies=["ingest"],
        ),
        Step(
            name="train",
            step_type=StepType.FUNCTION,
            handler=train_model,
            dependencies=["features"],
            timeout=timedelta(minutes=10),
        ),
        Step(
            name="evaluate",
            step_type=StepType.FUNCTION,
            handler=evaluate_model,
            dependencies=["train"],
        ),
        Step(
            name="publish",
            step_type=StepType.FUNCTION,
            handler=publish_model,
            dependencies=["evaluate"],
        ),
    ],
    default_executor=ExecutorType.LOCAL,
    priority=Priority.NORMAL,
    metadata={"team": "ml-platform", "framework": "sklearn", "model": "RandomForest"},
    tags=["ml", "training", "weekly"],
)

reporting_job = Job(
    name="weekly_report",
    description="Génère et distribue le rapport hebdomadaire des KPIs métier.",
    steps=[
        Step(name="query_kpis", step_type=StepType.FUNCTION, handler=query_kpis),
        Step(
            name="render_pdf",
            step_type=StepType.FUNCTION,
            handler=render_pdf,
            dependencies=["query_kpis"],
        ),
        Step(
            name="distribute",
            step_type=StepType.FUNCTION,
            handler=distribute_report,
            dependencies=["render_pdf"],
        ),
    ],
    default_executor=ExecutorType.LOCAL,
    priority=Priority.LOW,
    metadata={"team": "analytics", "recipients": 2, "format": "PDF"},
    tags=["reporting", "weekly", "kpis"],
)

retry_demo_job = Job(
    name="flaky_integration",
    description=(
        "Démontre la gestion des erreurs transitoires : l'étape fetch_upstream "
        "échoue une fois sur deux avant de réussir au retry."
    ),
    steps=[
        Step(
            name="fetch_upstream",
            step_type=StepType.FUNCTION,
            handler=flaky_api_call,
            retry_count=2,
            retry_delay=timedelta(seconds=0),
        ),
        Step(
            name="process",
            step_type=StepType.FUNCTION,
            handler=process_api_result,
            dependencies=["fetch_upstream"],
        ),
    ],
    default_executor=ExecutorType.LOCAL,
    priority=Priority.NORMAL,
    metadata={"team": "integrations", "upstream": "partner-api-v3"},
    tags=["integration", "retry"],
)

failure_demo_job = Job(
    name="failing_pipeline",
    description=(
        "Pipeline intentionnellement défaillant — illustre l'état FAILED "
        "et les messages d'erreur dans la vue Run Detail."
    ),
    steps=[
        Step(name="prepare", step_type=StepType.FUNCTION, handler=extract_records),
        Step(
            name="crash",
            step_type=StepType.FUNCTION,
            handler=always_fails,
            dependencies=["prepare"],
        ),
        Step(
            name="cleanup",
            step_type=StepType.FUNCTION,
            handler=post_failure_cleanup,
            dependencies=["crash"],
        ),
    ],
    default_executor=ExecutorType.LOCAL,
    priority=Priority.LOW,
    metadata={"team": "qa", "purpose": "error-demo"},
    tags=["demo", "error-handling"],
)

# ---------------------------------------------------------------------------
# Seed : engine + persistence + exécutions initiales
# ---------------------------------------------------------------------------

_ALL_JOBS = [
    etl_job,
    health_check_job,
    ml_pipeline_job,
    reporting_job,
    retry_demo_job,
    failure_demo_job,
]


def _seed_runs(eng: WorkflowEngine) -> None:
    """Lance plusieurs exécutions historiques pour alimenter la GUI."""

    print("  [gui_demo] Seeding demo runs …")

    # ETL — 3 succès successifs
    for i in range(3):
        eng.run_with_storage(etl_job)
        print(f"    ✓ etl_pipeline run {i + 1}/3")

    # Health check — 5 exécutions rapides (simule un cron 5-min)
    for i in range(5):
        eng.run_with_storage(health_check_job)
        print(f"    ✓ health_check run {i + 1}/5")

    # ML pipeline — 2 exécutions (les accuracy varient aléatoirement)
    for i in range(2):
        eng.run_with_storage(ml_pipeline_job)
        print(f"    ✓ ml_training_pipeline run {i + 1}/2")

    # Weekly report — 1 exécution
    eng.run_with_storage(reporting_job)
    print("    ✓ weekly_report run 1/1")

    # Retry demo — 2 exécutions (la première tentative flaky échoue et retry)
    for i in range(2):
        eng.run_with_storage(retry_demo_job)
        print(f"    ✓ flaky_integration run {i + 1}/2")

    # Failure demo — 2 exécutions délibérément en FAILED
    for i in range(2):
        try:
            eng.run_with_storage(failure_demo_job)
        except Exception:
            pass  # échec attendu — le JobRun FAILED est déjà persisté
        print(f"    ✓ failing_pipeline run {i + 1}/2 (expected FAILED)")

    print("  [gui_demo] Seeding complete — GUI is ready.")


def _build_engine() -> WorkflowEngine:
    """Construit et retourne le WorkflowEngine avec SQLite et données démo."""
    db_path = _DB_PATH
    persistence = SQLiteStorage(database_path=db_path)
    eng = WorkflowEngine(storage=persistence)

    # Enregistre tous les jobs
    for job in _ALL_JOBS:
        eng.save_job(job)
        print(f"  [gui_demo] Registered job: {job.name!r}")

    # Vérifie si des runs existent déjà pour ne pas dupliquer à chaque import
    existing_runs = eng.list_job_runs(limit=1)
    if not existing_runs:
        _seed_runs(eng)
    else:
        print(
            f"  [gui_demo] Existing runs found in {db_path!r} — skipping seed. "
            "Delete the file to re-seed."
        )

    return eng


# Module-level engine — exposé pour le CLI loader (--app examples.gui_demo:engine)
print(f"[gui_demo] Initialising demo engine → {_DB_PATH}")
engine = _build_engine()
print("[gui_demo] Engine ready.\n")

# ---------------------------------------------------------------------------
# Point d'entrée autonome
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Lance la GUI directement sans passer par la CLI pyworkflow.

    Équivalent de :
        pyworkflow --app examples.gui_demo:engine gui --show
    """
    try:
        from pyworkflow_engine.adapters.gui import WorkflowGUI
        from pyworkflow_engine.adapters.gui.config import GUIConfig
    except ImportError as exc:
        raise SystemExit(
            "NiceGUI est requis pour la GUI. "
            "Installez-le avec : pip install 'pyworkflow-engine[gui]'"
        ) from exc

    config = GUIConfig(
        host="127.0.0.1",
        port=8080,
        db_path=_DB_PATH,
        title="PyWorkflow Demo",
        dark_mode=True,
        show_browser=True,
        refresh_interval=3.0,
    )

    print(f"\n🚀 Démarrage de la GUI sur http://{config.host}:{config.port}")
    print(f"   Base SQLite : {_DB_PATH}")
    print(f"   Jobs enregistrés : {len(_ALL_JOBS)}")
    print("   Appuyez sur Ctrl+C pour arrêter.\n")

    gui = WorkflowGUI(engine, config)
    gui.run()
