"""
Exemple v0.4.0 : Triggers — ManualTrigger et ScheduleTrigger

Démontre les trois points d'entrée du système de triggers :

1. ManualTrigger      — déclenchement explicite par code (API, bouton, test)
2. ScheduleTrigger    — déclenchement par expression cron (stdlib, sans Celery)
3. CronExpression     — parser cron standalone (utile pour les tests de planning)

Structure du job utilisé dans les exemples :
    fetch_data → compute_metrics → send_report
"""

import time
from datetime import datetime

from pyworkflow_engine import (
    WorkflowEngine, Job, Step, StepType, WorkflowContext,
    ManualTrigger, ScheduleTrigger, CronExpression,
)
from pyworkflow_engine.triggers import TriggerState


# ---------------------------------------------------------------------------
# Job léger utilisé par tous les exemples
# ---------------------------------------------------------------------------

def fetch_data(context: WorkflowContext) -> dict:
    ts = context.get("triggered_at", "N/A")
    print(f"    [fetch_data] triggered_at={ts}")
    return {"records": 42, "triggered_at": ts}


def compute_metrics(context: WorkflowContext) -> dict:
    data = context.get_step_output("fetch_data")
    metrics = {"avg": data["records"] / 2.0, "total": data["records"]}
    print(f"    [compute_metrics] avg={metrics['avg']}, total={metrics['total']}")
    return metrics


def send_report(context: WorkflowContext) -> dict:
    metrics = context.get_step_output("compute_metrics")
    print(f"    [send_report] Rapport envoyé — avg={metrics['avg']}")
    return {"sent": True}


def build_job() -> Job:
    return Job(
        name="Daily Report",
        steps=[
            Step(name="fetch_data",       step_type=StepType.FUNCTION, handler=fetch_data),
            Step(name="compute_metrics",  step_type=StepType.FUNCTION, handler=compute_metrics,
                 dependencies=["fetch_data"]),
            Step(name="send_report",      step_type=StepType.FUNCTION, handler=send_report,
                 dependencies=["compute_metrics"]),
        ],
    )


# ---------------------------------------------------------------------------
# 1. ManualTrigger
# ---------------------------------------------------------------------------

def demo_manual_trigger():
    """ManualTrigger : déclenchement explicite, sans automatisation."""
    print("=" * 60)
    print("1. ManualTrigger")
    print("=" * 60)

    engine = WorkflowEngine()
    job = build_job()

    runs = []
    trigger = ManualTrigger(
        engine=engine,
        name="api-trigger",
        on_run_complete=lambda run: runs.append(run),
    )

    trigger.start()
    print(f"  État : {trigger.state.value}")

    # Premier déclenchement — contexte initial personnalisé
    print("\n  Déclenchement #1 (contexte initial : env=prod)")
    job_run = trigger.fire(job, initial_context={"triggered_at": "2026-04-11T09:00:00", "env": "prod"})
    print(f"  → Statut : {job_run.status.value}, run_count={trigger.run_count}")

    # Deuxième déclenchement — contexte différent
    print("\n  Déclenchement #2 (contexte initial : env=staging)")
    job_run2 = trigger.fire(job, initial_context={"triggered_at": "2026-04-11T09:05:00", "env": "staging"})
    print(f"  → Statut : {job_run2.status.value}, run_count={trigger.run_count}")

    trigger.stop()
    print(f"\n  État final : {trigger.state.value}")
    print(f"  Total exécutions : {trigger.run_count}")

    # Vérification que fire() échoue après stop()
    try:
        trigger.fire(job)
    except RuntimeError as e:
        print(f"  fire() après stop() → RuntimeError attendue : {e}")


# ---------------------------------------------------------------------------
# 2. CronExpression — tests du parser
# ---------------------------------------------------------------------------

def demo_cron_expression():
    """CronExpression : parser cron standalone."""
    print("\n" + "=" * 60)
    print("2. CronExpression — tests du parser cron")
    print("=" * 60)

    cases = [
        ("* * * * *",   "toutes les minutes"),
        ("0 * * * *",   "toutes les heures à :00"),
        ("0 9 * * 1-5", "9h00 lun-ven"),
        ("*/15 * * * *", "toutes les 15 min"),
        ("30 6 1,15 * *", "6h30 le 1er et le 15"),
        ("0 0 * * 0",    "minuit le dimanche"),
    ]

    print(f"  {'Expression':<22} {'Description':<30} {'Correspond à maintenant ?'}")
    print(f"  {'-'*22} {'-'*30} {'-'*25}")
    now = datetime.now()
    for expr, desc in cases:
        cron = CronExpression(expr)
        matches = cron.matches(now)
        mark = "✓" if matches else "·"
        print(f"  {expr:<22} {desc:<30} {mark}  ({now.strftime('%H:%M %a')})")

    # Vérification d'expression invalide
    print()
    try:
        CronExpression("* * * *")  # seulement 4 champs
    except ValueError as e:
        print(f"  Expression invalide détectée → ValueError : {e}")


