# filepath: jobs/ingestion/strava/fetch_today_activities.py
"""
Ingestion — Activités Strava du jour → Data Lake (raw).

Contrairement à ``extract_strava.py`` (ingestion historique complète),
ce job cible uniquement les activités d'une **date précise** (par défaut
aujourd'hui) via le filtre ``after`` / ``before`` de l'API Strava.

Il est conçu pour être le 1er maillon de la pipeline quotidienne
``pipelines/daily/strava_daily_coaching.py``.

Cible :
    datalake://raw/strava/daily/{date}/activities.json   — activités du jour
    datalake://raw/strava/daily/{date}/athlete.json      — snapshot profil
    datalake://raw/strava/daily/{date}/stats.json        — snapshot stats

Pipeline :
    fetch_athlete_snapshot   (profil + stats, retry ×3)
        ↓
    fetch_daily_activities   (activités du jour via after/before, retry ×3)
        ↓
    fetch_activity_details   (details + laps + streams par activité)
        ↓
    validate_daily           (au moins un champ obligatoire, status vide OK)
        ↓
    load_daily_to_datalake   (écriture JSON partitionné par date)
        ↓
    load_to_cloud_hetzner    (upload S3 Hetzner Object Storage)
        ↓
    notify_by_email          (rapport par e-mail)

Variables d'environnement :
    STRAVA_CLIENT_ID      : Client ID
    STRAVA_CLIENT_SECRET  : Client Secret
    STRAVA_REFRESH_TOKEN  : Refresh token OAuth2
    DATALAKE_PATH         : Répertoire racine du Data Lake
    HETZNER_ACCESS_KEY    : Clé d'accès Hetzner S3
    HETZNER_SECRET_KEY    : Clé secrète Hetzner S3
    HETZNER_BUCKET        : Nom du bucket (ex: webtech-s3)
    HETZNER_REGION        : Région Hetzner (ex: hel1, fsn1)

Usage CLI :
    python -m jobs.ingestion.strava.fetch_today_activities
    python -m jobs.ingestion.strava.fetch_today_activities --date 2026-04-11
    python -m jobs.ingestion.strava.fetch_today_activities --date 2023-04-16
    python -m jobs.ingestion.strava.fetch_today_activities --dry-run
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

from jobs.shared.datalake import DataLake

# Adresse de notification — peut être surchargée via NOTIFY_EMAIL
_NOTIFY_TO = "thomas.awounfouet@yahoo.com"

_logger = get_logger("jobs.ingestion.strava.daily")


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="fetch_athlete_snapshot", retry_count=3, retry_delay=5.0, timeout=60.0)
def fetch_athlete_snapshot() -> dict[str, Any]:
    """Récupère un snapshot du profil athlète et de ses stats all-time.

    Returns:
        ``{"athlete": {...}, "stats": {...}, "athlete_id": int}``
    """
    from jobs.ingestion.strava.client import StravaClient  # noqa: PLC0415

    client = StravaClient.from_env()

    _logger.info("GET /athlete (snapshot)...")
    athlete = client.get("/athlete")
    athlete_id: int = athlete["id"]
    _logger.info(
        "Athlète : %s %s (id=%s)",
        athlete.get("firstname", ""),
        athlete.get("lastname", ""),
        athlete_id,
    )

    _logger.info("GET /athletes/%s/stats...", athlete_id)
    stats = client.get(f"/athletes/{athlete_id}/stats")
    _logger.info(
        "Stats all-time : %d runs · %d rides · %d swims",
        stats.get("all_run_totals", {}).get("count", 0),
        stats.get("all_ride_totals", {}).get("count", 0),
        stats.get("all_swim_totals", {}).get("count", 0),
    )

    _logger.success(  # type: ignore[attr-defined]
        "✅ fetch_athlete_snapshot — id=%s", athlete_id
    )
    return {"athlete": athlete, "stats": stats, "athlete_id": athlete_id}


@step(
    name="fetch_daily_activities",
    dependencies=["fetch_athlete_snapshot"],
    retry_count=3,
    retry_delay=5.0,
    timeout=60.0,
)
def fetch_daily_activities(
    target_date: str = "today",
) -> dict[str, Any]:
    """Récupère les activités Strava pour la date cible via ``after``/``before``.

    Utilise les timestamps Unix calculés depuis ``target_date`` pour borner
    la requête : ``after = minuit début du jour``, ``before = minuit fin du jour``.

    Args:
        target_date: Date ``YYYY-MM-DD`` ou ``"today"``. Injecté depuis
                     ``initial_context``.

    Returns:
        ``{"activities": [...], "count": int, "target_date": str}``
    """
    from datetime import UTC, date, datetime, timedelta  # noqa: PLC0415

    import requests  # noqa: PLC0415

    from jobs.ingestion.strava.client import StravaClient  # noqa: PLC0415

    client = StravaClient.from_env()

    # Résolution de la date
    if target_date == "today":
        from jobs.shared.timezone import today as _today  # noqa: PLC0415

        resolved_date = date.fromisoformat(_today())
    else:
        resolved_date = date.fromisoformat(target_date)

    # Bornes timestamp Unix (journée complète en UTC)
    day_start = datetime(
        resolved_date.year,
        resolved_date.month,
        resolved_date.day,
        0,
        0,
        0,
        tzinfo=UTC,
    )
    day_end = day_start + timedelta(days=1)
    after_ts = int(day_start.timestamp())
    before_ts = int(day_end.timestamp())

    _logger.info(
        "Fetch activités du %s (after=%d, before=%d)...",
        resolved_date.isoformat(),
        after_ts,
        before_ts,
    )

    activities: list[dict[str, Any]] = []
    page = 1
    while True:
        try:
            batch = client.get(
                "/athlete/activities",
                params={
                    "after": after_ts,
                    "before": before_ts,
                    "per_page": 50,
                    "page": page,
                },
            )
        except requests.HTTPError as exc:
            _logger.error("Erreur API Strava page %d : %s", page, exc)
            raise

        if not batch:
            break

        activities.extend(batch)
        _logger.info("  Page %d : %d activité(s)", page, len(batch))

        if len(batch) < 50:
            break
        page += 1

    _logger.info(
        "Activités récupérées pour le %s : %d",
        resolved_date.isoformat(),
        len(activities),
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ fetch_daily_activities — %d activité(s) le %s",
        len(activities),
        resolved_date.isoformat(),
    )
    return {
        "activities": activities,
        "count": len(activities),
        "target_date": resolved_date.isoformat(),
    }


@step(
    name="fetch_activity_details",
    dependencies=["fetch_daily_activities"],
    retry_count=3,
    retry_delay=5.0,
    timeout=300.0,
)
def fetch_activity_details(
    activities: list[dict[str, Any]] | None = None,
    target_date: str = "",
) -> dict[str, Any]:
    """Récupère les détails complets de chaque activité du jour.

    Pour chaque activité retournée par ``fetch_daily_activities``, effectue
    trois appels API supplémentaires et écrit les résultats dans le Data Lake
    sous la structure ::

        raw/strava/daily/{date}/activities/{activity_id}/details.json
        raw/strava/daily/{date}/activities/{activity_id}/laps.json
        raw/strava/daily/{date}/activities/{activity_id}/streams.json

    Args:
        activities:  Injecté depuis ``fetch_daily_activities``.
        target_date: Injecté depuis ``fetch_daily_activities``.

    Returns:
        ``{"enriched_count": int, "skipped_count": int, "paths": [...]}``
    """
    import time  # noqa: PLC0415

    from jobs.ingestion.strava.client import StravaClient  # noqa: PLC0415

    client = StravaClient.from_env()
    dl = DataLake.from_env()

    items = activities or []
    if not items:
        _logger.info("Aucune activité à enrichir pour le %s.", target_date)
        return {"enriched_count": 0, "skipped_count": 0, "paths": []}

    # Streams souhaités (tous les types disponibles)
    STREAM_KEYS = (
        "time,distance,latlng,altitude,velocity_smooth,"
        "heartrate,cadence,watts,temp,moving,grade_smooth"
    )

    all_paths: list[str] = []
    enriched = 0
    skipped = 0

    for activity in items:
        activity_id = activity.get("id")
        if not activity_id:
            _logger.warning("Activité sans id ignorée : %s", activity)
            skipped += 1
            continue

        activity_dir = f"raw/strava/daily/{target_date}/activities/{activity_id}"
        _logger.info("Enrichissement activité %s...", activity_id)

        # ── details ──────────────────────────────────────────────────
        try:
            details = client.get(f"/activities/{activity_id}")
            dest = dl.write_json_file(activity_dir, "details.json", details)
            all_paths.append(str(dest))
            _logger.info("  ✓ details.json → %s", dest)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("  ⚠️  details échoué (id=%s) : %s", activity_id, exc)
            skipped += 1
            continue

        # ── laps ─────────────────────────────────────────────────────
        try:
            laps = client.get(f"/activities/{activity_id}/laps")
            dest = dl.write_json_file(activity_dir, "laps.json", laps)
            all_paths.append(str(dest))
            _logger.info("  ✓ laps.json → %s", dest)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("  ⚠️  laps échoué (id=%s) : %s", activity_id, exc)

        # ── streams ──────────────────────────────────────────────────
        try:
            streams = client.get(
                f"/activities/{activity_id}/streams",
                params={"keys": STREAM_KEYS, "key_by_type": "true"},
            )
            dest = dl.write_json_file(activity_dir, "streams.json", streams)
            all_paths.append(str(dest))
            _logger.info("  ✓ streams.json → %s", dest)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("  ⚠️  streams échoué (id=%s) : %s", activity_id, exc)

        enriched += 1
        # Pause légère pour ne pas saturer le rate limit (200 req/15 min)
        time.sleep(0.5)

    _logger.success(  # type: ignore[attr-defined]
        "✅ fetch_activity_details — %d enrichie(s), %d ignorée(s)",
        enriched,
        skipped,
    )
    return {"enriched_count": enriched, "skipped_count": skipped, "paths": all_paths}


@step(name="validate_daily", dependencies=["fetch_daily_activities"])
def validate_daily(
    activities: list[dict[str, Any]] | None = None,
    count: int = 0,
    target_date: str = "",
) -> dict[str, Any]:
    """Valide les activités du jour.

    Un jour sans activité est considéré comme ``"rest_day"`` (pas une erreur).
    En cas d'activités, vérifie les champs obligatoires : ``id``, ``sport_type``,
    ``start_date_local``.

    Args:
        activities:  Injecté depuis ``fetch_daily_activities``.
        count:       Injecté depuis ``fetch_daily_activities``.
        target_date: Injecté depuis ``fetch_daily_activities``.

    Returns:
        ``{"status": "valid"|"rest_day", "invalid_count": int, "total": int}``
    """
    items = activities or []
    _logger.info("Validation : %d activité(s) pour le %s", len(items), target_date)

    if not items:
        _logger.info("Jour de repos — aucune activité le %s", target_date)
        return {"status": "rest_day", "invalid_count": 0, "total": 0}

    required = ["id", "sport_type", "start_date_local"]
    invalid = [a for a in items if any(a.get(f) is None for f in required)]

    if invalid:
        _logger.warning(
            "%d activité(s) avec champs manquants %s", len(invalid), required
        )

    _logger.success(  # type: ignore[attr-defined]
        "✅ validate_daily — %d/%d valides (status=valid)",
        len(items) - len(invalid),
        len(items),
    )
    return {"status": "valid", "invalid_count": len(invalid), "total": len(items)}


@step(
    name="load_daily_to_datalake",
    dependencies=["fetch_athlete_snapshot", "fetch_daily_activities", "validate_daily"],
)
def load_daily_to_datalake(
    athlete: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    activities: list[dict[str, Any]] | None = None,
    status: str = "rest_day",
    target_date: str = "",
) -> dict[str, Any]:
    """Écrit le snapshot journalier dans le Data Lake.

    Structure de sortie ::

        raw/strava/daily/{target_date}/activities.json
        raw/strava/daily/{target_date}/athlete.json
        raw/strava/daily/{target_date}/stats.json

    Args:
        athlete:     Injecté depuis ``fetch_athlete_snapshot``.
        stats:       Injecté depuis ``fetch_athlete_snapshot``.
        activities:  Injecté depuis ``fetch_daily_activities``.
        status:      Injecté depuis ``validate_daily``.
        target_date: Injecté depuis ``fetch_daily_activities``.

    Returns:
        ``{"partition": str, "activity_count": int, "status": str, "paths": [...]}``
    """
    dl = DataLake.from_env()
    date_dir = f"raw/strava/daily/{target_date}"
    paths: list[str] = []

    # Toujours écrire le snapshot profil/stats (même jour de repos)
    for filename, data in [
        ("athlete.json", athlete or {}),
        ("stats.json", stats or {}),
    ]:
        dest = dl.write_json_file(date_dir, filename, data)
        paths.append(str(dest))
        _logger.info("Écrit : %s", dest)

    # Activités (liste vide OK pour un jour de repos)
    acts = activities or []
    dest = dl.write_json_file(date_dir, "activities.json", acts)
    paths.append(str(dest))
    _logger.info("Écrit : %s (%d activité(s))", dest, len(acts))

    _logger.success(  # type: ignore[attr-defined]
        "✅ load_daily_to_datalake — partition=%s · %d activité(s) · status=%s",
        target_date,
        len(acts),
        status,
    )
    return {
        "partition": target_date,
        "activity_count": len(acts),
        "status": status,
        "paths": paths,
    }


@step(
    name="load_to_cloud_hetzner",
    dependencies=["load_daily_to_datalake"],
    retry_count=2,
    retry_delay=5.0,
)
def load_to_cloud_hetzner(
    partition: str = "",
    paths: list[str] | None = None,
    activity_count: int = 0,
) -> dict[str, Any]:
    """Upload les fichiers JSON du jour vers Hetzner Object Storage (S3).

    Prend les chemins écrits par ``load_daily_to_datalake`` et les envoie
    vers le bucket Hetzner en conservant la même structure ::

        s3://{HETZNER_BUCKET}/raw/strava/daily/{date}/athlete.json
        s3://{HETZNER_BUCKET}/raw/strava/daily/{date}/stats.json
        s3://{HETZNER_BUCKET}/raw/strava/daily/{date}/activities.json
        s3://{HETZNER_BUCKET}/raw/strava/daily/{date}/activities/{id}/details.json
        s3://{HETZNER_BUCKET}/raw/strava/daily/{date}/activities/{id}/laps.json
        s3://{HETZNER_BUCKET}/raw/strava/daily/{date}/activities/{id}/streams.json

    Variables d'environnement requises :
        HETZNER_ACCESS_KEY : Clé d'accès Hetzner S3
        HETZNER_SECRET_KEY : Clé secrète Hetzner S3
        HETZNER_BUCKET     : Nom du bucket (ex: ``webtech-s3``)
        HETZNER_REGION     : Région Hetzner (ex: ``hel1``, ``fsn1``)

    Args:
        partition:      Date de partition (``YYYY-MM-DD``), injectée depuis
                        ``load_daily_to_datalake``.
        paths:          Chemins locaux écrits, injectés depuis
                        ``load_daily_to_datalake``.
        activity_count: Nombre d'activités (pour le log).

    Returns:
        ``{"uploaded": [str], "skipped": bool}``
    """
    import os  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    import boto3  # noqa: PLC0415
    from botocore.exceptions import ClientError  # noqa: PLC0415

    local_files = paths or []
    if not local_files:
        _logger.info("Upload Hetzner ignoré — aucun fichier écrit localement")
        return {"uploaded": [], "skipped": True}

    region = os.environ.get("HETZNER_REGION", "hel1")
    bucket = os.environ.get("HETZNER_BUCKET", "")
    if not bucket:
        raise ValueError("HETZNER_BUCKET manquant dans les variables d'environnement")

    _logger.info(
        "=== load_to_cloud_hetzner (partition=%s, region=%s, bucket=%s) ===",
        partition,
        region,
        bucket,
    )

    dl = DataLake.from_env()
    dl_root = Path(dl.root).resolve()

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{region}.your-objectstorage.com",
        aws_access_key_id=os.environ["HETZNER_ACCESS_KEY"],
        aws_secret_access_key=os.environ["HETZNER_SECRET_KEY"],
    )

    uploaded: list[str] = []

    for local_str in local_files:
        local_path = Path(local_str).resolve()

        if not local_path.exists():
            _logger.warning("  ⚠ Fichier introuvable, ignoré : %s", local_path)
            continue

        # Calcule la clé S3 relative à la racine du datalake
        try:
            s3_key = str(local_path.relative_to(dl_root))
        except ValueError:
            s3_key = local_path.name

        size = local_path.stat().st_size
        _logger.info("  Upload → s3://%s/%s (%d octets)", bucket, s3_key, size)
        try:
            s3.upload_file(str(local_path), bucket, s3_key)
            uploaded.append(s3_key)
            _logger.info("  ✓ %s", s3_key)
        except ClientError as exc:
            _logger.error("  ✗ Erreur upload %s : %s", s3_key, exc)
            raise

    _logger.success(  # type: ignore[attr-defined]
        "✅ load_to_cloud_hetzner — %d fichier(s) uploadés dans s3://%s/raw/strava/daily/%s/",
        len(uploaded),
        bucket,
        partition,
    )
    return {"uploaded": uploaded, "skipped": False}


@step(
    name="notify_by_email",
    dependencies=["load_daily_to_datalake"],
)
def notify_by_email(
    partition: str = "",
    activity_count: int = 0,
    status: str = "rest_day",
    paths: list[str] | None = None,
    target_date: str = "",
) -> dict[str, Any]:
    """Envoie un e-mail de notification de fin de pipeline via ``email.smtp``.

    La configuration SMTP est chargée depuis les variables d'environnement
    avec le préfixe ``SMTP_`` (``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``,
    ``SMTP_PASSWORD``, ``SMTP_USE_SSL``).

    Args:
        partition:      Partition écrite (``YYYY-MM-DD``).
        activity_count: Nombre d'activités ingérées.
        status:         ``"valid"`` ou ``"rest_day"``.
        paths:          Chemins écrits dans le Data Lake.
        target_date:    Date cible injectée depuis le contexte initial.

    Returns:
        ``{"status": "sent", "to": str, "subject": str}``
    """
    import os  # noqa: PLC0415

    from pyconnectors.config import ConnectorConfig  # noqa: PLC0415
    from pyconnectors.services.factory import ConnectorFactory  # noqa: PLC0415

    # ── Config SMTP depuis env ────────────────────────────────────────
    smtp_config = ConnectorConfig(
        params={
            "host": os.environ["SMTP_HOST"],
            "port": int(os.environ.get("SMTP_PORT", "465")),
            "user": os.environ["SMTP_USER"],
            "password": os.environ["SMTP_PASSWORD"],
            "from_addr": os.environ.get("SMTP_USER", "no-reply@localhost"),
            "use_ssl": os.environ.get("SMTP_USE_SSL", "true").lower() == "true",
        }
    )

    # ── Contenu du mail ───────────────────────────────────────────────
    date_label = partition or target_date or "N/A"
    status_emoji = "✅" if status == "valid" else "🛌"
    status_label = "Activités ingérées" if status == "valid" else "Jour de repos"

    subject = (
        f"[Strava Daily] {status_emoji} {date_label} — {activity_count} activité(s)"
    )

    separator = "=" * 50
    written = "\n".join(f"  • {p}" for p in (paths or [])) or "  (aucun fichier)"
    body = (
        f"Rapport d'ingestion Strava — {date_label}\n"
        f"{separator}\n"
        f"\n"
        f"Statut        : {status_label} ({status})\n"
        f"Date          : {date_label}\n"
        f"Activités     : {activity_count}\n"
        f"\n"
        f"Fichiers écrits dans le Data Lake :\n"
        f"{written}\n"
        f"\n"
        f"--\n"
        f"PyWorkflow Engine — pipeline ingestion-strava-daily\n"
    )

    to_addr = os.environ.get("NOTIFY_EMAIL", _NOTIFY_TO)

    # ── Envoi via ConnectorFactory ────────────────────────────────────
    connector = ConnectorFactory.create("email.smtp", config=smtp_config)
    result = connector.safe_execute(
        to_addr=to_addr, subject=subject, body=body, html=False
    )

    if not result.success:
        _logger.warning("Échec envoi email : %s", result.error)
        return {
            "status": "failed",
            "to": to_addr,
            "subject": subject,
            "error": result.error,
        }

    _logger.success(  # type: ignore[attr-defined]
        "✅ notify_by_email — envoyé à %s", to_addr
    )
    return {"status": "sent", "to": to_addr, "subject": subject}


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="ingestion-strava-daily",
    version="1.1.0",
    description=(
        "Ingestion des activités Strava du jour → Data Lake (raw/strava/daily/). "
        "Pipeline : snapshot athlète → activités du jour (filtre after/before) "
        "→ détails enrichis → validation → écriture JSON → upload Hetzner S3 → e-mail."
    ),
    steps=[
        fetch_athlete_snapshot,
        fetch_daily_activities,
        fetch_activity_details,
        validate_daily,
        load_daily_to_datalake,
        load_to_cloud_hetzner,
        notify_by_email,
    ],
)
def ingest_strava_daily() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    fetch_athlete_snapshot()
    fetch_daily_activities()
    fetch_activity_details()
    validate_daily()
    load_daily_to_datalake()
    load_to_cloud_hetzner()
    notify_by_email()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    from dotenv import load_dotenv  # noqa: PLC0415
    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.storage import SQLiteStorage  # noqa: PLC0415

    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Ingestion activités Strava du jour → Data Lake"
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date cible (défaut : aujourd'hui).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les timestamps calculés sans appeler l'API.",
    )
    args = parser.parse_args()

    configure_platform_logging()

    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    today = args.date or settings.today()

    if args.dry_run:
        from datetime import date, timedelta  # noqa: PLC0415

        d = date.fromisoformat(today)
        day_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        print(f"Date cible    : {today}")  # noqa: T201
        print(f"after (Unix)  : {int(day_start.timestamp())}")  # noqa: T201
        print(f"before (Unix) : {int(day_end.timestamp())}")  # noqa: T201
        print("\nDry-run OK — aucun appel API effectué")  # noqa: T201
    else:
        engine = WorkflowEngine(storage=SQLiteStorage(database_path="workflow.db"))
        result = engine.run_with_storage(
            ingest_strava_daily.build(),
            initial_context={"target_date": today},
        )
        for step_run in result.step_runs:
            ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
            print(
                f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
            )  # noqa: T201
        print(f"\nStatut final : {result.status}")  # noqa: T201
