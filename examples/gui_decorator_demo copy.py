"""
Démo GUI — jobs définis avec les décorateurs @step / @job.

Pipeline : audit de qualité de données
  collect → (validate_schema ‖ compute_stats) → generate_report
                  └── retry_count=2

─────────────────────────────────────────────────────────────────────────
Seed la BD (jobs visibles dans la GUI courante, bouton Lancer inactif) :

    python examples/gui_decorator_demo.py

GUI complète avec bouton Lancer fonctionnel (handlers importables) :

    pyworkflow --app examples.gui_decorator_demo:engine gui
─────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import random
import time
from pathlib import Path

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.adapters.persistence import SQLitePersistence
from pyworkflow_engine.decorators import job, step

_DB_PATH = str(Path(__file__).parent.parent / "workflow.db")


# ── Steps : pipeline "Data Quality Audit" ────────────────────────────────────


@step(name="collect_data")
def collect_data() -> dict:
    """Simule la collecte d'un dataset depuis une source externe."""
    time.sleep(0.05)
    n = random.randint(800, 1200)
    return {
        "rows": n,
        "columns": ["id", "name", "score", "created_at", "status"],
        "source": "postgres://demo/events",
    }


@step(
    name="validate_schema",
    dependencies=["collect_data"],
    retry_count=2,
    retry_delay=0.5,
)
def validate_schema(rows: int = 0, columns: list | None = None) -> dict:
    """Vérifie le schéma attendu — retry x2 en cas d'échec transitoire."""
    time.sleep(0.04)
    expected = {"id", "name", "score", "created_at", "status"}
    actual = set(columns or [])
    missing = expected - actual
    return {
        "schema_ok": len(missing) == 0,
        "missing_columns": list(missing),
        "checked_rows": rows,
    }


@step(name="compute_stats", dependencies=["collect_data"])
def compute_stats(rows: int = 0) -> dict:
    """Calcule des statistiques descriptives sur le dataset (parallèle)."""
    time.sleep(0.06)
    return {
        "row_count": rows,
        "null_rate": round(random.uniform(0.0, 0.05), 4),
        "duplicate_rate": round(random.uniform(0.0, 0.02), 4),
        "score_mean": round(random.uniform(60.0, 90.0), 2),
        "score_std": round(random.uniform(5.0, 20.0), 2),
    }


@step(
    name="generate_report",
    dependencies=["validate_schema", "compute_stats"],
)
def generate_report(
    schema_ok: bool = False,
    missing_columns: list | None = None,
    row_count: int = 0,
    null_rate: float = 0.0,
    duplicate_rate: float = 0.0,
    score_mean: float = 0.0,
) -> dict:
    """Consolide les résultats et produit le rapport d'audit."""
    time.sleep(0.03)
    quality_score = 100.0
    issues = []
    if not schema_ok:
        quality_score -= 40
        issues.append(f"Schema invalide — colonnes manquantes : {missing_columns}")
    if null_rate > 0.03:
        quality_score -= 20
        issues.append(f"Taux de nulls élevé : {null_rate:.1%}")
    if duplicate_rate > 0.01:
        quality_score -= 10
        issues.append(f"Doublons détectés : {duplicate_rate:.1%}")
    grade = "A" if quality_score >= 90 else "B" if quality_score >= 75 else "C"
    return {
        "quality_score": round(quality_score, 1),
        "grade": grade,
        "row_count": row_count,
        "score_mean": score_mean,
        "issues": issues,
        "report_url": f"s3://demo-reports/audit-{random.randint(1000, 9999)}.html",
    }


@job(
    name="data_quality_audit",
    version="1.0.0",
    description=(
        "Audit de qualité d'un dataset : collecte → validation du schéma "
        "(retry ×2) ‖ statistiques descriptives → rapport consolidé. "
        "Illustre les décorateurs @step / @job avec dépendances et injection."
    ),
    steps=[collect_data, validate_schema, compute_stats, generate_report],
)
def data_quality_audit_workflow():
    """Déclaration du pipeline — le corps n'est pas exécuté par build()."""
    collect_data()
    validate_schema()
    compute_stats()
    generate_report()


