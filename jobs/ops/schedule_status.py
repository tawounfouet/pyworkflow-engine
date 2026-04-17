# filepath: jobs/ops/schedule_status.py
"""
Ops — Affiche l'état de tous les jobs/pipelines schedulés du manifest.

Lit ``jobs/manifest.yaml`` et affiche :
  - Les jobs avec leur cron, prochain déclenchement, owner et tags
  - Les pipelines avec leur cron et leurs jobs
  - Les schedulers détachés actifs (via les .pid dans logs/)

Usage :
    python -m jobs.ops.schedule_status
    python -m jobs.ops.schedule_status --all          # inclut les jobs sans schedule
    python -m jobs.ops.schedule_status --json         # sortie JSON brute
    python -m jobs.ops.schedule_status --next 5       # affiche les 5 prochains fires
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


# ── Chemins ───────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "jobs" / "manifest.yaml"
_LOGS_DIR = _ROOT / "logs"

# ── Helpers cron ──────────────────────────────────────────────────────────────


def _next_fire(cron_expr: str, after: datetime | None = None) -> datetime | None:
    """Calcule la prochaine occurrence d'une expression cron après ``after``."""
    try:
        # Réutilise CronExpression du projet
        sys.path.insert(0, str(_ROOT / "src"))
        from pyworkflow_engine.adapters.triggers.schedule import (
            CronExpression,
        )  # noqa: PLC0415

        expr = CronExpression(cron_expr)
    except Exception:
        return None

    now = after or datetime.now(UTC)
    # Avance minute par minute (max 1 an = ~525 600 itérations)
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(525_600):
        if expr.matches(candidate):
            return candidate
        candidate += timedelta(minutes=1)
    return None


def _human_delta(dt: datetime) -> str:
    """Retourne un delta lisible : 'dans 3 min', 'dans 2h 15min', etc."""
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = dt - now
    total = int(delta.total_seconds())
    if total < 0:
        return "passé"
    if total < 60:
        return f"dans {total}s"
    if total < 3600:
        return f"dans {total // 60}min"
    h = total // 3600
    m = (total % 3600) // 60
    if m:
        return f"dans {h}h {m}min"
    return f"dans {h}h"


# ── PID / scheduler détaché ───────────────────────────────────────────────────


def _active_pids() -> dict[str, int]:
    """Retourne les schedulers détachés actifs {nom: pid}."""
    active: dict[str, int] = {}
    for pid_file in _LOGS_DIR.glob("*.pid"):
        try:
            pid = int(pid_file.read_text().strip())
            try:
                os.kill(pid, 0)
                active[pid_file.stem] = pid
            except (ProcessLookupError, PermissionError):
                pass
        except (ValueError, OSError):
            pass
    return active


# ── Affichage ─────────────────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RED = "\033[31m"
_BLUE = "\033[34m"
_WHITE = "\033[97m"


def _c(text: str, *codes: str) -> str:
    return "".join(codes) + str(text) + _RESET


def _print_jobs(
    jobs: list[dict], show_all: bool, next_n: int, active_pids: dict
) -> None:
    scheduled = [j for j in jobs if j.get("schedule")]
    unscheduled = [j for j in jobs if not j.get("schedule")]

    print(
        _c(
            f"\n  {'JOB':<36} {'CRON':<22} {'PROCHAIN FIRE':<20} {'ÉTAT':<12} TAGS",
            _BOLD,
            _WHITE,
        )
    )
    print("  " + "─" * 105)

    for job in scheduled:
        name = job["name"]
        cron = job["schedule"]
        tags = ", ".join(job.get("tags", []))
        owner = job.get("owner", "")
        nxt = _next_fire(cron)
        nxt_str = nxt.strftime("%d/%m %H:%M") if nxt else "?"
        delta = _human_delta(nxt) if nxt else ""

        # Déterminer l'état : scheduler détaché actif ?
        pid_key = name.replace("-", "_").replace(".", "_")
        # Cherche si un pid file porte ce nom ou "heartbeat"
        state = ""
        for pid_name, pid in active_pids.items():
            if pid_name in name or name.startswith("ops-heartbeat"):
                state = _c(f"🟢 PID {pid}", _GREEN)
                break
        if not state:
            state = _c("⚪ manifest", _DIM)

        tags_str = _c(tags[:30], _DIM) if tags else ""
        print(
            f"  {_c(name[:35], _CYAN):<46} "
            f"{_c(cron, _YELLOW):<31} "
            f"{nxt_str:<12}{_c(delta, _DIM):<20} "
            f"{state:<22} {tags_str}"
        )

    if show_all and unscheduled:
        print(_c("\n  Sans schedule :", _DIM))
        for job in unscheduled:
            print(f"  {_c('·', _DIM)} {job['name']}")


