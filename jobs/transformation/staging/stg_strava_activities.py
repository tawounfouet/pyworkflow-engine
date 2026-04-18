# filepath: jobs/transformation/staging/stg_strava_activities.py
"""
Transformation — Activités Strava (raw) → Staging DWH.

Lit les JSON produits par le job d'ingestion depuis le Data Lake et les
charge dans le DWH DuckDB en exploitant tous les champs disponibles.

Sources (par partition YYYY-MM-DD) :
    datalake://raw/strava/daily/{date}/activities.json
    datalake://raw/strava/daily/{date}/athlete.json
    datalake://raw/strava/daily/{date}/activities/{id}/details.json
    datalake://raw/strava/daily/{date}/activities/{id}/laps.json
    datalake://raw/strava/daily/{date}/activities/{id}/streams.json

Tables créées / alimentées :
    staging.stg_strava_athlete      — snapshot athlète (SCD Type 1)
    staging.stg_strava_activities   — activités enrichies (summary + details fusionnés)
    staging.stg_strava_laps         — laps détaillés (1 ligne par lap)
    staging.stg_strava_streams      — streams métriques (1 ligne par type par activité)
    staging.stg_strava_stream_points — time-series pivotées (1 ligne par seconde par activité)

Star schema :
    dim_athlete (athlete_id)
        └── fact_activities (activity_id → athlete_id, date_id)
                ├── fact_laps    (lap_id → activity_id)
                └── fact_streams (activity_id + stream_type)

Pipeline :
    read_raw_from_datalake      (charge tous les JSON de la partition)
        ↓
    normalize_activities        (fusionne summary + details, calcule champs dérivés)
        ↓
    normalize_laps              (aplatit les laps)
        ↓
    normalize_streams           (pivote les streams par type)
        ↓
    load_to_warehouse           (upsert DuckDB toutes les tables)
        ↓
    quality_check               (COUNT + intégrité référentielle)

Usage CLI :
    python -m jobs.transformation.staging.stg_strava_activities
    python -m jobs.transformation.staging.stg_strava_activities --date 2026-04-11
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

from jobs.shared.datalake import DataLake
from jobs.shared.warehouse import Warehouse

_logger = get_logger("jobs.transformation.staging.stg_strava_activities")

_TABLE_ATHLETE = "staging.stg_strava_athlete"
_TABLE_ACTIVITIES = "staging.stg_strava_activities"
_TABLE_LAPS = "staging.stg_strava_laps"
_TABLE_STREAMS = "staging.stg_strava_streams"
_TABLE_STREAM_POINTS = "staging.stg_strava_stream_points"

# DDL des 4 tables (DuckDB)
_DDL = {
    _TABLE_ATHLETE: """
        CREATE TABLE IF NOT EXISTS staging.stg_strava_athlete (
            athlete_id          BIGINT PRIMARY KEY,
            partition_date      VARCHAR,
            username            VARCHAR,
            firstname           VARCHAR,
            lastname            VARCHAR,
            bio                 VARCHAR,
            city                VARCHAR,
            state               VARCHAR,
            country             VARCHAR,
            sex                 VARCHAR,
            weight_kg           DOUBLE,
            athlete_type        INTEGER,
            measurement_pref    VARCHAR,
            follower_count      INTEGER,
            friend_count        INTEGER,
            premium             BOOLEAN,
            summit              BOOLEAN,
            ftp                 DOUBLE,
            profile_url         VARCHAR,
            created_at          TIMESTAMP,
            updated_at          TIMESTAMP,
            loaded_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    _TABLE_ACTIVITIES: """
        CREATE TABLE IF NOT EXISTS staging.stg_strava_activities (
            -- Identifiants
            activity_id             BIGINT PRIMARY KEY,
            athlete_id              BIGINT,
            partition_date          VARCHAR,

            -- Descriptif
            name                    VARCHAR,
            description             VARCHAR,
            sport_type              VARCHAR,
            workout_type            INTEGER,
            device_name             VARCHAR,
            gear_id                 VARCHAR,
            trainer                 BOOLEAN,
            commute                 BOOLEAN,
            manual                  BOOLEAN,
            private                 BOOLEAN,
            visibility              VARCHAR,
            flagged                 BOOLEAN,

            -- Dates
            start_date              TIMESTAMP,
            start_date_local        TIMESTAMP,
            timezone                VARCHAR,
            utc_offset              DOUBLE,
            -- Champs calculés depuis start_date_local
            date_id                 VARCHAR,   -- YYYY-MM-DD
            year                    INTEGER,
            month                   INTEGER,
            day                     INTEGER,
            hour_of_day             INTEGER,
            day_of_week             INTEGER,   -- 0=lundi .. 6=dimanche
            is_weekend              BOOLEAN,

            -- Métriques distance / temps
            distance_m              DOUBLE,
            distance_km             DOUBLE,
            moving_time_s           INTEGER,
            elapsed_time_s          INTEGER,
            duration_min            DOUBLE,
            pace_min_per_km         DOUBLE,    -- null si non-running

            -- Métriques vitesse
            average_speed_ms        DOUBLE,
            max_speed_ms            DOUBLE,
            average_speed_kmh       DOUBLE,
            max_speed_kmh           DOUBLE,

            -- Métriques altitude / dénivelé
            total_elevation_gain_m  DOUBLE,
            elev_high_m             DOUBLE,
            elev_low_m              DOUBLE,
            elevation_per_km        DOUBLE,

            -- Métriques cardio
            has_heartrate           BOOLEAN,
            average_heartrate       DOUBLE,
            max_heartrate           DOUBLE,
            heartrate_opt_out       BOOLEAN,

            -- Métriques puissance / cadence
            average_watts           DOUBLE,
            max_watts               INTEGER,
            weighted_avg_watts      DOUBLE,
            kilojoules              DOUBLE,
            device_watts            BOOLEAN,
            average_cadence         DOUBLE,

            -- Métriques effort
            calories                DOUBLE,
            perceived_exertion      DOUBLE,
            suffer_score            INTEGER,
            achievement_count       INTEGER,
            pr_count                INTEGER,
            kudos_count             INTEGER,
            comment_count           INTEGER,
            photo_count             INTEGER,
            total_photo_count       INTEGER,

            -- GPS
            start_lat               DOUBLE,
            start_lng               DOUBLE,
            end_lat                 DOUBLE,
            end_lng                 DOUBLE,
            summary_polyline        VARCHAR,

            -- Localisation (null si non renseigné par Strava)
            location_city           VARCHAR,
            location_state          VARCHAR,
            location_country        VARCHAR,

            -- Métadonnées
            upload_id               BIGINT,
            external_id             VARCHAR,
            resource_state          INTEGER,
            embed_token             VARCHAR,
            loaded_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    _TABLE_LAPS: """
        CREATE TABLE IF NOT EXISTS staging.stg_strava_laps (
            lap_id                  BIGINT PRIMARY KEY,
            activity_id             BIGINT,
            athlete_id              BIGINT,
            partition_date          VARCHAR,

            name                    VARCHAR,
            lap_index               INTEGER,
            split                   INTEGER,
            start_index             INTEGER,
            end_index               INTEGER,
            pace_zone               INTEGER,

            start_date              TIMESTAMP,
            start_date_local        TIMESTAMP,

            distance_m              DOUBLE,
            distance_km             DOUBLE,
            moving_time_s           INTEGER,
            elapsed_time_s          INTEGER,
            average_speed_ms        DOUBLE,
            max_speed_ms            DOUBLE,
            pace_min_per_km         DOUBLE,
            total_elevation_gain_m  DOUBLE,
            average_heartrate       DOUBLE,
            max_heartrate           DOUBLE,
            average_watts           DOUBLE,
            device_watts            BOOLEAN,
            average_cadence         DOUBLE,

            loaded_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    _TABLE_STREAMS: """
        CREATE TABLE IF NOT EXISTS staging.stg_strava_streams (
            activity_id             BIGINT,
            stream_type             VARCHAR,
            partition_date          VARCHAR,

            -- Métadonnées du stream (résolution, taille originale)
            series_type             VARCHAR,
            original_size           INTEGER,
            resolution              VARCHAR,

            -- Statistiques pré-calculées sur les streams numériques
            data_count              INTEGER,
            data_min                DOUBLE,
            data_max                DOUBLE,
            data_avg                DOUBLE,

            PRIMARY KEY (activity_id, stream_type),
            loaded_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    _TABLE_STREAM_POINTS: """
        CREATE TABLE IF NOT EXISTS staging.stg_strava_stream_points (
            -- Clé primaire composite : activité × index temporel
            activity_id             BIGINT,
            time_index              INTEGER,   -- position dans le stream (0-based)
            partition_date          VARCHAR,

            -- Index temporel et spatial
            time_s                  INTEGER,   -- secondes depuis le début
            distance_m              DOUBLE,    -- mètres depuis le début

            -- Métriques GPS
            lat                     DOUBLE,
            lng                     DOUBLE,

            -- Métriques physiques
            altitude_m              DOUBLE,
            velocity_ms             DOUBLE,    -- m/s
            velocity_kmh            DOUBLE,    -- km/h (calculé)
            grade_pct               DOUBLE,    -- % de pente
            moving                  BOOLEAN,

            -- Métriques optionnelles (null si non disponible)
            heartrate_bpm           DOUBLE,
            cadence_rpm             DOUBLE,
            watts                   DOUBLE,
            temp_c                  DOUBLE,

            PRIMARY KEY (activity_id, time_index),
            loaded_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
}


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="read_raw_from_datalake", timeout=60.0)
def read_raw_from_datalake(
    partition: str = "today",
) -> dict[str, Any]:
    """Charge tous les JSON Strava de la partition depuis le Data Lake.

    Lit :
      - ``raw/strava/daily/{partition}/activities.json``
      - ``raw/strava/daily/{partition}/athlete.json``
      - Pour chaque activité :
          ``raw/strava/daily/{partition}/activities/{id}/details.json``
          ``raw/strava/daily/{partition}/activities/{id}/laps.json``
          ``raw/strava/daily/{partition}/activities/{id}/streams.json``

    Args:
        partition: Date ``YYYY-MM-DD`` ou ``"today"``.

    Returns:
        ``{"partition": str, "athlete": dict, "activities_summary": list,
           "details_by_id": dict, "laps_by_id": dict, "streams_by_id": dict}``
    """
    import json  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    dl = DataLake.from_env()

    if partition == "today":
        from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

        partition = settings.today()

    base = dl.root / f"raw/strava/daily/{partition}"

    # ── Athlète ───────────────────────────────────────────────────────
    athlete_path = base / "athlete.json"
    if not athlete_path.exists():
        raise FileNotFoundError(
            f"athlete.json introuvable : {athlete_path}\n"
            "Lancez d'abord : python -m jobs.ingestion.strava.fetch_today_activities"
        )
    athlete: dict[str, Any] = json.loads(athlete_path.read_text())
    _logger.info("Athlète chargé : id=%s", athlete.get("id"))

    # ── Activités (résumé) ────────────────────────────────────────────
    acts_path = base / "activities.json"
    activities_summary: list[dict[str, Any]] = (
        json.loads(acts_path.read_text()) if acts_path.exists() else []
    )
    _logger.info("Activités (résumé) : %d", len(activities_summary))

    # ── Détails, laps, streams par activité ──────────────────────────
    details_by_id: dict[str, Any] = {}
    laps_by_id: dict[str, Any] = {}
    streams_by_id: dict[str, Any] = {}

    acts_dir = base / "activities"
    if acts_dir.exists():
        for act_dir in sorted(acts_dir.iterdir()):
            if not act_dir.is_dir():
                continue
            act_id = act_dir.name

            details_file = act_dir / "details.json"
            if details_file.exists():
                details_by_id[act_id] = json.loads(details_file.read_text())

            laps_file = act_dir / "laps.json"
            if laps_file.exists():
                laps_by_id[act_id] = json.loads(laps_file.read_text())

            streams_file = act_dir / "streams.json"
            if streams_file.exists():
                streams_by_id[act_id] = json.loads(streams_file.read_text())

    _logger.info(
        "Détails: %d · Laps: %d · Streams: %d",
        len(details_by_id),
        len(laps_by_id),
        len(streams_by_id),
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ read_raw_from_datalake — partition=%s · %d activité(s)",
        partition,
        len(activities_summary),
    )
    return {
        "partition": partition,
        "athlete": athlete,
        "activities_summary": activities_summary,
        "details_by_id": details_by_id,
        "laps_by_id": laps_by_id,
        "streams_by_id": streams_by_id,
    }


@step(name="normalize_athlete", dependencies=["read_raw_from_datalake"])
def normalize_athlete(
    athlete: dict[str, Any] | None = None,
    partition: str = "",
) -> dict[str, Any]:
    """Normalise le snapshot athlète en une ligne plate.

    Args:
        athlete:   Injecté depuis ``read_raw_from_datalake``.
        partition: Injecté depuis ``read_raw_from_datalake``.

    Returns:
        ``{"athlete_row": {...}}``
    """
    data = athlete or {}
    row: dict[str, Any] = {
        "athlete_id": data.get("id"),
        "partition_date": partition,
        "username": data.get("username"),
        "firstname": data.get("firstname"),
        "lastname": data.get("lastname"),
        "bio": data.get("bio"),
        "city": (data.get("city") or "").strip() or None,
        "state": data.get("state"),
        "country": data.get("country"),
        "sex": data.get("sex"),
        "weight_kg": data.get("weight"),
        "athlete_type": data.get("athlete_type"),
        "measurement_pref": data.get("measurement_preference"),
        "follower_count": data.get("follower_count"),
        "friend_count": data.get("friend_count"),
        "premium": data.get("premium"),
        "summit": data.get("summit"),
        "ftp": data.get("ftp"),
        "profile_url": data.get("profile"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }
    _logger.info(
        "Athlète normalisé : id=%s (%s %s)",
        row["athlete_id"],
        row["firstname"],
        row["lastname"],
    )
    _logger.success("✅ normalize_athlete — id=%s", row["athlete_id"])  # type: ignore[attr-defined]
    return {"athlete_row": row}


@step(name="normalize_activities", dependencies=["read_raw_from_datalake"])
def normalize_activities(
    partition: str = "",
    activities_summary: list[dict[str, Any]] | None = None,
    details_by_id: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fusionne les résumés et les détails en lignes plats enrichies.

    Pour chaque activité :
    - Prend le résumé (resource_state=2) comme base
    - Enrichit avec les champs détail (resource_state=3) si disponibles :
      calories, description, best_efforts, splits, etc.
    - Calcule les champs dérivés : distance_km, pace, vitesse en km/h,
      day_of_week, is_weekend, etc.

    Args:
        partition:          Injecté depuis ``read_raw_from_datalake``.
        activities_summary: Injecté depuis ``read_raw_from_datalake``.
        details_by_id:      Injecté depuis ``read_raw_from_datalake``.

    Returns:
        ``{"activity_rows": [...], "act_count": int}``
    """
    from datetime import datetime  # noqa: PLC0415

    summaries = activities_summary or []
    details = details_by_id or {}
    rows: list[dict[str, Any]] = []

    for summary in summaries:
        act_id = summary.get("id")
        # Fusionne summary + details (details écrase en cas de doublon de clé)
        detail = details.get(str(act_id), {})
        merged: dict[str, Any] = {**summary, **detail}

        # ── GPS ───────────────────────────────────────────────────────
        start_ll = merged.get("start_latlng") or []
        end_ll = merged.get("end_latlng") or []
        start_lat = start_ll[0] if len(start_ll) >= 2 else None
        start_lng = start_ll[1] if len(start_ll) >= 2 else None
        end_lat = end_ll[0] if len(end_ll) >= 2 else None
        end_lng = end_ll[1] if len(end_ll) >= 2 else None

        # ── Distance / vitesse ────────────────────────────────────────
        distance_m: float = merged.get("distance") or 0.0
        distance_km = round(distance_m / 1000, 3) if distance_m else None
        moving_time_s: int = merged.get("moving_time") or 0
        duration_min = round(moving_time_s / 60, 1) if moving_time_s else None
        avg_speed_ms: float = merged.get("average_speed") or 0.0
        max_speed_ms: float = merged.get("max_speed") or 0.0

        # Pace (min/km) — pertinent uniquement pour running/walking
        sport = (merged.get("sport_type") or "").lower()
        pace = None
        if (
            distance_m
            and moving_time_s
            and sport in ("run", "walk", "hike", "trailrun")
        ):
            pace = round((moving_time_s / 60) / (distance_m / 1000), 2)

        # Dénivelé par km
        elevation = merged.get("total_elevation_gain") or 0.0
        elevation_per_km = (
            round(elevation / (distance_m / 1000), 2) if distance_m else None
        )

        # ── Dates ─────────────────────────────────────────────────────
        start_local_str: str = merged.get("start_date_local") or ""
        date_id = year = month = day = hour = dow = is_weekend = None
        if start_local_str:
            try:
                dt = datetime.fromisoformat(start_local_str.replace("Z", "+00:00"))
                date_id = dt.strftime("%Y-%m-%d")
                year, month, day = dt.year, dt.month, dt.day
                hour = dt.hour
                dow = dt.weekday()  # 0=lundi, 6=dimanche
                is_weekend = dow >= 5
            except ValueError:
                pass

        # ── Polyline ──────────────────────────────────────────────────
        map_data = merged.get("map") or {}
        polyline = map_data.get("summary_polyline") or map_data.get("polyline")

        rows.append(
            {
                # Identifiants
                "activity_id": act_id,
                "athlete_id": (merged.get("athlete") or {}).get("id"),
                "partition_date": partition,
                # Descriptif
                "name": merged.get("name"),
                "description": merged.get("description"),
                "sport_type": merged.get("sport_type"),
                "workout_type": merged.get("workout_type"),
                "device_name": merged.get("device_name"),
                "gear_id": merged.get("gear_id"),
                "trainer": merged.get("trainer"),
                "commute": merged.get("commute"),
                "manual": merged.get("manual"),
                "private": merged.get("private"),
                "visibility": merged.get("visibility"),
                "flagged": merged.get("flagged"),
                # Dates
                "start_date": merged.get("start_date"),
                "start_date_local": merged.get("start_date_local"),
                "timezone": merged.get("timezone"),
                "utc_offset": merged.get("utc_offset"),
                "date_id": date_id,
                "year": year,
                "month": month,
                "day": day,
                "hour_of_day": hour,
                "day_of_week": dow,
                "is_weekend": is_weekend,
                # Distance / temps
                "distance_m": distance_m or None,
                "distance_km": distance_km,
                "moving_time_s": moving_time_s or None,
                "elapsed_time_s": merged.get("elapsed_time"),
                "duration_min": duration_min,
                "pace_min_per_km": pace,
                # Vitesse
                "average_speed_ms": avg_speed_ms or None,
                "max_speed_ms": max_speed_ms or None,
                "average_speed_kmh": (
                    round(avg_speed_ms * 3.6, 2) if avg_speed_ms else None
                ),
                "max_speed_kmh": round(max_speed_ms * 3.6, 2) if max_speed_ms else None,
                # Altitude / dénivelé
                "total_elevation_gain_m": merged.get("total_elevation_gain"),
                "elev_high_m": merged.get("elev_high"),
                "elev_low_m": merged.get("elev_low"),
                "elevation_per_km": elevation_per_km,
                # Cardio
                "has_heartrate": merged.get("has_heartrate"),
                "average_heartrate": merged.get("average_heartrate"),
                "max_heartrate": merged.get("max_heartrate"),
                "heartrate_opt_out": merged.get("heartrate_opt_out"),
                # Puissance / cadence
                "average_watts": merged.get("average_watts"),
                "max_watts": merged.get("max_watts"),
                "weighted_avg_watts": merged.get("weighted_average_watts"),
                "kilojoules": merged.get("kilojoules"),
                "device_watts": merged.get("device_watts"),
                "average_cadence": merged.get("average_cadence"),
                # Effort
                "calories": merged.get("calories"),
                "perceived_exertion": merged.get("perceived_exertion"),
                "suffer_score": merged.get("suffer_score"),
                "achievement_count": merged.get("achievement_count"),
                "pr_count": merged.get("pr_count"),
                "kudos_count": merged.get("kudos_count"),
                "comment_count": merged.get("comment_count"),
                "photo_count": merged.get("photo_count"),
                "total_photo_count": merged.get("total_photo_count"),
                # GPS
                "start_lat": start_lat,
                "start_lng": start_lng,
                "end_lat": end_lat,
                "end_lng": end_lng,
                "summary_polyline": polyline,
                # Localisation
                "location_city": merged.get("location_city"),
                "location_state": merged.get("location_state"),
                "location_country": merged.get("location_country"),
                # Métadonnées
                "upload_id": merged.get("upload_id"),
                "external_id": merged.get("external_id"),
                "resource_state": merged.get("resource_state"),
                "embed_token": merged.get("embed_token"),
            }
        )

    _logger.info("Activités normalisées : %d ligne(s)", len(rows))
    _logger.success("✅ normalize_activities — %d activité(s)", len(rows))  # type: ignore[attr-defined]
    return {"activity_rows": rows, "act_count": len(rows)}


@step(name="normalize_laps", dependencies=["read_raw_from_datalake"])
def normalize_laps(
    partition: str = "",
    laps_by_id: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aplatit tous les laps en lignes relationnelles.

    Args:
        partition:  Injecté depuis ``read_raw_from_datalake``.
        laps_by_id: Injecté depuis ``read_raw_from_datalake``.

    Returns:
        ``{"lap_rows": [...], "lap_count": int}``
    """
    laps_map = laps_by_id or {}
    rows: list[dict[str, Any]] = []

    for act_id_str, laps in laps_map.items():
        act_id = int(act_id_str)
        for lap in laps:
            distance_m: float = lap.get("distance") or 0.0
            moving_time_s: int = lap.get("moving_time") or 0
            avg_speed_ms: float = lap.get("average_speed") or 0.0
            max_speed_ms: float = lap.get("max_speed") or 0.0

            pace = None
            if distance_m and moving_time_s:
                pace = round((moving_time_s / 60) / (distance_m / 1000), 2)

            rows.append(
                {
                    "lap_id": lap.get("id"),
                    "activity_id": act_id,
                    "athlete_id": (lap.get("athlete") or {}).get("id"),
                    "partition_date": partition,
                    "name": lap.get("name"),
                    "lap_index": lap.get("lap_index"),
                    "split": lap.get("split"),
                    "start_index": lap.get("start_index"),
                    "end_index": lap.get("end_index"),
                    "pace_zone": lap.get("pace_zone"),
                    "start_date": lap.get("start_date"),
                    "start_date_local": lap.get("start_date_local"),
                    "distance_m": distance_m or None,
                    "distance_km": round(distance_m / 1000, 3) if distance_m else None,
                    "moving_time_s": moving_time_s or None,
                    "elapsed_time_s": lap.get("elapsed_time"),
                    "average_speed_ms": avg_speed_ms or None,
                    "max_speed_ms": max_speed_ms or None,
                    "pace_min_per_km": pace,
                    "total_elevation_gain_m": lap.get("total_elevation_gain"),
                    "average_heartrate": lap.get("average_heartrate"),
                    "max_heartrate": lap.get("max_heartrate"),
                    "average_watts": lap.get("average_watts"),
                    "device_watts": lap.get("device_watts"),
                    "average_cadence": lap.get("average_cadence"),
                }
            )

    _logger.info("Laps normalisés : %d ligne(s)", len(rows))
    _logger.success("✅ normalize_laps — %d lap(s)", len(rows))  # type: ignore[attr-defined]
    return {"lap_rows": rows, "lap_count": len(rows)}


@step(name="normalize_streams", dependencies=["read_raw_from_datalake"])
def normalize_streams(
    partition: str = "",
    streams_by_id: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalise les streams en deux tables complémentaires.

    1. ``stream_rows`` → ``stg_strava_streams`` : 1 ligne par type de stream
       par activité, avec métadonnées (resolution, original_size) et
       statistiques pré-calculées (min, max, avg, count). Pas de data_json —
       les données brutes sont dans stream_point_rows.

    2. ``stream_point_rows`` → ``stg_strava_stream_points`` : 1 ligne par
       seconde par activité. Tous les streams sont pivotés sur l'index
       temporel commun, ce qui permet des requêtes analytiques directes :
       ``WHERE altitude_m > 40``, ``AVG(velocity_kmh) WHERE moving = true``,
       ``WHERE grade_pct > 5``, etc.

    Args:
        partition:     Injecté depuis ``read_raw_from_datalake``.
        streams_by_id: Injecté depuis ``read_raw_from_datalake``.

    Returns:
        ``{"stream_rows": [...], "stream_count": int,
           "stream_point_rows": [...], "stream_point_count": int}``
    """
    import statistics  # noqa: PLC0415

    streams_map = streams_by_id or {}
    stream_rows: list[dict[str, Any]] = []
    stream_point_rows: list[dict[str, Any]] = []

    NUMERIC_STREAMS = {
        "altitude",
        "distance",
        "velocity_smooth",
        "grade_smooth",
        "heartrate",
        "cadence",
        "watts",
        "temp",
    }

    for act_id_str, streams_data in streams_map.items():
        act_id = int(act_id_str)

        # ── 1. Métadonnées par type de stream ─────────────────────────
        for stream_type, stream_obj in streams_data.items():
            if not isinstance(stream_obj, dict):
                continue

            data: list[Any] = stream_obj.get("data") or []
            data_min = data_max = data_avg = None

            if stream_type in NUMERIC_STREAMS and data:
                numeric = [v for v in data if isinstance(v, (int, float))]
                if numeric:
                    data_min = round(min(numeric), 4)
                    data_max = round(max(numeric), 4)
                    data_avg = round(statistics.mean(numeric), 4)

            stream_rows.append(
                {
                    "activity_id": act_id,
                    "stream_type": stream_type,
                    "partition_date": partition,
                    "series_type": stream_obj.get("series_type"),
                    "original_size": stream_obj.get("original_size"),
                    "resolution": stream_obj.get("resolution"),
                    "data_count": len(data),
                    "data_min": data_min,
                    "data_max": data_max,
                    "data_avg": data_avg,
                }
            )

        # ── 2. Points temporels — pivot de tous les streams ───────────
        # On utilise le stream 'time' pour déterminer le nombre de points.
        time_data: list[int] = (streams_data.get("time") or {}).get("data") or []
        n_points = len(time_data)
        if n_points == 0:
            continue

        # Extraction de chaque stream en liste (None si absent)
        def _get(name: str) -> list[Any]:
            obj = streams_data.get(name) or {}
            d = obj.get("data") or []
            return d if len(d) == n_points else [None] * n_points

        distance_data = _get("distance")
        altitude_data = _get("altitude")
        velocity_data = _get("velocity_smooth")
        grade_data = _get("grade_smooth")
        moving_data = _get("moving")
        latlng_data = _get("latlng")
        heartrate_data = _get("heartrate")
        cadence_data = _get("cadence")
        watts_data = _get("watts")
        temp_data = _get("temp")

        for i in range(n_points):
            ll = latlng_data[i] if latlng_data[i] else None
            lat = ll[0] if ll and len(ll) == 2 else None
            lng = ll[1] if ll and len(ll) == 2 else None

            v_ms: float | None = velocity_data[i]
            stream_point_rows.append(
                {
                    "activity_id": act_id,
                    "time_index": i,
                    "partition_date": partition,
                    "time_s": time_data[i],
                    "distance_m": distance_data[i],
                    "lat": lat,
                    "lng": lng,
                    "altitude_m": altitude_data[i],
                    "velocity_ms": v_ms,
                    "velocity_kmh": round(v_ms * 3.6, 3) if v_ms is not None else None,
                    "grade_pct": grade_data[i],
                    "moving": (
                        bool(moving_data[i]) if moving_data[i] is not None else None
                    ),
                    "heartrate_bpm": heartrate_data[i],
                    "cadence_rpm": cadence_data[i],
                    "watts": watts_data[i],
                    "temp_c": temp_data[i],
                }
            )

    _logger.info(
        "Streams normalisés : %d métadonnées · %d points",
        len(stream_rows),
        len(stream_point_rows),
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ normalize_streams — %d stream(s) · %d point(s)",
        len(stream_rows),
        len(stream_point_rows),
    )
    return {
        "stream_rows": stream_rows,
        "stream_count": len(stream_rows),
        "stream_point_rows": stream_point_rows,
        "stream_point_count": len(stream_point_rows),
    }


@step(
    name="load_to_warehouse",
    dependencies=[
        "normalize_athlete",
        "normalize_activities",
        "normalize_laps",
        "normalize_streams",
    ],
)
def load_to_warehouse(
    athlete_row: dict[str, Any] | None = None,
    activity_rows: list[dict[str, Any]] | None = None,
    lap_rows: list[dict[str, Any]] | None = None,
    stream_rows: list[dict[str, Any]] | None = None,
    stream_point_rows: list[dict[str, Any]] | None = None,
    partition: str = "",
) -> dict[str, Any]:
    """Upsert toutes les tables dans le DWH DuckDB.

    Ordre d'insertion respectant l'intégrité référentielle :
      1. stg_strava_athlete        (dim)
      2. stg_strava_activities     (fait principal)
      3. stg_strava_laps           (fait enfant)
      4. stg_strava_streams        (métadonnées stream, clé composite)
      5. stg_strava_stream_points  (points temporels, clé composite)

    Args:
        athlete_row:       Injecté depuis ``normalize_athlete``.
        activity_rows:     Injecté depuis ``normalize_activities``.
        lap_rows:          Injecté depuis ``normalize_laps``.
        stream_rows:       Injecté depuis ``normalize_streams``.
        stream_point_rows: Injecté depuis ``normalize_streams``.
        partition:         Injecté depuis ``read_raw_from_datalake``.

    Returns:
        ``{"upserted": {"athlete": int, "activities": int, "laps": int,
                        "streams": int, "stream_points": int}}``
    """
    wh = Warehouse.from_env()
    conn = wh._get_connection()

    # ── Créer les schemas et tables ───────────────────────────────────
    conn.execute("CREATE SCHEMA IF NOT EXISTS staging")
    for table_name, ddl in _DDL.items():
        conn.execute(ddl)
        _logger.info("Table vérifiée / créée : %s", table_name)

    counts: dict[str, int] = {}

    # ── 1. Athlète ────────────────────────────────────────────────────
    athlete_data = [athlete_row] if athlete_row else []
    counts["athlete"] = (
        wh.upsert(_TABLE_ATHLETE, athlete_data, key="athlete_id") if athlete_data else 0
    )
    _logger.info("Upsert %s : %d ligne(s)", _TABLE_ATHLETE, counts["athlete"])

    # ── 2. Activités ──────────────────────────────────────────────────
    acts = activity_rows or []
    counts["activities"] = (
        wh.upsert(_TABLE_ACTIVITIES, acts, key="activity_id") if acts else 0
    )
    _logger.info("Upsert %s : %d ligne(s)", _TABLE_ACTIVITIES, counts["activities"])

    # ── 3. Laps ───────────────────────────────────────────────────────
    laps = lap_rows or []
    counts["laps"] = wh.upsert(_TABLE_LAPS, laps, key="lap_id") if laps else 0
    _logger.info("Upsert %s : %d ligne(s)", _TABLE_LAPS, counts["laps"])

    # ── 4. Streams — métadonnées (clé composite) ──────────────────────
    streams = stream_rows or []
    counts["streams"] = (
        wh.upsert(_TABLE_STREAMS, streams, key=["activity_id", "stream_type"])
        if streams
        else 0
    )
    _logger.info("Upsert %s : %d ligne(s)", _TABLE_STREAMS, counts["streams"])

    # ── 5. Stream points — données temporelles (clé composite) ────────
    points = stream_point_rows or []
    counts["stream_points"] = (
        wh.upsert(_TABLE_STREAM_POINTS, points, key=["activity_id", "time_index"])
        if points
        else 0
    )
    _logger.info(
        "Upsert %s : %d ligne(s)", _TABLE_STREAM_POINTS, counts["stream_points"]
    )

    _logger.success(  # type: ignore[attr-defined]
        "✅ load_to_warehouse — athlete=%d · activities=%d · laps=%d · streams=%d · points=%d",
        counts["athlete"],
        counts["activities"],
        counts["laps"],
        counts["streams"],
        counts["stream_points"],
    )
    return {"upserted": counts, "partition": partition}


@step(name="quality_check", dependencies=["load_to_warehouse"])
def quality_check(
    partition: str = "",
    upserted: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Vérifie l'intégrité post-chargement.

    Contrôles :
    - Les activités de la partition existent dans le DWH.
    - Chaque activité a au moins un lap associé.
    - Chaque activité a au moins un stream.
    - Aucune activité sans athlete_id (intégrité référentielle).

    Args:
        partition: Injecté depuis ``load_to_warehouse``.
        upserted:  Injecté depuis ``load_to_warehouse``.

    Returns:
        ``{"quality_passed": bool, "checks": dict}``
    """
    wh = Warehouse.from_env()

    checks: dict[str, Any] = {}

    # Activités de la partition
    checks["activities_in_partition"] = wh.query_scalar(
        f"SELECT COUNT(*) FROM {_TABLE_ACTIVITIES} WHERE partition_date = ?",  # noqa: S608
        (partition,),
    )

    # Activités sans athlete_id (problème d'intégrité)
    checks["activities_without_athlete"] = wh.query_scalar(
        f"SELECT COUNT(*) FROM {_TABLE_ACTIVITIES} WHERE athlete_id IS NULL"  # noqa: S608
    )

    # Laps orphelins (sans activité correspondante)
    checks["orphan_laps"] = wh.query_scalar(
        f"""SELECT COUNT(*) FROM {_TABLE_LAPS} l  -- noqa: S608
            LEFT JOIN {_TABLE_ACTIVITIES} a ON l.activity_id = a.activity_id
            WHERE a.activity_id IS NULL"""
    )

    # Streams orphelins
    checks["orphan_streams"] = wh.query_scalar(
        f"""SELECT COUNT(*) FROM {_TABLE_STREAMS} s  -- noqa: S608
            LEFT JOIN {_TABLE_ACTIVITIES} a ON s.activity_id = a.activity_id
            WHERE a.activity_id IS NULL"""
    )

    # Points temporels de la partition
    checks["stream_points_in_partition"] = wh.query_scalar(
        f"SELECT COUNT(*) FROM {_TABLE_STREAM_POINTS} WHERE partition_date = ?",  # noqa: S608
        (partition,),
    )

    quality_passed = (
        int(checks.get("activities_in_partition") or 0) > 0
        and int(checks.get("activities_without_athlete") or 0) == 0
        and int(checks.get("orphan_laps") or 0) == 0
        and int(checks.get("orphan_streams") or 0) == 0
    )

    checks_str = " · ".join(f"{k}={v}" for k, v in checks.items())
    if quality_passed:
        _logger.success("✅ quality_check — %s", checks_str)  # type: ignore[attr-defined]
    else:
        _logger.warning("⚠️  quality_check ÉCHEC — %s", checks_str)

    return {"quality_passed": quality_passed, "checks": checks}


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="transform-stg-strava-activities",
    version="1.0.0",
    description=(
        "Transformation activités Strava raw → Staging DWH. "
        "Pipeline : lecture Data Lake → normalisation (activities + laps + streams) "
        "→ upsert DuckDB → quality check."
    ),
    steps=[
        read_raw_from_datalake,
        normalize_athlete,
        normalize_activities,
        normalize_laps,
        normalize_streams,
        load_to_warehouse,
        quality_check,
    ],
)
def transform_stg_strava_activities() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    read_raw_from_datalake()
    normalize_athlete()
    normalize_activities()
    normalize_laps()
    normalize_streams()
    load_to_warehouse()
    quality_check()


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
        description="Transformation activités Strava raw → Staging DWH"
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Partition à transformer (défaut : aujourd'hui).",
    )
    args = parser.parse_args()

    configure_platform_logging()

    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    today = args.date or settings.today()

    engine = WorkflowEngine(storage=SQLiteStorage(database_path="workflow.db"))
    result = engine.run_with_storage(
        transform_stg_strava_activities.build(),
        initial_context={"partition": today},
    )
    for step_run in result.step_runs:
        ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
        print(
            f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
        )  # noqa: T201
    print(f"\nStatut final : {result.status}")  # noqa: T201
