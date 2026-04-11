"""
Démo GUI — jobs définis avec les décorateurs @step / @job + logging SQLite.

Pipelines :
  data_quality_audit   : collect → (validate_schema ‖ compute_stats) → report
  notification_dispatch: subscribers → template → send (retry×3) → metrics

Les logs de chaque step sont persistés dans la table ``workflow_logs``
de ``workflow.db`` via ``SQLiteLogHandler``.

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

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.config.settings import settings
from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

# ── Surcharge des settings pour cet exemple ──────────────────────────────────
settings.configure(
    DATABASE="workflow.db",
    LOGGING_LEVEL="DEBUG",
    LOGGING_DIR="logs",
    LOGGING_TO_DB=True,
)

# Logger partagé pour tous les steps de ce module
logger = get_logger("demo.decorator")


# ── Steps : pipeline "Data Quality Audit" ────────────────────────────────────


@step(name="collect_data")
def collect_data() -> dict:
    """Simule la collecte d'un dataset depuis une source externe."""
    logger.info("Démarrage de la collecte de données")
    time.sleep(0.05)
    n = random.randint(800, 1200)
    result = {
        "rows": n,
        "columns": ["id", "name", "score", "created_at", "status"],
        "source": "postgres://demo/events",
    }
    logger.info("Collecte terminée", extra={"rows": n, "source": result["source"]})
    return result


@step(
    name="validate_schema",
    dependencies=["collect_data"],
    retry_count=2,
    retry_delay=0.5,
)
def validate_schema(rows: int = 0, columns: list | None = None) -> dict:
    """Vérifie le schéma attendu — retry x2 en cas d'échec transitoire."""
    logger.info("Validation du schéma sur %d lignes", rows)
    time.sleep(0.04)
    expected = {"id", "name", "score", "created_at", "status"}
    actual = set(columns or [])
    missing = expected - actual
    if missing:
        logger.warning("Colonnes manquantes détectées", extra={"missing": list(missing)})
    else:
        logger.info("Schéma valide — toutes les colonnes présentes")
    return {
        "schema_ok": len(missing) == 0,
        "missing_columns": list(missing),
        "checked_rows": rows,
    }


@step(name="compute_stats", dependencies=["collect_data"])
def compute_stats(rows: int = 0) -> dict:
    """Calcule des statistiques descriptives (step parallèle à validate_schema)."""
    logger.info("Calcul des statistiques sur %d lignes", rows)
    time.sleep(0.06)
    null_rate = round(random.uniform(0.0, 0.05), 4)
    dup_rate = round(random.uniform(0.0, 0.02), 4)
    if null_rate > 0.03:
        logger.warning("Taux de nulls élevé", extra={"null_rate": null_rate})
    if dup_rate > 0.01:
        logger.warning("Doublons détectés", extra={"duplicate_rate": dup_rate})
    result = {
        "row_count": rows,
        "null_rate": null_rate,
        "duplicate_rate": dup_rate,
        "score_mean": round(random.uniform(60.0, 90.0), 2),
        "score_std": round(random.uniform(5.0, 20.0), 2),
    }
    logger.debug("Statistiques calculées", extra=result)
    return result


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
    logger.info("Génération du rapport d'audit")
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
    report_url = f"s3://demo-reports/audit-{random.randint(1000, 9999)}.html"
    logger.info(
        "Rapport généré",
        extra={"grade": grade, "quality_score": quality_score, "report_url": report_url},
    )
    if issues:
        logger.warning("Problèmes détectés dans le dataset", extra={"issues": issues})
    return {
        "quality_score": round(quality_score, 1),
        "grade": grade,
        "row_count": row_count,
        "score_mean": score_mean,
        "issues": issues,
        "report_url": report_url,
    }


@job(
    name="data_quality_audit",
    version="1.0.0",
    description=(
        "Audit de qualité d'un dataset : collecte → validation du schéma "
        "(retry ×2) ‖ statistiques descriptives → rapport consolidé. "
        "Illustre les décorateurs @step / @job avec dépendances, injection et logging."
    ),
    steps=[collect_data, validate_schema, compute_stats, generate_report],
)
def data_quality_audit_workflow():
    collect_data()
    validate_schema()
    compute_stats()
    generate_report()


# ── Steps : pipeline "Notification Dispatch" ─────────────────────────────────


