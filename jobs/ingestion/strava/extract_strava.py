"""
Ingestion — Strava API v3 → Data Lake (raw).

Adapté depuis ``_archives/jules_strava-api-v3/ingest.py``.
Ce job utilise l'**API décorateurs** ``@step`` / ``@job``.

Fréquence : quotidienne (ou manuelle après une session sportive)
Source    : https://www.strava.com/api/v3
Cible     :
    datalake://raw/strava/athlete/{date}/data.json    — profil athlète
    datalake://raw/strava/stats/{date}/data.json      — statistiques all-time
    datalake://raw/strava/clubs/{date}/data.json      — clubs rejoints
    datalake://raw/strava/routes/{date}/data.json     — routes créées
    datalake://raw/strava/activities/{date}/data.json — liste complète des activités
Owner     : data-team@company.com

Pipeline :
    fetch_global_data      (athlete + stats + clubs + routes)
        ↓
    fetch_activities       (pagination complète, per_page=200, retry ×2)
        ↓
    validate_activities    (champs obligatoires : id, sport_type, start_date_local)
        ↓
    load_to_local_datalake (5 entités JSON partitionnées par date → disque local)
        ↓
    load_to_cloud_hetzner  (upload S3 Hetzner Object Storage)

Variables d'environnement :
    STRAVA_CLIENT_ID      : Client ID de l'application Strava
    STRAVA_CLIENT_SECRET  : Client Secret de l'application Strava
    STRAVA_REFRESH_TOKEN  : Refresh token OAuth2 (généré par setup_auth.py)
    DATALAKE_PATH         : Répertoire racine du Data Lake (défaut : ./data/datalake)
    HETZNER_ACCESS_KEY    : Clé d'accès Hetzner S3
    HETZNER_SECRET_KEY    : Clé secrète Hetzner S3
    HETZNER_BUCKET        : Nom du bucket Hetzner (ex: webtech-s3)
    HETZNER_REGION        : Région Hetzner (ex: hel1, fsn1)

Usage CLI :
    python -m jobs.ingestion.strava.extract_strava                          # pipeline complet
    python -m jobs.ingestion.strava.extract_strava --global-only            # profil + stats + clubs + routes seulement
    python -m jobs.ingestion.strava.extract_strava --start-page 3           # reprendre la pagination à la page 3
    python -m jobs.ingestion.strava.extract_strava --date 2026-01-01        # partition custom
    python -m jobs.ingestion.strava.extract_strava --global-only --date 2026-04-11
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

from jobs.ingestion.strava.client import RateLimitExceededException, StravaClient
from jobs.shared.datalake import DataLake

_logger = get_logger("jobs.ingestion.strava.extract")


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="fetch_global_data", retry_count=3, retry_delay=5.0, timeout=120.0)
def fetch_global_data() -> dict[str, Any]:
    """Récupère les données globales de l'athlète (profil, stats, clubs, routes).

    Effectue 4 appels API :
    - ``GET /athlete``                    → profil complet
    - ``GET /athletes/{id}/stats``        → statistiques all-time
    - ``GET /athlete/clubs``              → clubs rejoints
    - ``GET /athletes/{id}/routes``       → routes créées

    Returns:
        ``{"athlete": {...}, "stats": {...}, "clubs": [...], "routes": [...], "athlete_id": int}``
    """
    _logger.info("=== fetch_global_data ===")
    client = StravaClient.from_env()

    _logger.info("GET /athlete...")
    athlete = client.get("/athlete")
    athlete_id: int = athlete["id"]
    _logger.info(
        "  → Athlète : %s %s (id=%s)",
        athlete.get("firstname", ""),
        athlete.get("lastname", ""),
        athlete_id,
    )

    _logger.info("GET /athletes/%s/stats...", athlete_id)
    stats = client.get(f"/athletes/{athlete_id}/stats")
    _logger.info(
        "  → Stats : %d runs, %d rides, %d swims",
        stats.get("all_run_totals", {}).get("count", 0),
        stats.get("all_ride_totals", {}).get("count", 0),
        stats.get("all_swim_totals", {}).get("count", 0),
    )

    _logger.info("GET /athlete/clubs...")
    clubs = client.get("/athlete/clubs")
    _logger.info("  → %d club(s)", len(clubs))

    _logger.info("GET /athletes/%s/routes...", athlete_id)
    routes = client.get(f"/athletes/{athlete_id}/routes")
    _logger.info("  → %d route(s)", len(routes))

    _logger.success(
        "✅ fetch_global_data — athlète id=%s, %d clubs, %d routes",
        athlete_id,
        len(clubs),
        len(routes),
    )
    return {
        "athlete": athlete,
        "stats": stats,
        "clubs": clubs,
        "routes": routes,
        "athlete_id": athlete_id,
    }


@step(
    name="fetch_activities",
    dependencies=["fetch_global_data"],
    retry_count=2,
    retry_delay=10.0,
)
def fetch_activities(
    athlete_id: int | None = None,
    start_page: int = 1,
) -> dict[str, Any]:
    """Récupère l'intégralité des résumés d'activités via pagination.

    Utilise ``per_page=200`` (maximum Strava) pour minimiser le nombre
    d'appels API. Une pause de 2 s est appliquée entre chaque page.

    Args:
        athlete_id: Injecté depuis l'output de ``fetch_global_data``.
        start_page: Page de départ pour la reprise sur crash (défaut : 1).
                    Peut être passé via ``initial_context`` par le moteur.

    Returns:
        ``{"activities": [...], "count": int, "pages_fetched": int}``

    Raises:
        RateLimitExceededException: Si le quota journalier est atteint.
    """
    if athlete_id is None:
        raise ValueError(
            "athlete_id manquant — fetch_global_data doit s'exécuter en premier."
        )

    _logger.info("=== fetch_activities (start_page=%d) ===", start_page)
    client = StravaClient.from_env()

    pages_fetched = 0
    existing_ids: set[int] = set()
    all_activities: list[dict[str, Any]] = []

    def _on_page(page: int, items: list[dict[str, Any]]) -> None:
        nonlocal pages_fetched
        pages_fetched += 1
        # Comptage par type de sport
        type_counts: dict[str, int] = {}
        for a in items:
            sport = a.get("sport_type", a.get("type", "Unknown"))
            type_counts[sport] = type_counts.get(sport, 0) + 1
        types_str = ", ".join(f"{v}×{k}" for k, v in sorted(type_counts.items()))

        dates = [
            a.get("start_date_local", "")[:10]
            for a in items
            if a.get("start_date_local")
        ]
        period = f"{min(dates)} → {max(dates)}" if dates else "N/A"

        new_items = [a for a in items if a.get("id") and a["id"] not in existing_ids]
        for a in new_items:
            existing_ids.add(a["id"])
        all_activities.extend(new_items)

        _logger.info(
            "  ✓ Page %d : %d récupérées (%s) | Période : %s | %d nouvelles",
            page,
            len(items),
            types_str,
            period,
            len(new_items),
        )

    try:
        client.get_paginated(
            "/athlete/activities",
            per_page=200,
            start_page=start_page,
            page_callback=_on_page,
        )
    except RateLimitExceededException:
        _logger.error(
            "Rate limit atteint après %d pages — %d activités récupérées.",
            pages_fetched,
            len(all_activities),
        )
        raise

    _logger.success(
        "✅ fetch_activities — %d activités sur %d pages",
        len(all_activities),
        pages_fetched,
    )
    return {
        "activities": all_activities,
        "count": len(all_activities),
        "pages_fetched": pages_fetched,
    }


@step(name="validate_activities", dependencies=["fetch_activities"])
def validate_activities(
    activities: list[dict[str, Any]] | None = None,
    count: int = 0,
) -> dict[str, Any]:
    """Validation minimale des activités brutes.

    Vérifie que :
    - La liste n'est pas vide
    - Chaque activité a les champs obligatoires : ``id``, ``sport_type``,
      ``start_date_local``

    Args:
        activities: Injecté depuis l'output de ``fetch_activities``.
        count:      Nombre d'activités (pour le log).

    Returns:
        ``{"status": "valid"|"empty", "invalid_count": int, "total": int}``

    Raises:
        ValueError: Si des activités sans ``id`` sont détectées.
    """
    items = activities or []
    total = len(items)
    _logger.info("Validation de %d activités brutes", total)

    if not items:
        _logger.warning("Validation : aucune activité — pipeline ignorée")
        return {"status": "empty", "invalid_count": 0, "total": 0}

    required = ["id", "sport_type", "start_date_local"]
    invalid = [a for a in items if any(a.get(f) is None for f in required)]

    if invalid:
        msg = f"{len(invalid)} activité(s) sans champ(s) obligatoire(s) {required}"
        _logger.warning("Validation partielle : %s", msg)

    _logger.success(
        "✅ validate_activities — %d/%d valides", total - len(invalid), total
    )
    return {
        "status": "valid",
        "invalid_count": len(invalid),
        "total": total,
    }


@step(
    name="load_to_local_datalake",
    dependencies=["fetch_global_data", "fetch_activities", "validate_activities"],
)
def load_to_local_datalake(
    athlete: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    clubs: list[dict[str, Any]] | None = None,
    routes: list[dict[str, Any]] | None = None,
    activities: list[dict[str, Any]] | None = None,
    status: str = "empty",
    ingest_date: str = "latest",
) -> dict[str, Any]:
    """Écrit toutes les données brutes dans le Data Lake local (partitionné par date).

    Structure de sortie ::

        raw/strava/athlete/{ingest_date}/data.json
        raw/strava/stats/{ingest_date}/data.json
        raw/strava/clubs/{ingest_date}/data.json
        raw/strava/routes/{ingest_date}/data.json
        raw/strava/activities/{ingest_date}/data.json

    Args:
        athlete:      Injecté depuis ``fetch_global_data``.
        stats:        Injecté depuis ``fetch_global_data``.
        clubs:        Injecté depuis ``fetch_global_data``.
        routes:       Injecté depuis ``fetch_global_data``.
        activities:   Injecté depuis ``fetch_activities``.
        status:       Injecté depuis ``validate_activities``.
        ingest_date:  Partition date — injecté depuis ``initial_context``.

    Returns:
        ``{"written": {entity: rows}, "skipped": bool}``
    """
    if status == "empty":
        _logger.info("Chargement local ignoré — aucune activité à écrire")
        return {"written": {}, "skipped": True}

    dl = DataLake.from_env()
    written: dict[str, int] = {}

    entities: dict[str, Any] = {
        "athlete": athlete or {},
        "stats": stats or {},
        "clubs": clubs or [],
        "routes": routes or [],
        "activities": activities or [],
    }

    for entity_name, data in entities.items():
        if not data:
            _logger.debug("Entité '%s' vide — ignorée", entity_name)
            continue

        path = f"raw/strava/{entity_name}/{ingest_date}/"
        _logger.info(
            "Écriture %s → %s (%d enregistrement(s))",
            entity_name,
            path,
            1 if isinstance(data, dict) else len(data),
        )
        dl.write_json_file(path, "data.json", data)
        written[entity_name] = 1 if isinstance(data, dict) else len(data)

    _logger.success(
        "✅ load_to_local_datalake — %d entités écrites, %d enregistrement(s) total",
        len(written),
        sum(written.values()),
    )
    return {"written": written, "skipped": False}


@step(
    name="load_to_cloud_hetzner",
    dependencies=["load_to_local_datalake"],
    retry_count=2,
    retry_delay=5.0,
)
def load_to_cloud_hetzner(
    written: dict[str, int] | None = None,
    skipped: bool = True,
    ingest_date: str = "latest",
) -> dict[str, Any]:
    """Upload les fichiers JSON du Data Lake local vers Hetzner Object Storage (S3).

    Lit les fichiers écrits par ``load_to_local_datalake`` et les envoie
    vers le bucket Hetzner en conservant la même structure de chemin ::

        s3://{HETZNER_BUCKET}/raw/strava/{entity}/{ingest_date}/data.json

    Variables d'environnement requises :
        HETZNER_ACCESS_KEY : Clé d'accès Hetzner S3
        HETZNER_SECRET_KEY : Clé secrète Hetzner S3
        HETZNER_BUCKET     : Nom du bucket (ex: ``webtech-s3``)
        HETZNER_REGION     : Région Hetzner (ex: ``hel1``, ``fsn1``)

    Args:
        written:     Injecté depuis ``load_to_local_datalake`` — entités écrites.
        skipped:     Si True, le chargement local a été ignoré — upload skippé.
        ingest_date: Partition date — injecté depuis ``initial_context``.

    Returns:
        ``{"uploaded": [str], "skipped": bool}``
    """
    import os  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    import boto3  # noqa: PLC0415
    from botocore.exceptions import ClientError  # noqa: PLC0415

    if skipped or not written:
        _logger.info("Upload Hetzner ignoré — aucune donnée écrite localement")
        return {"uploaded": [], "skipped": True}

    region = os.environ.get("HETZNER_REGION", "hel1")
    bucket = os.environ.get("HETZNER_BUCKET", "")
    if not bucket:
        raise ValueError("HETZNER_BUCKET manquant dans les variables d'environnement")

    _logger.info("=== load_to_cloud_hetzner (region=%s, bucket=%s) ===", region, bucket)

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{region}.your-objectstorage.com",
        aws_access_key_id=os.environ["HETZNER_ACCESS_KEY"],
        aws_secret_access_key=os.environ["HETZNER_SECRET_KEY"],
    )

    dl = DataLake.from_env()
    uploaded: list[str] = []

    for entity_name in written:
        local_path = Path(dl.root) / f"raw/strava/{entity_name}/{ingest_date}/data.json"
        s3_key = f"raw/strava/{entity_name}/{ingest_date}/data.json"

        if not local_path.exists():
            _logger.warning("  ⚠ Fichier local introuvable, ignoré : %s", local_path)
            continue

        size = local_path.stat().st_size
        _logger.info(
            "  Upload %s → s3://%s/%s (%d octets)", entity_name, bucket, s3_key, size
        )
        try:
            s3.upload_file(str(local_path), bucket, s3_key)
            uploaded.append(s3_key)
            _logger.info("  ✓ %s", s3_key)
        except ClientError as exc:
            _logger.error("  ✗ Erreur upload %s : %s", s3_key, exc)
            raise

    _logger.success(
        "✅ load_to_cloud_hetzner — %d fichier(s) uploadés dans s3://%s/",
        len(uploaded),
        bucket,
    )
    return {"uploaded": uploaded, "skipped": False}


# ═══════════════════════════════════════════════════════════════════════════
# Job — composition des steps
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="ingestion-strava",
    version="1.1.0",
    description=(
        "Ingestion Strava API v3 → Data Lake (raw). "
        "Pipeline : fetch profil+stats+clubs+routes → "
        "fetch activités paginées (per_page=200, retry ×2) → "
        "validation → écriture JSON locale → upload Hetzner S3."
    ),
    steps=[
        fetch_global_data,
        fetch_activities,
        validate_activities,
        load_to_local_datalake,
        load_to_cloud_hetzner,
    ],
)
def ingest_strava() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    fetch_global_data()
    fetch_activities()
    validate_activities()
    load_to_local_datalake()
    load_to_cloud_hetzner()


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

    parser = argparse.ArgumentParser(
        description="Ingestion Strava API v3 → Data Lake (raw) + Hetzner S3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python -m jobs.ingestion.strava.extract_strava
  python -m jobs.ingestion.strava.extract_strava --global-only
  python -m jobs.ingestion.strava.extract_strava --start-page 3
  python -m jobs.ingestion.strava.extract_strava --date 2026-01-01
  python -m jobs.ingestion.strava.extract_strava --no-cloud
        """,
    )
    parser.add_argument(
        "--global-only",
        action="store_true",
        help=(
            "Récupère uniquement les données globales de l'athlète "
            "(profil, stats, clubs, routes) sans les activités."
        ),
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        metavar="N",
        help="Page de départ pour la pagination des activités (défaut : 1). "
        "Utile pour reprendre une ingestion interrompue.",
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date de partition dans le Data Lake (défaut : date du jour).",
    )
    parser.add_argument(
        "--no-cloud",
        action="store_true",
        help="Désactive l'upload Hetzner — écriture locale uniquement.",
    )
    args = parser.parse_args()

    load_dotenv()
    configure_platform_logging()

    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    today = args.date or settings.today()

    if args.global_only:
        # ── Mode global-only : fetch_global_data + écriture locale + upload ──
        import os  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        import boto3  # noqa: PLC0415

        client = StravaClient.from_env()

        _logger.info("GET /athlete...")
        athlete = client.get("/athlete")
        athlete_id = athlete["id"]
        _logger.info(
            "  → Athlète : %s %s (id=%s)",
            athlete.get("firstname", ""),
            athlete.get("lastname", ""),
            athlete_id,
        )

        _logger.info("GET /athletes/%s/stats...", athlete_id)
        stats = client.get(f"/athletes/{athlete_id}/stats")
        _logger.info(
            "  → Stats : %d runs, %d rides, %d swims",
            stats.get("all_run_totals", {}).get("count", 0),
            stats.get("all_ride_totals", {}).get("count", 0),
            stats.get("all_swim_totals", {}).get("count", 0),
        )

        _logger.info("GET /athlete/clubs...")
        clubs = client.get("/athlete/clubs")
        _logger.info("  → %d club(s)", len(clubs))

        _logger.info("GET /athletes/%s/routes...", athlete_id)
        routes = client.get(f"/athletes/{athlete_id}/routes")
        _logger.info("  → %d route(s)", len(routes))

        dl = DataLake.from_env()
        entities = {
            "athlete": athlete,
            "stats": stats,
            "clubs": clubs,
            "routes": routes,
        }

        # ── Écriture locale ───────────────────────────────────────────────
        written_paths: dict[str, Path] = {}
        for name, data in entities.items():
            dest_file = dl.write_json_file(
                f"raw/strava/{name}/{today}/", "data.json", data
            )
            count = 1 if isinstance(data, dict) else len(data)
            _logger.info("  💾 %s : %d enregistrement(s) → %s", name, count, dest_file)
            print(f"  ✅ {name}: {count} enregistrement(s) → {dest_file}")  # noqa: T201
            written_paths[name] = Path(dest_file)

        _logger.success(  # type: ignore[attr-defined]
            "✅ global-only local — 4 entités écrites dans %s/raw/strava/", dl.root
        )
        print(f"\nDonnées locales écrites dans : {dl.root}/raw/strava/")  # noqa: T201

        # ── Upload Hetzner ────────────────────────────────────────────────
        if not args.no_cloud:
            region = os.environ.get("HETZNER_REGION", "hel1")
            bucket = os.environ.get("HETZNER_BUCKET", "")
            if not bucket:
                print("⚠ HETZNER_BUCKET non défini — upload ignoré")  # noqa: T201
            else:
                s3 = boto3.client(
                    "s3",
                    endpoint_url=f"https://{region}.your-objectstorage.com",
                    aws_access_key_id=os.environ["HETZNER_ACCESS_KEY"],
                    aws_secret_access_key=os.environ["HETZNER_SECRET_KEY"],
                )
                for name, local_path in written_paths.items():
                    s3_key = f"raw/strava/{name}/{today}/data.json"
                    s3.upload_file(str(local_path), bucket, s3_key)
                    print(f"  ☁ {name} → s3://{bucket}/{s3_key}")  # noqa: T201
                print(
                    f"\nUpload Hetzner terminé → s3://{bucket}/raw/strava/"
                )  # noqa: T201

    else:
        # ── Mode complet : pipeline 5 steps ──────────────────────────────
        engine = WorkflowEngine(
            storage=SQLiteStorage(database_path="workflow.db"),
        )

        result = engine.run_with_storage(
            ingest_strava.build(),
            initial_context={"ingest_date": today, "start_page": args.start_page},
        )

        print()  # noqa: T201
        for step_run in result.step_runs:
            ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
            icon = "✅" if ok else "❌"
            print(f"  {icon} {step_run.step_name}: {step_run.status}")  # noqa: T201
            if step_run.output_data:
                summary = {
                    k: v
                    for k, v in step_run.output_data.items()
                    if k not in ("athlete", "stats", "clubs", "routes", "activities")
                }
                if summary:
                    print(f"     → {summary}")  # noqa: T201

        print(f"\nStatut final : {result.status}")  # noqa: T201