# ── Steps : pipeline "Notification Dispatch" ─────────────────────────────────


@step(name="load_subscribers")
def load_subscribers() -> dict:
    """Charge la liste des abonnés depuis le CRM."""
    time.sleep(0.03)
    count = random.randint(200, 500)
    return {"subscribers": count, "segments": ["premium", "standard", "trial"]}


@step(name="render_template", dependencies=["load_subscribers"])
def render_template(subscribers: int = 0) -> dict:
    """Génère le contenu HTML personnalisé pour chaque segment."""
    time.sleep(0.05)
    return {
        "templates_rendered": 3,
        "total_recipients": subscribers,
        "subject": "Votre résumé hebdomadaire PyWorkflow",
    }


@step(
    name="send_emails",
    dependencies=["render_template"],
    retry_count=3,
    retry_delay=1.0,
    timeout=30.0,
)
def send_emails(total_recipients: int = 0, templates_rendered: int = 0) -> dict:
    """Envoie les emails via le provider SMTP — retry ×3, timeout 30 s."""
    time.sleep(0.08)
    sent = int(total_recipients * random.uniform(0.97, 1.0))
    return {
        "sent": sent,
        "failed": total_recipients - sent,
        "provider": "sendgrid",
        "message_id": f"msg-{random.randint(10000, 99999)}",
    }


@step(name="record_metrics", dependencies=["send_emails"])
def record_metrics(sent: int = 0, failed: int = 0) -> dict:
    """Enregistre les métriques d'envoi dans le système de monitoring."""
    time.sleep(0.02)
    return {
        "delivery_rate": round(sent / max(sent + failed, 1), 4),
        "recorded": True,
        "dashboard": "https://metrics.demo/notifications",
    }


@job(
    name="notification_dispatch",
    version="1.0.0",
    description=(
        "Envoi de notifications hebdomadaires : chargement abonnés → rendu template "
        "→ envoi SMTP (retry ×3, timeout 30 s) → enregistrement métriques. "
        "Démontre @step avec timeout et retry élevé."
    ),
    steps=[load_subscribers, render_template, send_emails, record_metrics],
)
def notification_dispatch_workflow():
    load_subscribers()
    render_template()
    send_emails()
    record_metrics()


# ── Engine + seed ─────────────────────────────────────────────────────────────


def _build_engine() -> WorkflowEngine:
    persistence = SQLitePersistence(database_path=_DB_PATH)
    eng = WorkflowEngine(persistence=persistence)

    audit_job = data_quality_audit_workflow.build()
    notif_job = notification_dispatch_workflow.build()

    eng.save_job(audit_job)
    print(f"  [decorator_demo] Registered: {audit_job.name!r}")

    eng.save_job(notif_job)
    print(f"  [decorator_demo] Registered: {notif_job.name!r}")

    existing = eng.list_job_runs(limit=1)
    if not existing:
        print("  [decorator_demo] Seeding demo runs …")
        for _ in range(2):
            eng.run_with_persistence(audit_job)
        eng.run_with_persistence(notif_job)
        print("  [decorator_demo] Seeding complete.")
    else:
        print(f"  [decorator_demo] Existing runs in {_DB_PATH!r} — skipping seed.")

    return eng


print(f"[decorator_demo] Connecting to {_DB_PATH}")
engine = _build_engine()
print("[decorator_demo] Done.\n")


# ── Point d'entrée autonome ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("Jobs enregistrés dans workflow.db.")
    print("La GUI affichera les nouveaux jobs au prochain refresh (3 s).")
    print()
    print("Pour lancer la GUI avec le bouton 'Lancer' actif :")
    print("  pyworkflow --app examples.gui_decorator_demo:engine gui")