@step(name="load_subscribers")
def load_subscribers() -> dict:
    """Charge la liste des abonnés depuis le CRM."""
    logger.info("Chargement des abonnés depuis le CRM")
    time.sleep(0.03)
    count = random.randint(200, 500)
    segments = ["premium", "standard", "trial"]
    logger.info("Abonnés chargés", extra={"count": count, "segments": segments})
    return {"subscribers": count, "segments": segments}


@step(name="render_template", dependencies=["load_subscribers"])
def render_template(subscribers: int = 0) -> dict:
    """Génère le contenu HTML personnalisé pour chaque segment."""
    logger.info("Rendu des templates pour %d destinataires", subscribers)
    time.sleep(0.05)
    result = {
        "templates_rendered": 3,
        "total_recipients": subscribers,
        "subject": "Votre résumé hebdomadaire PyWorkflow",
    }
    logger.debug("Templates rendus", extra=result)
    return result


@step(
    name="send_emails",
    dependencies=["render_template"],
    retry_count=3,
    retry_delay=1.0,
    timeout=30.0,
)
def send_emails(total_recipients: int = 0, templates_rendered: int = 0) -> dict:
    """Envoie les emails via le provider SMTP — retry ×3, timeout 30 s."""
    logger.info("Envoi de %d emails via SendGrid", total_recipients)
    time.sleep(0.08)
    sent = int(total_recipients * random.uniform(0.97, 1.0))
    failed = total_recipients - sent
    if failed > 0:
        logger.warning("Échecs d'envoi détectés", extra={"sent": sent, "failed": failed})
    else:
        logger.info("Tous les emails envoyés avec succès", extra={"sent": sent})
    return {
        "sent": sent,
        "failed": failed,
        "provider": "sendgrid",
        "message_id": f"msg-{random.randint(10000, 99999)}",
    }


@step(name="record_metrics", dependencies=["send_emails"])
def record_metrics(sent: int = 0, failed: int = 0) -> dict:
    """Enregistre les métriques d'envoi dans le système de monitoring."""
    delivery_rate = round(sent / max(sent + failed, 1), 4)
    logger.info(
        "Métriques enregistrées",
        extra={"sent": sent, "failed": failed, "delivery_rate": delivery_rate},
    )
    time.sleep(0.02)
    return {
        "delivery_rate": delivery_rate,
        "recorded": True,
        "dashboard": "https://metrics.demo/notifications",
    }


@job(
    name="notification_dispatch",
    version="1.0.0",
    description=(
        "Envoi de notifications hebdomadaires : chargement abonnés → rendu template "
        "→ envoi SMTP (retry ×3, timeout 30 s) → enregistrement métriques. "
        "Démontre @step avec timeout, retry élevé et logging structuré."
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
    eng = WorkflowEngine(config=settings.workflow_config)

    audit_job = data_quality_audit_workflow.build()
    notif_job = notification_dispatch_workflow.build()

    eng.save_job(audit_job)
    logger.info("Job enregistré", extra={"job": audit_job.name})
    print(f"  [decorator_demo] Registered: {audit_job.name!r}")

    eng.save_job(notif_job)
    logger.info("Job enregistré", extra={"job": notif_job.name})
    print(f"  [decorator_demo] Registered: {notif_job.name!r}")

    existing_audit = eng.list_job_runs(job_name=audit_job.name, limit=1)
    if not existing_audit:
        print("  [decorator_demo] Seeding demo runs …")
        for _ in range(2):
            eng.run_with_storage(audit_job)
        eng.run_with_storage(notif_job)
        print("  [decorator_demo] Seeding complete.")
    else:
        print(f"  [decorator_demo] Runs already exist for {audit_job.name!r} — skipping seed.")

    return eng


print(f"[decorator_demo] Connecting to {settings.DATABASE}")
engine = _build_engine()
print("[decorator_demo] Done.\n")


# ── Point d'entrée autonome ───────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Jobs enregistrés dans {settings.DATABASE}.")
    print(f"Logs disponibles dans la table 'workflow_logs' de {settings.DATABASE}.")
    print()
    print("Interroger les logs (sqlite3) :")
    print("  sqlite3 workflow.db 'SELECT timestamp,level,logger,message FROM workflow_logs ORDER BY id DESC LIMIT 20;'")
    print()
    print("Pour lancer la GUI avec le bouton 'Lancer' actif :")
    print("  pyworkflow --app examples.gui_decorator_demo:engine gui")
