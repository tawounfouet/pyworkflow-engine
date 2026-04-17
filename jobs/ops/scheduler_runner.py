# filepath: jobs/ops/scheduler_runner.py
"""
Ops — Orchestrateur central : démarre un ScheduleTrigger pour chaque job
du manifest qui possède un champ ``schedule``.

C'est le point d'entrée unique pour faire tourner **tous** les jobs
en production. Il lit ``jobs/manifest.yaml``, charge chaque job via
``jobs.shared.loader``, et démarre un ``ScheduleTrigger`` par job schedulé.

Usage :
    python -m jobs.ops.scheduler_runner                         # démarre tout
    python -m jobs.ops.scheduler_runner --dry-run               # liste sans démarrer
    python -m jobs.ops.scheduler_runner --only ingestion-strava,ops-heartbeat-email
    python -m jobs.ops.scheduler_runner --exclude ops-heartbeat-email
    python -m jobs.ops.scheduler_runner --detach                # arrière-plan (fork)
    python -m jobs.ops.scheduler_runner --stop                  # arrête le runner détaché
    python -m jobs.ops.scheduler_runner --status                # état du runner détaché
    python -m jobs.ops.scheduler_runner --disable ops-heartbeat-email  # stoppe un trigger
    python -m jobs.ops.scheduler_runner --enable  ops-heartbeat-email  # réactive un trigger
    python -m jobs.ops.scheduler_runner --reload                # recharge le manifest à chaud
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# ── Chemins ───────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[2]
_LOGS_DIR = _ROOT / "logs"
_PID_FILE = _LOGS_DIR / "scheduler_runner.pid"
_LOG_FILE = _LOGS_DIR / "scheduler_runner.log"
_EXCLUDED_FILE = _LOGS_DIR / "scheduler_runner.excluded"  # liste des jobs désactivés

sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

_LOGS_DIR.mkdir(exist_ok=True)

# ── Logging bootstrap (avant dotenv / engine) ─────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-36s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger("ops.scheduler_runner")


# ── Helpers PID ───────────────────────────────────────────────────────────────


def _read_pid() -> int | None:
    try:
        return int(_PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── Helpers excluded-list ─────────────────────────────────────────────────────


def _read_excluded() -> set[str]:
    """Lit la liste des jobs désactivés depuis le fichier d'état."""
    try:
        return {l.strip() for l in _EXCLUDED_FILE.read_text().splitlines() if l.strip()}
    except FileNotFoundError:
        return set()


def _write_excluded(jobs: set[str]) -> None:
    """Persiste la liste des jobs désactivés."""
    _EXCLUDED_FILE.write_text("\n".join(sorted(jobs)))


# ── Gestionnaire de signaux in-process ───────────────────────────────────────
# Utilisé par --disable / --enable / --reload pour piloter le daemon sans
# le redémarrer.  Le daemon répond à SIGUSR1 (reload/disable/enable) via
# un fichier de commande temporaire logs/scheduler_runner.cmd.

_CMD_FILE = _LOGS_DIR / "scheduler_runner.cmd"

# Registre global des triggers actifs (rempli par _run_loop)
_active_triggers: dict[str, object] = {}


def _install_signal_handler() -> None:
    """Installe le handler SIGUSR1 dans le processus daemon."""

    def _on_sigusr1(signum: int, frame: object) -> None:  # noqa: ARG001
        cmd = ""
        try:
            cmd = _CMD_FILE.read_text().strip()
            _CMD_FILE.unlink(missing_ok=True)
        except OSError:
            return

        verb, _, job_name = cmd.partition(" ")
        verb = verb.lower()

        if verb == "disable" and job_name:
            # Persiste l'exclusion en premier (survit aux redémarrages)
            excluded = _read_excluded()
            excluded.add(job_name)
            _write_excluded(excluded)

            trigger = _active_triggers.get(job_name)
            if trigger is None:
                # Le trigger n'est pas actif dans ce cycle (ex: démarré avec --exclude)
                # L'exclusion est déjà persistée → sera ignoré au prochain démarrage.
                _logger.info(
                    "⏸  '%s' ajouté à la liste d'exclusion "
                    "(non actif dans ce cycle — ignoré au prochain démarrage).",
                    job_name,
                )
                return
            try:
                trigger.stop(timeout=5.0)  # type: ignore[attr-defined]
            except Exception as exc:
                _logger.error("❌ Erreur stop '%s' : %s", job_name, exc)
                return
            _active_triggers.pop(job_name, None)
            _logger.info("⏸  Trigger désactivé à chaud : %s", job_name)

        elif verb == "enable" and job_name:
            excluded = _read_excluded()
            excluded.discard(job_name)
            _write_excluded(excluded)
            # Recharger ce seul job depuis le manifest
            _reload_one(job_name)

        elif verb == "reload":
            _reload_all()

        else:
            _logger.warning("⚠️  SIGUSR1 : commande inconnue : '%s'", cmd)

    signal.signal(signal.SIGUSR1, _on_sigusr1)


