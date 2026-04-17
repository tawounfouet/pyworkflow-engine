# filepath: jobs/ops/heartbeat_email.py
"""
Ops — Heartbeat e-mail toutes les 5 minutes (job de test scheduling).

Ce job sert à **valider le fonctionnement du ScheduleTrigger** :
il envoie un e-mail de test toutes les 5 minutes via SMTP et log
un heartbeat dans le système.

Pipeline :
    collect_metrics   (stats système : heure, PID, mémoire RSS)
        ↓
    send_heartbeat_email   (e-mail SMTP via pyconnectors)
        ↓
    log_heartbeat          (enregistre le heartbeat dans les logs)

Variables d'environnement (depuis .env ou env système) :
    SMTP_HOST         : Serveur SMTP (ex. smtp.gmail.com)
    SMTP_PORT         : Port SMTP (défaut : 465)
    SMTP_USER         : Adresse e-mail expéditeur
    SMTP_PASSWORD     : Mot de passe / app password
    SMTP_USE_SSL      : "true" / "false" (défaut : "true")
    NOTIFY_EMAIL      : Adresse destinataire (défaut : SMTP_USER)

Usage CLI (test manuel) :
    python -m jobs.ops.heartbeat_email
    python -m jobs.ops.heartbeat_email --dry-run
    python -m jobs.ops.heartbeat_email --run-scheduler   # boucle infinie 5min
"""

from __future__ import annotations

import os
from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.ops.heartbeat")

# ─── Compteur global pour l'affichage du numéro de run ───────────────────────
_run_counter: list[int] = [0]


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="collect_metrics", timeout=10.0)
def collect_metrics(triggered_at: str = "") -> dict[str, Any]:
    """Collecte les métriques système au moment du déclenchement.

    Args:
        triggered_at: Timestamp d'injection via ``initial_context_factory``.

    Returns:
        ``{"triggered_at": str, "pid": int, "memory_rss_mb": float,
           "run_number": int, "hostname": str}``
    """
    import os  # noqa: PLC0415
    import socket  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    _run_counter[0] += 1
    run_number = _run_counter[0]

    now = triggered_at or datetime.now(UTC).isoformat()
    pid = os.getpid()
    hostname = socket.gethostname()

    # Mémoire RSS (optionnel — ignore si resource non dispo sur Windows)
    memory_rss_mb: float = 0.0
    try:
        import resource  # noqa: PLC0415

        memory_rss_mb = round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 2
        )
    except ImportError:
        pass

    _logger.info(
        "📊 collect_metrics — run #%d | pid=%d | host=%s | rss=%.1f MB",
        run_number,
        pid,
        hostname,
        memory_rss_mb,
    )
    return {
        "triggered_at": now,
        "pid": pid,
        "hostname": hostname,
        "memory_rss_mb": memory_rss_mb,
        "run_number": run_number,
    }