# ---------------------------------------------------------------------------
# 3. ScheduleTrigger — déclenchement automatique
# ---------------------------------------------------------------------------

def demo_schedule_trigger():
    """ScheduleTrigger : déclenchement par cron, thread d'arrière-plan."""
    print("\n" + "=" * 60)
    print("3. ScheduleTrigger — déclenchement automatique")
    print("=" * 60)

    engine = WorkflowEngine()
    job = build_job()
    fired_runs = []

    # Utilise "* * * * *" pour déclencher à chaque minute correspondante.
    # Dans ce démo on laisse le trigger tourner 65 secondes pour observer
    # au moins un déclenchement naturel si on est en début de minute.
    # Pour rester rapide, on appelle aussi fire() manuellement.
    trigger = ScheduleTrigger(
        engine=engine,
        job=job,
        cron="* * * * *",  # toutes les minutes
        name="every-minute-demo",
        initial_context_factory=lambda: {
            "triggered_at": datetime.now().isoformat(),
            "source": "schedule",
        },
        on_run_complete=lambda run: fired_runs.append(run),
    )

    print(f"  Expression cron : {trigger.cron.expression}")
    print(f"  État initial    : {trigger.state.value}")

    trigger.start()
    # Le thread démarre immédiatement : avec "* * * * *" il tire dans les
    # premières millisecondes. On attend qu'il ait terminé son premier cycle
    # avant d'afficher l'état, pour un output lisible.
    time.sleep(0.2)
    print(f"  État après start() : {trigger.state.value}")
    assert trigger.state == TriggerState.RUNNING

    # --- Déclenchement manuel direct (sans attendre la prochaine minute) ---
    print("\n  Déclenchement manuel via trigger.fire() :")
    job_run = trigger.fire()
    fired_runs.append(job_run)
    print(f"  → Statut : {job_run.status.value}")

    # --- Laisser le thread tourner 2 secondes (ne se déclenchera pas
    #     automatiquement : la même minute est déjà marquée comme traitée) ---
    print("\n  Le thread tourne en arrière-plan (2 s)...")
    time.sleep(2)
    print(f"  run_count (via fire manuel) : {trigger.run_count}")

    trigger.stop(timeout=3.0)
    print(f"  État après stop() : {trigger.state.value}")

    # --- Vérification ---
    assert trigger.state == TriggerState.STOPPED
    assert len(fired_runs) >= 1
    last = fired_runs[-1]
    print(f"\n  Dernière exécution : statut={last.status.value}, "
          f"steps={len(last.step_runs)}")


# ---------------------------------------------------------------------------
# 4. ScheduleTrigger — démonstration avec callback d'erreur
# ---------------------------------------------------------------------------

def demo_schedule_error_callback():
    """Montre comment capturer les erreurs d'exécution via on_run_error."""
    print("\n" + "=" * 60)
    print("4. ScheduleTrigger — callback on_run_error")
    print("=" * 60)

    def failing_step() -> dict:
        raise RuntimeError("Simulated failure in scheduled job")

    engine = WorkflowEngine()
    bad_job = Job(
        name="Fragile Job",
        steps=[Step(name="boom", step_type=StepType.FUNCTION, handler=failing_step)],
    )

    errors_caught = []

    trigger = ScheduleTrigger(
        engine=engine,
        job=bad_job,
        cron="* * * * *",
        name="fragile-trigger",
        on_run_error=lambda exc: errors_caught.append(exc),
    )
    # Ne PAS démarrer le thread ici — on veut contrôler précisément combien
    # de fois fire() est appelé. On appelle fire() directement (hors thread).

    print("  Déclenchement #1 — appel direct trigger.fire() :")
    try:
        trigger.fire()
    except Exception as exc:
        print(f"  Exception propagée : {type(exc).__name__}")

    print(f"  on_run_error appelé : {len(errors_caught)} fois")

    print("\n  Déclenchement #2 — deuxième appel fire() :")
    try:
        trigger.fire()
    except Exception as exc:
        print(f"  Exception propagée : {type(exc).__name__}")

    print(f"  on_run_error appelé : {len(errors_caught)} fois (cumulé)")
    print(f"  Message : {type(errors_caught[0]).__name__}: {errors_caught[0]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("PyWorkflow Engine v0.4.0 — Triggers\n")

    demo_manual_trigger()
    demo_cron_expression()
    demo_schedule_trigger()
    demo_schedule_error_callback()

    print("\nTous les exemples triggers ont été exécutés avec succès.")


if __name__ == "__main__":
    main()