def _reload_one(job_name: str) -> None:
    """Charge et démarre un trigger pour un job déjà exclu ou nouveau."""
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(_ROOT / ".env")
    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.triggers.schedule import (
        ScheduleTrigger,
    )  # noqa: PLC0415
    from jobs.shared.loader import (
        load_manifest,
        load_job,
        JobLoadError,
    )  # noqa: PLC0415

    manifest = load_manifest()
    job_def = next(
        (j for j in manifest.get("jobs", []) if j.get("name") == job_name), None
    )
    if job_def is None:
        _logger.warning("⚠️  enable : '%s' introuvable dans le manifest", job_name)
        return

    schedule = job_def.get("schedule")
    if not schedule:
        _logger.warning("⚠️  enable : '%s' n'a pas de schedule", job_name)
        return

    if job_name in _active_triggers:
        _logger.info("ℹ️  enable : '%s' est déjà actif", job_name)
        return

    try:
        job = load_job(job_def)
    except JobLoadError as exc:
        _logger.error("❌ enable : impossible de charger '%s' : %s", job_name, exc)
        return

    engine = WorkflowEngine()
    trigger = ScheduleTrigger(
        engine=engine,
        job=job,
        cron=schedule,
        name=job_name,
        timezone_aware=True,
        initial_context_factory=lambda n=job_name: {
            "triggered_at": datetime.now(UTC).isoformat(),
            "job_name": n,
        },
        on_run_complete=lambda run, n=job_name: _logger.info(
            "✅ [%s] Run terminé — statut=%s", n, run.status
        ),
        on_run_error=lambda exc, n=job_name: _logger.error(
            "❌ [%s] Erreur : %s", n, exc
        ),
    )
    trigger.start()
    _active_triggers[job_name] = trigger
    _logger.info("▶️  Trigger réactivé : %s  cron=%s", job_name, schedule)


def _reload_all() -> None:
    """Arrête tous les triggers et recharge le manifest complet."""
    _logger.info("🔄 Reload demandé — arrêt de %d trigger(s)...", len(_active_triggers))
    for name, trigger in list(_active_triggers.items()):
        try:
            trigger.stop(timeout=5.0)  # type: ignore[attr-defined]
        except Exception:
            pass
    _active_triggers.clear()
    # Recharge en respectant la liste d'exclusion persistée
    excluded = _read_excluded()
    triggers = _build_triggers(only=[], exclude=list(excluded))
    for t in triggers:
        t.start()
        _active_triggers[t.name] = t  # type: ignore[attr-defined]
    _logger.info("🔄 Reload terminé — %d trigger(s) actifs", len(_active_triggers))