@step(
    name="send_heartbeat_email",
    dependencies=["collect_metrics"],
    retry_count=2,
    retry_delay=3.0,
    timeout=30.0,
)
def send_heartbeat_email(
    triggered_at: str = "",
    pid: int = 0,
    hostname: str = "",
    memory_rss_mb: float = 0.0,
    run_number: int = 0,
) -> dict[str, Any]:
    """Envoie un e-mail de heartbeat via SMTP.

    Les variables d'env SMTP_* sont requises. Si ``NOTIFY_EMAIL`` n'est pas
    défini, utilise ``SMTP_USER`` comme destinataire.

    Args:
        triggered_at:   Timestamp injecté depuis ``collect_metrics``.
        pid:            PID du processus.
        hostname:       Nom de la machine.
        memory_rss_mb:  Mémoire RSS en Mo.
        run_number:     Numéro de run incrémental.

    Returns:
        ``{"status": "sent"|"skipped", "to": str, "subject": str}``
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")

    # Pas de config SMTP → on skip l'envoi (mode dev sans .env)
    if not smtp_host or not smtp_user or not smtp_password:
        _logger.warning(
            "⚠️  send_heartbeat_email — SMTP non configuré (SMTP_HOST/USER/PASSWORD manquants)."
            " Email non envoyé.",
        )
        return {"status": "skipped", "to": "", "subject": "", "run_number": run_number}

    from pyconnectors.config import ConnectorConfig  # noqa: PLC0415
    from pyconnectors.services.factory import ConnectorFactory  # noqa: PLC0415

    to_addr = os.environ.get("NOTIFY_EMAIL", smtp_user)
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    use_ssl = os.environ.get("SMTP_USE_SSL", "true").lower() == "true"

    subject = f"[Heartbeat #{run_number}] PyWorkflow ✅ — {triggered_at[:19]}"

    separator = "─" * 50
    body = (
        f"Heartbeat PyWorkflow Engine\n"
        f"{separator}\n"
        f"\n"
        f"  Run n°       : {run_number}\n"
        f"  Déclenché à  : {triggered_at}\n"
        f"  Hostname     : {hostname}\n"
        f"  PID          : {pid}\n"
        f"  Mémoire RSS  : {memory_rss_mb:.1f} Mo\n"
        f"\n"
        f"{separator}\n"
        f"Job    : ops-heartbeat-email\n"
        f"Cron   : */5 * * * * (toutes les 5 minutes)\n"
        f"Engine : PyWorkflow Engine\n"
    )

    smtp_config = ConnectorConfig(
        params={
            "host": smtp_host,
            "port": smtp_port,
            "user": smtp_user,
            "password": smtp_password,
            "from_addr": smtp_user,
            "use_ssl": use_ssl,
        }
    )

    connector = ConnectorFactory.create("email.smtp", config=smtp_config)
    result = connector.safe_execute(
        to_addr=to_addr, subject=subject, body=body, html=False
    )

    if not result.success:
        _logger.error("✗ send_heartbeat_email — échec envoi : %s", result.error)
        raise RuntimeError(f"SMTP send failed: {result.error}")

    _logger.success(  # type: ignore[attr-defined]
        "✅ send_heartbeat_email — envoyé à %s (run #%d)", to_addr, run_number
    )
    return {
        "status": "sent",
        "to": to_addr,
        "subject": subject,
        "run_number": run_number,
    }


@step(
    name="log_heartbeat",
    dependencies=["send_heartbeat_email"],
)
def log_heartbeat(
    triggered_at: str = "",
    run_number: int = 0,
    status: str = "skipped",
    to: str = "",
) -> dict[str, Any]:
    """Enregistre le résultat du heartbeat dans les logs.

    Args:
        triggered_at: Timestamp depuis ``collect_metrics``.
        run_number:   Numéro de run depuis ``collect_metrics``.
        status:       ``"sent"`` ou ``"skipped"`` depuis ``send_heartbeat_email``.
        to:           Destinataire depuis ``send_heartbeat_email``.

    Returns:
        ``{"run_number": int, "email_status": str, "logged_at": str}``
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    logged_at = datetime.now(UTC).isoformat()
    icon = "📧" if status == "sent" else "🔕"

    _logger.info(
        "%s log_heartbeat — run #%d | triggered=%s | email=%s | to=%s",
        icon,
        run_number,
        triggered_at[:19] if triggered_at else "N/A",
        status,
        to or "N/A",
    )
    return {
        "run_number": run_number,
        "email_status": status,
        "logged_at": logged_at,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="ops-heartbeat-email",
    version="1.0.0",
    description=(
        "Job de test scheduling — envoie un e-mail de heartbeat toutes les 5 minutes. "
        "Valide le bon fonctionnement du ScheduleTrigger et de la stack SMTP. "
        "Pipeline : collect_metrics → send_heartbeat_email → log_heartbeat."
    ),
    tags=["ops", "heartbeat", "email", "scheduling", "test"],
    steps=[collect_metrics, send_heartbeat_email, log_heartbeat],
)
def heartbeat_email_job() -> None:
    """Déclaration du job — le corps n'est pas exécuté par ``build()``."""
    collect_metrics()
    send_heartbeat_email()
    log_heartbeat()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse  # noqa: PLC0415
    import time  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    from dotenv import load_dotenv  # noqa: PLC0415
    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.triggers.schedule import (
        ScheduleTrigger,
    )  # noqa: PLC0415

    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415

    load_dotenv()
    configure_platform_logging()

    parser = argparse.ArgumentParser(
        description="Heartbeat e-mail — job de test scheduling (toutes les 5 min)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exécute le job une seule fois immédiatement, sans boucle scheduler.",
    )
    parser.add_argument(
        "--run-scheduler",
        action="store_true",
        help="Démarre le ScheduleTrigger en boucle infinie (Ctrl+C pour arrêter).",
    )
    parser.add_argument(
        "--detach",
        action="store_true",
        help="Lance le scheduler en arrière-plan (détaché). Écrit le PID dans logs/heartbeat.pid.",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Arrête le scheduler détaché en lisant logs/heartbeat.pid.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Affiche l'état du scheduler détaché (running / stopped).",
    )
    args = parser.parse_args()

    engine = WorkflowEngine()
    job = heartbeat_email_job.build()

    # ── Helpers PID file ──────────────────────────────────────────────────
    import os as _os  # noqa: PLC0415
    import signal  # noqa: PLC0415

    _PID_FILE = _os.path.join(_os.path.dirname(__file__), "../../logs/heartbeat.pid")
    _PID_FILE = _os.path.normpath(_PID_FILE)
    _LOG_FILE = _os.path.join(_os.path.dirname(__file__), "../../logs/heartbeat.log")
    _LOG_FILE = _os.path.normpath(_LOG_FILE)

    def _read_pid() -> int | None:
        try:
            return int(open(_PID_FILE).read().strip())
        except (FileNotFoundError, ValueError):
            return None

    def _is_running(pid: int) -> bool:
        try:
            _os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    # ── Mode --status ─────────────────────────────────────────────────────
    if args.status:
        pid = _read_pid()
        if pid and _is_running(pid):
            print(f"🟢 Scheduler en cours — PID {pid}")
            print(f"   Logs : {_LOG_FILE}")
        else:
            print("🔴 Scheduler arrêté (aucun PID actif)")
        raise SystemExit(0)

    # ── Mode --stop ───────────────────────────────────────────────────────
    if args.stop:
        pid = _read_pid()
        if not pid:
            print("⚠️  Aucun PID trouvé — scheduler déjà arrêté ?")
            raise SystemExit(1)
        if not _is_running(pid):
            print(f"⚠️  PID {pid} introuvable — processus déjà terminé.")
            _os.remove(_PID_FILE)
            raise SystemExit(0)
        _os.kill(pid, signal.SIGTERM)
        print(f"⏹  Signal SIGTERM envoyé au PID {pid}.")
        _os.remove(_PID_FILE)
        raise SystemExit(0)

    # ── Mode --detach ─────────────────────────────────────────────────────
    if args.detach:
        pid = _read_pid()
        if pid and _is_running(pid):
            print(f"⚠️  Scheduler déjà actif — PID {pid}")
            print(f"   Utilisez --stop pour l'arrêter.")
            raise SystemExit(1)

        # Fork : le processus parent s'arrête, l'enfant continue
        child_pid = _os.fork()
        if child_pid > 0:
            # ── Processus parent ──
            with open(_PID_FILE, "w") as f:
                f.write(str(child_pid))
            print(f"🚀 Scheduler lancé en arrière-plan — PID {child_pid}")
            print(f"   Logs   : {_LOG_FILE}")
            print(f"   Arrêt  : python -m jobs.ops.heartbeat_email --stop")
            print(f"   État   : python -m jobs.ops.heartbeat_email --status")
            raise SystemExit(0)

        # ── Processus enfant — détachement complet ──
        _os.setsid()
        import sys  # noqa: PLC0415

        log_fd = open(_LOG_FILE, "a", buffering=1)
        sys.stdout = log_fd
        sys.stderr = log_fd
        # Reconfigurer le logging vers le fichier log
        import logging  # noqa: PLC0415

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.basicConfig(
            stream=log_fd,
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(name)-36s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        # Continuer comme --run-scheduler (fall-through ci-dessous)
        args.run_scheduler = True

    # ── Mode dry-run : une seule exécution immédiate ──────────────────────
    if args.dry_run:
        print("🔍 Dry-run — exécution unique du job heartbeat_email")
        result = engine.run(
            job,
            initial_context={"triggered_at": datetime.now(UTC).isoformat()},
        )
        print(f"\nStatut : {result.status}")
        for step_run in result.step_runs:
            icon = "✅" if str(step_run.status).endswith("SUCCESS") else "❌"
            print(f"  {icon} {step_run.step_name:<25} → {step_run.status}")
        raise SystemExit(0)

    # ── Mode scheduler : ScheduleTrigger en boucle infinie ────────────────
    if args.run_scheduler:
        print("🕐 Démarrage du ScheduleTrigger — cron '*/5 * * * *'")
        print("   Ctrl+C pour arrêter proprement.\n")

        trigger = ScheduleTrigger(
            engine=engine,
            job=job,
            cron="*/5 * * * *",  # toutes les 5 minutes
            name="heartbeat-5min",
            timezone_aware=True,  # timestamps UTC
            initial_context_factory=lambda: {
                "triggered_at": datetime.now(UTC).isoformat(),
            },
            on_run_complete=lambda run: _logger.info(
                "✅ Run terminé — statut=%s | steps=%d",
                run.status,
                len(run.step_runs),
            ),
            on_run_error=lambda exc: _logger.error("❌ Erreur scheduler : %s", exc),
        )

        trigger.start()
        print(f"Trigger state  : {trigger.state.value}")
        print(f"Cron           : {trigger.cron.expression}")
        print(f"Prochain fire  : à la prochaine minute en */5\n")

        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n⏹  Arrêt demandé...")
        finally:
            trigger.stop(timeout=10.0)
            print(f"Trigger arrêté — {trigger.run_count} run(s) exécuté(s).")
        raise SystemExit(0)

    # ── Par défaut : exécution unique (même que --dry-run) ────────────────
    print("💡 Astuce : utilisez --dry-run ou --run-scheduler")
    print("   python -m jobs.ops.heartbeat_email --dry-run")
    print("   python -m jobs.ops.heartbeat_email --run-scheduler\n")

    result = engine.run(
        job,
        initial_context={"triggered_at": datetime.now(UTC).isoformat()},
    )
    print(f"Statut : {result.status}")
    for step_run in result.step_runs:
        icon = "✅" if str(step_run.status).endswith("SUCCESS") else "❌"
        print(f"  {icon} {step_run.step_name:<25} → {step_run.status}")