def _print_pipelines(pipelines: list[dict]) -> None:
    scheduled = [p for p in pipelines if p.get("schedule")]
    if not scheduled:
        return

    print(
        _c(
            f"\n  {'PIPELINE':<36} {'CRON':<22} {'PROCHAIN FIRE':<20} JOBS",
            _BOLD,
            _WHITE,
        )
    )
    print("  " + "─" * 105)

    for pl in scheduled:
        name = pl["name"]
        cron = pl["schedule"]
        nxt = _next_fire(cron)
        nxt_str = nxt.strftime("%d/%m %H:%M") if nxt else "?"
        delta = _human_delta(nxt) if nxt else ""
        pl_jobs = "→ ".join(pl.get("jobs", []))

        print(
            f"  {_c(name[:35], _BLUE):<46} "
            f"{_c(cron, _YELLOW):<31} "
            f"{nxt_str:<12}{_c(delta, _DIM):<20} "
            f"{_c(pl_jobs[:50], _DIM)}"
        )


def _print_next_n(jobs: list[dict], pipelines: list[dict], n: int) -> None:
    """Affiche les n prochains fires (jobs + pipelines triés par heure)."""
    events: list[tuple[datetime, str, str]] = []  # (dt, type, name)

    for item in jobs:
        if item.get("schedule"):
            nxt = _next_fire(item["schedule"])
            if nxt:
                events.append((nxt, "job", item["name"]))

    for pl in pipelines:
        if pl.get("schedule"):
            nxt = _next_fire(pl["schedule"])
            if nxt:
                events.append((nxt, "pipeline", pl["name"]))

    events.sort(key=lambda x: x[0])

    print(_c(f"\n  Prochains {n} déclenchements :", _BOLD, _WHITE))
    print("  " + "─" * 65)
    for dt, kind, name in events[:n]:
        icon = "⚙" if kind == "job" else "⛓"
        delta = _human_delta(dt)
        label = _c(name, _CYAN if kind == "job" else _BLUE)
        print(
            f"  {icon}  {dt.strftime('%d/%m %H:%M UTC'):<18} {_c(delta, _YELLOW):<22} {label}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Affiche l'état de tous les jobs/pipelines schedulés."
    )
    parser.add_argument(
        "--all", action="store_true", help="Inclut les jobs sans schedule."
    )
    parser.add_argument(
        "--json", action="store_true", help="Sortie JSON brute du manifest."
    )
    parser.add_argument(
        "--next",
        type=int,
        default=0,
        metavar="N",
        help="Affiche les N prochains fires (ex: --next 10).",
    )
    args = parser.parse_args()

    # ── Chargement manifest ───────────────────────────────────────────────
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        print("⚠️  PyYAML non installé. Lancez : pip install pyyaml")
        raise SystemExit(1)

    if not _MANIFEST.exists():
        print(f"✗ Manifest introuvable : {_MANIFEST}")
        raise SystemExit(1)

    with _MANIFEST.open() as f:
        manifest = yaml.safe_load(f)

    jobs_list = manifest.get("jobs", [])
    pipelines_list = manifest.get("pipelines", [])

    # ── Mode --json ───────────────────────────────────────────────────────
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return

    # ── En-tête ───────────────────────────────────────────────────────────
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    active = _active_pids()

    print(_c(f"\n{'─' * 107}", _DIM))
    print(
        _c("  PyWorkflow Engine", _BOLD, _WHITE)
        + _c(" — Schedule Status", _DIM)
        + _c(f"  ·  {now_str}", _DIM)
    )
    print(
        _c(f"  {len(jobs_list)} jobs", _CYAN)
        + _c(f"  ·  {len(pipelines_list)} pipelines", _BLUE)
        + _c(f"  ·  {len(active)} scheduler(s) actif(s)", _GREEN if active else _DIM)
    )
    print(_c(f"{'─' * 107}\n", _DIM))

    # ── Schedulers détachés actifs ────────────────────────────────────────
    if active:
        print(_c("  Schedulers détachés actifs :", _BOLD, _GREEN))
        for name, pid in active.items():
            log = _LOGS_DIR / f"{name}.log"
            print(f"  🟢  {_c(name, _GREEN)}  PID {pid}  logs → {log}")
        print()

    # ── Jobs ──────────────────────────────────────────────────────────────
    print(
        _c(
            "  ── JOBS ─────────────────────────────────────────────────────────────────────────────────────────────────",
            _DIM,
        )
    )
    _print_jobs(jobs_list, args.all, args.next, active)

    # ── Pipelines ─────────────────────────────────────────────────────────
    print(
        _c(
            "\n  ── PIPELINES ────────────────────────────────────────────────────────────────────────────────────────────",
            _DIM,
        )
    )
    _print_pipelines(pipelines_list)

    # ── Prochains N fires ─────────────────────────────────────────────────
    if args.next:
        _print_next_n(jobs_list, pipelines_list, args.next)

    print(_c(f"\n{'─' * 107}\n", _DIM))


if __name__ == "__main__":
    main()