def _build_triggers(only: list[str], exclude: list[str]) -> list:
    """Charge les jobs du manifest et crée les ScheduleTriggers."""
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")

    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.adapters.triggers.schedule import ScheduleTrigger
    from jobs.shared.loader import load_manifest, load_job, JobLoadError

    manifest = load_manifest()
    jobs_defs = manifest.get("jobs", [])

    engine = WorkflowEngine()
    triggers: list[ScheduleTrigger] = []
    skipped: list[str] = []
    errors: list[str] = []

    for job_def in jobs_defs:
        name = job_def.get("name", "?")
        schedule = job_def.get("schedule")

        # Filtre --only / --exclude
        if only and name not in only:
            continue
        if name in exclude:
            _logger.info("⏭  Ignoré (--exclude) : %s", name)
            continue

        if not schedule:
            skipped.append(name)
            continue

        # Chargement du Job
        try:
            job = load_job(job_def)
        except JobLoadError as exc:
            _logger.warning("⚠️  Impossible de charger '%s' : %s", name, exc)
            errors.append(name)
            continue

        # Création du trigger
        trigger = ScheduleTrigger(
            engine=engine,
            job=job,
            cron=schedule,
            name=name,
            timezone_aware=True,
            initial_context_factory=lambda n=name: {
                "triggered_at": datetime.now(UTC).isoformat(),
                "job_name": n,
            },
            on_run_complete=lambda run, n=name: _logger.info(
                "✅ [%s] Run terminé — statut=%s", n, run.status
            ),
            on_run_error=lambda exc, n=name: _logger.error(
                "❌ [%s] Erreur : %s", n, exc
            ),
        )
        triggers.append(trigger)
        _logger.info("📅 Enregistré : %-40s cron=%s", name, schedule)

    if skipped:
        _logger.debug("Jobs sans schedule (ignorés) : %s", ", ".join(skipped))
    if errors:
        _logger.warning("Jobs en erreur de chargement : %s", ", ".join(errors))

    return triggers


def _run_loop(triggers: list) -> None:
    """Démarre tous les triggers et attend indéfiniment."""
    _install_signal_handler()

    for trigger in triggers:
        trigger.start()
        _active_triggers[trigger.name] = trigger  # type: ignore[attr-defined]

    _logger.info("🚀 %d scheduler(s) démarré(s). Ctrl+C pour arrêter.", len(triggers))

    try:
        while True:
            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        _logger.info("⏹  Arrêt en cours...")
        for trigger in triggers:
            try:
                trigger.stop(timeout=5.0)
            except Exception:
                pass
        _logger.info("✅ Tous les schedulers arrêtés.")


# ── Entrypoint ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrateur central — démarre tous les jobs schedulés du manifest."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Liste les jobs qui seraient démarrés, sans rien lancer.",
    )
    parser.add_argument(
        "--only",
        default="",
        metavar="JOB1,JOB2",
        help="Ne démarre que ces jobs (noms séparés par virgule).",
    )
    parser.add_argument(
        "--exclude",
        default="",
        metavar="JOB1,JOB2",
        help="Exclut ces jobs (noms séparés par virgule).",
    )
    parser.add_argument(
        "--detach",
        action="store_true",
        help="Lance l'orchestrateur en arrière-plan (fork). PID dans logs/scheduler_runner.pid.",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Arrête l'orchestrateur détaché.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Affiche l'état de l'orchestrateur détaché.",
    )
    parser.add_argument(
        "--disable",
        default="",
        metavar="JOB",
        help="Stoppe un trigger précis sans redémarrer le runner (ex: ops-heartbeat-email).",
    )
    parser.add_argument(
        "--enable",
        default="",
        metavar="JOB",
        help="Réactive un trigger précédemment désactivé via --disable.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Recharge le manifest à chaud (arrêt + redémarrage de tous les triggers).",
    )
    args = parser.parse_args()

    only_list = [j.strip() for j in args.only.split(",") if j.strip()]
    exclude_list = [j.strip() for j in args.exclude.split(",") if j.strip()]

    # ── --status ──────────────────────────────────────────────────────────
    if args.status:
        pid = _read_pid()
        if pid and _is_running(pid):
            excluded = _read_excluded()
            print(f"🟢 Scheduler runner en cours — PID {pid}")
            print(f"   Logs    : {_LOG_FILE}")
            if excluded:
                print(f"   Désactivés : {', '.join(sorted(excluded))}")
        else:
            print("🔴 Scheduler runner arrêté (aucun PID actif)")
        return

    # ── --disable / --enable / --reload  (pilotage du daemon via SIGUSR1) ─
    def _send_command(cmd: str) -> None:
        pid = _read_pid()
        if not pid or not _is_running(pid):
            print("🔴 Scheduler runner non actif. Lancez-le d'abord avec --detach.")
            raise SystemExit(1)
        _CMD_FILE.write_text(cmd)
        os.kill(pid, signal.SIGUSR1)
        print(f"✅ Commande envoyée au PID {pid} : {cmd!r}")
        print(f"   Vérifiez les logs : {_LOG_FILE}")

    if args.disable:
        _send_command(f"disable {args.disable.strip()}")
        return

    if args.enable:
        _send_command(f"enable {args.enable.strip()}")
        return

    if args.reload:
        _send_command("reload")
        return

    # ── --stop ────────────────────────────────────────────────────────────
    if args.stop:
        pid = _read_pid()
        if not pid:
            print("⚠️  Aucun PID trouvé — scheduler déjà arrêté ?")
            raise SystemExit(1)
        if not _is_running(pid):
            print(f"⚠️  PID {pid} introuvable — processus déjà terminé.")
            _PID_FILE.unlink(missing_ok=True)
            raise SystemExit(0)
        os.kill(pid, signal.SIGTERM)
        print(f"⏹  Signal SIGTERM envoyé au PID {pid}.")
        _PID_FILE.unlink(missing_ok=True)
        return

    # ── --dry-run ─────────────────────────────────────────────────────────
    if args.dry_run:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
        from jobs.shared.loader import load_manifest

        manifest = load_manifest()
        jobs_defs = manifest.get("jobs", [])

        print(f"\n{'─' * 70}")
        print(f"  Dry-run — jobs qui seraient démarrés")
        print(f"{'─' * 70}")
        count = 0
        for job_def in jobs_defs:
            name = job_def.get("name", "?")
            schedule = job_def.get("schedule")
            if only_list and name not in only_list:
                continue
            if name in exclude_list:
                print(f"  ⏭  {name:<45} (exclu)")
                continue
            if schedule:
                print(f"  ✅  {name:<45} cron={schedule}")
                count += 1
            else:
                print(f"  ⚪  {name:<45} (pas de schedule)")
        print(f"{'─' * 70}")
        print(f"  {count} trigger(s) seraient démarrés.\n")
        return

    # ── --detach ──────────────────────────────────────────────────────────
    if args.detach:
        pid = _read_pid()
        if pid and _is_running(pid):
            print(f"⚠️  Runner déjà actif — PID {pid}")
            print(f"   Utilisez --stop pour l'arrêter.")
            raise SystemExit(1)

        child_pid = os.fork()
        if child_pid > 0:
            # Parent : écrit le PID et sort
            _PID_FILE.write_text(str(child_pid))
            print(f"🚀 Scheduler runner lancé en arrière-plan — PID {child_pid}")
            print(f"   Logs   : {_LOG_FILE}")
            print(f"   État   : python -m jobs.ops.scheduler_runner --status")
            print(f"   Arrêt  : python -m jobs.ops.scheduler_runner --stop")
            return

        # Enfant : détachement complet
        os.setsid()
        log_fd = open(_LOG_FILE, "a", buffering=1)
        sys.stdout = log_fd
        sys.stderr = log_fd
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.basicConfig(
            stream=log_fd,
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(name)-36s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # ── Démarrage normal (ou enfant après fork) ────────────────────────────
    _logger.info("=" * 60)
    _logger.info("Scheduler Runner démarré — %s", datetime.now(UTC).isoformat())
    _logger.info("=" * 60)

    # Fusionne les exclusions CLI + persistées (--disable survit aux redémarrages)
    persisted_excluded = _read_excluded()
    effective_exclude = list(set(exclude_list) | persisted_excluded)
    if persisted_excluded:
        _logger.info(
            "⏸  Jobs désactivés (exclusion persistée) : %s",
            ", ".join(sorted(persisted_excluded)),
        )

    triggers = _build_triggers(only_list, effective_exclude)
    if not triggers:
        _logger.warning("Aucun trigger à démarrer. Vérifiez le manifest.")
        return

    _run_loop(triggers)


if __name__ == "__main__":
    main()
