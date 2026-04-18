# filepath: jobs/llm/strava_daily_coaching/coach_daily.py
"""
LLM — Coaching journalier Strava via agent IA (GPT-4o).

2ème maillon de la pipeline ``pipelines/daily/strava_daily_coaching.py``.
Lit les données du jour (activités + snapshot profil) depuis le Data Lake,
soumet un rapport à un agent IA coach sportif, puis stocke l'analyse dans le
Data Lake sous ``llm/strava/daily_coaching/{date}/coaching.json``.

Cible :
    datalake://llm/strava/daily_coaching/{date}/coaching.json

Pipeline :
    load_daily_data       (lecture raw/strava/daily/{date}/)
        ↓
    load_session_details  (laps + km-splits + zones FC depuis DWH DuckDB)
        ↓
    build_coaching_prompt (contexte textuel enrichi + stats récentes)
        ↓
    run_coaching_agent    (appel GPT-4o, JSON structuré, retry ×2)
        ↓
    save_coaching_report  (écriture datalake + résumé console)

Variables d'environnement :
    OPENAI_API_KEY  : Clé API OpenAI (obligatoire)
    OPENAI_MODEL    : Modèle (défaut : gpt-4o)
    OPENAI_TIMEOUT  : Timeout secondes (défaut : 120)
    DATALAKE_PATH   : Répertoire racine du Data Lake

Usage CLI :
    python -m jobs.llm.strava_daily_coaching.coach_daily
    python -m jobs.llm.strava_daily_coaching.coach_daily --date 2026-04-13
    python -m jobs.llm.strava_daily_coaching.coach_daily --date 2023-04-16

    python -m jobs.llm.strava_daily_coaching.coach_daily --model gpt-4o-mini
    python -m jobs.llm.strava_daily_coaching.coach_daily --dry-run
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

from jobs.shared.datalake import DataLake
from jobs.shared.warehouse import Warehouse

_logger = get_logger("jobs.llm.strava_daily_coaching")

# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
Tu es un coach sportif personnel expert, bienveillant et motivant.
Tu reçois chaque jour le rapport d'entraînement d'un athlète via Strava.

Ton rôle :
- Analyser la ou les séance(s) du jour avec une précision chirurgicale.
- Exploiter toutes les données granulaires disponibles : laps, km-splits (allure + altitude
  par km), zones FC, dénivelé. Cite les chiffres réels.
- Contextualiser par rapport aux stats récentes (fatigue, charge, progression YTD).
- Donner des recommandations concrètes et personnalisées pour le lendemain et la semaine.
- Adapter le ton : encourager un jour de repos, féliciter une belle séance, alerter sur
  les signaux de surmenage.

Données disponibles dans le prompt :
- Résumé activité (distance, durée, D+, FC moy/max, allure globale)
- Laps détaillés (allure, FC, distance par lap)
- Km-splits (allure + altitude moyennes par km entier)
- Analyse FC (médiane, P75 en % FCmax) si disponible
- Segments Strava (section "Segments & Records PR") : segments nommés avec rang PR, allure, dénivelé

Règles absolues :
- Réponds UNIQUEMENT en JSON valide, strictement conforme au schéma fourni.
- Toutes les valeurs textuelles sont en français.
- Distances en km, durées en min, dénivelé en mètres, allures en min/km.
- Sois précis : cite toujours les chiffres réels (distance, durée, FC, allure).
- Si aucune activité (jour de repos) : adapte ton analyse en conséquence.
- Si des km-splits sont fournis, analyse l'évolution km par km : repère les accélérations,
  les coups de mou, l'effet du dénivelé sur l'allure, la gestion d'effort globale.
- Si des segments sont fournis dans "Segments & Records PR", remplis ``segments_highlights``
  avec les segments notables (PR rank 1/2 en priorité). Pour chaque segment, cite l'allure
  réalisée, le dénivelé, et si c'est un PR absolu ou un 2e meilleur temps perso. Une phrase
  courte, factuelle et motivante. Si aucun segment n'est fourni, renvoie un tableau vide ``[]``.

Concernant le champ ``podcast_commentary`` :
- C'est le cœur de ton analyse. Écris un texte continu de 250 à 350 mots.
- Ton direct, parlé, comme si tu commentais la séance en podcast ou en audio-coaching.
- Structure naturelle : (1) description vivante de la séance, (2) analyse technique
  km par km (cite les splits clés), (3) bilan effort/récupération avec les données YTD,
  (4) recommandation motivante pour le lendemain.
- Utilise des connecteurs oraux : "Alors", "Ce qui est intéressant ici", "Regarde bien",
  "Et là on voit que", "Ce que je retiens", etc.
- Ne répète PAS les informations de ``session_summary`` ou ``coach_message``.
"""

_COACHING_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "Date analysée YYYY-MM-DD"},
        "session_type": {
            "type": "string",
            "enum": ["rest_day", "easy", "moderate", "hard", "race", "mixed"],
            "description": "Classification de la journée d'entraînement",
        },
        "session_summary": {
            "type": "string",
            "description": "Résumé en 1-2 phrases de la journée (ou du repos)",
        },
        "activities_analysis": {
            "type": "array",
            "description": "Analyse de chaque activité du jour",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "sport": {"type": "string"},
                    "distance_km": {"type": "number"},
                    "duration_min": {"type": "integer"},
                    "elevation_m": {"type": "number"},
                    "intensity_score": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Score d'intensité estimé sur 10",
                    },
                    "quality_assessment": {
                        "type": "string",
                        "description": "Évaluation qualitative de la séance",
                    },
                    "pace_min_per_km": {
                        "type": "string",
                        "description": "Allure moyenne si course (ex: '5:23') — null sinon",
                    },
                    "pace_profile": {
                        "type": "string",
                        "description": "Profil d'allure basé sur les km-splits/laps : 'régulière', 'progressif négatif', 'départ trop rapide', 'coups de mou km 10-12', etc. — null si données non disponibles",
                    },
                    "hr_profile": {
                        "type": "string",
                        "description": "Profil cardio basé sur la distribution FC : 'endurance fondamentale', 'seuil aérobie', 'travail au seuil', 'intensité élevée' — null si données non disponibles",
                    },
                    "km_splits_analysis": {
                        "type": "string",
                        "description": "Analyse narrative des km-splits : décris l'évolution de l'allure km par km, repère les phases (échauffement, régime de croisière, coups de mou, relances, fin de course). Cite les splits clés en min/km. 3-5 phrases.",
                    },
                },
                "required": ["name", "sport", "intensity_score", "quality_assessment"],
            },
        },
        "load_assessment": {
            "type": "object",
            "description": "Évaluation de la charge d'entraînement",
            "properties": {
                "daily_load": {
                    "type": "string",
                    "enum": ["none", "light", "moderate", "high", "very_high"],
                },
                "weekly_trend": {
                    "type": "string",
                    "description": "Tendance de la charge sur la semaine en cours",
                },
                "fatigue_signal": {
                    "type": "string",
                    "enum": ["none", "low", "moderate", "high"],
                    "description": "Signal de fatigue détecté dans les données",
                },
            },
            "required": ["daily_load", "weekly_trend", "fatigue_signal"],
        },
        "tomorrow_recommendation": {
            "type": "object",
            "description": "Recommandation pour le lendemain",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "Type de séance recommandé (ex: 'Récupération active', 'Repos complet', 'Endurance fondamentale 45 min')",
                },
                "rationale": {
                    "type": "string",
                    "description": "Justification basée sur les données du jour",
                },
            },
            "required": ["type", "rationale"],
        },
        "weekly_tip": {
            "type": "string",
            "description": "Conseil hebdomadaire ou point d'attention à surveiller cette semaine",
        },
        "coach_message": {
            "type": "string",
            "description": "Message personnel court du coach à l'athlète (2-3 phrases max, ton direct et motivant, à afficher en exergue)",
        },
        "podcast_commentary": {
            "type": "string",
            "description": "Commentaire audio-coaching long (250-350 mots). Ton parlé, comme un podcast. Structure : (1) description vivante de la séance, (2) analyse km par km avec chiffres des splits, (3) bilan effort/récupération contextuel (charge YTD, fatigue), (4) recommandation motivante. Utilise des connecteurs oraux. Ce texte doit pouvoir être lu à voix haute en 60-120 secondes.",
        },
        "segments_highlights": {
            "type": "array",
            "description": "Liste des segments notables (PR, top classement, effort remarquable). Inclure uniquement les segments significatifs (PR rank 1 ou 2, ou effort exceptionnel).",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom du segment Strava"},
                    "pr_rank": {
                        "type": "integer",
                        "description": "Classement personnel (1=nouveau PR, 2=2e meilleur temps, etc.)",
                    },
                    "distance_km": {"type": "number"},
                    "pace_min_per_km": {
                        "type": "string",
                        "description": "Allure réalisée sur ce segment",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Commentaire coach sur la performance (1 phrase, cite grade/contexte si pertinent)",
                    },
                },
                "required": ["name", "comment"],
            },
        },
        "metadata": {
            "type": "object",
            "properties": {
                "model_used": {"type": "string"},
                "generated_at": {"type": "string"},
                "partition": {"type": "string"},
                "activity_count": {"type": "integer"},
            },
        },
    },
    "required": [
        "date",
        "session_type",
        "session_summary",
        "activities_analysis",
        "load_assessment",
        "tomorrow_recommendation",
        "weekly_tip",
        "coach_message",
        "podcast_commentary",
        "segments_highlights",
        "metadata",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _fmt_pace(distance_m: float, moving_time_s: float) -> str | None:
    """Calcule l'allure min/km depuis distance (m) et temps (s)."""
    if not distance_m or not moving_time_s:
        return None
    pace_s_per_km = moving_time_s / (distance_m / 1000)
    mins, secs = divmod(int(pace_s_per_km), 60)
    return f"{mins}:{secs:02d}"


def _fmt_duration(seconds: int | float) -> str:
    """Formate secondes → 'Xh Ym' ou 'Xm'."""
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _sport_fr(sport_type: str) -> str:
    """Traduit sport_type Strava en français."""
    return {
        "Run": "Course à pied",
        "Ride": "Vélo",
        "Swim": "Natation",
        "Walk": "Marche",
        "Yoga": "Yoga",
        "Workout": "Musculation / Cross-training",
        "Pilates": "Pilates",
        "WeightTraining": "Haltérophilie",
        "Hike": "Randonnée",
        "VirtualRide": "Vélo virtuel",
        "VirtualRun": "Course virtuelle",
    }.get(sport_type, sport_type)


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="load_daily_data", timeout=30.0)
def load_daily_data(
    partition: str = "today",
) -> dict[str, Any]:
    """Lit le snapshot journalier depuis le Data Lake.

    Lit les 3 fichiers écrits par ``fetch_today_activities`` :
    ``activities.json``, ``athlete.json``, ``stats.json``.

    Si ``partition="today"``, résout automatiquement la date du jour.

    Args:
        partition: Date ``YYYY-MM-DD`` ou ``"today"``. Injecté depuis
                   ``initial_context`` (propagé par le PipelineRunner).

    Returns:
        ``{"activities": [...], "athlete": {...}, "stats": {...},
           "partition": str, "activity_count": int}``

    Raises:
        FileNotFoundError: Si la partition n'existe pas dans le Data Lake.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    dl = DataLake.from_env()

    if partition == "today":
        from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

        partition = settings.today()

    date_dir = f"raw/strava/daily/{partition}"
    if not dl.exists(date_dir):
        raise FileNotFoundError(
            f"Partition introuvable : {date_dir}\n"
            "Lancez d'abord : python -m jobs.ingestion.strava.fetch_today_activities"
        )

    # Lecture des 3 fichiers
    def _read(filename: str) -> Any:
        target = dl.root / date_dir / filename
        if not target.exists():
            return [] if "activities" in filename else {}
        import json as _json  # noqa: PLC0415

        return _json.loads(target.read_text())

    activities: list[dict[str, Any]] = _read("activities.json")
    athlete: dict[str, Any] = _read("athlete.json")
    stats: dict[str, Any] = _read("stats.json")

    _logger.info(
        "Partition %s : %d activité(s) · athlète=%s %s",
        partition,
        len(activities),
        athlete.get("firstname", "?"),
        athlete.get("lastname", "?"),
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ load_daily_data — partition=%s · %d activité(s)", partition, len(activities)
    )
    return {
        "activities": activities,
        "athlete": athlete,
        "stats": stats,
        "partition": partition,
        "activity_count": len(activities),
    }


@step(name="load_session_details", dependencies=["load_daily_data"], timeout=30.0)
def load_session_details(
    activities: list[dict[str, Any]] | None = None,
    partition: str = "",
) -> dict[str, Any]:
    """Charge les détails enrichis des activités depuis le DWH DuckDB.

    Requête les tables staging pour obtenir :
    - Les laps avec métriques détaillées (allure, FC, D+)
    - Les statistiques de stream par type (HR zones, vitesse, altitude)
    - Les km-splits (agrégation des stream_points par km entier)
    - La distribution des fréquences cardiaques (zones d'intensité)

    Ces données sont beaucoup plus riches et compactes pour le LLM que le
    JSON brut : les 9 302 points de stream sont résumés en ~20 lignes de
    statistiques pertinentes.

    Args:
        activities: Injecté depuis ``load_daily_data`` — liste des activités.
        partition:  Injecté depuis ``load_daily_data``.

    Returns:
        ``{"laps_by_activity": dict, "stream_stats_by_activity": dict,
           "km_splits_by_activity": dict, "hr_zones_by_activity": dict,
           "segments_by_activity": dict, "has_detail": bool}``
    """
    acts = activities or []
    if not acts:
        _logger.info("load_session_details — aucune activité, skip DWH")
        return {
            "laps_by_activity": {},
            "stream_stats_by_activity": {},
            "km_splits_by_activity": {},
            "hr_zones_by_activity": {},
            "has_detail": False,
        }

    wh = Warehouse.from_env()
    activity_ids = [str(a["id"]) for a in acts if a.get("id")]

    if not activity_ids:
        return {
            "laps_by_activity": {},
            "stream_stats_by_activity": {},
            "km_splits_by_activity": {},
            "hr_zones_by_activity": {},
            "has_detail": False,
        }

    # DuckDB placeholders: one ? per id
    ids_placeholder = ", ".join(["?"] * len(activity_ids))
    ids_params = tuple(int(i) for i in activity_ids)

    # ── 1. Laps ───────────────────────────────────────────────────────
    laps_by_activity: dict[str, list[dict[str, Any]]] = {}
    try:
        laps_rows = wh.query(
            f"""
            SELECT
                activity_id, lap_index, name,
                distance_km, moving_time_s, pace_min_per_km,
                average_heartrate, max_heartrate,
                total_elevation_gain_m, average_cadence, average_watts
            FROM staging.stg_strava_laps
            WHERE activity_id IN ({ids_placeholder})
            ORDER BY activity_id, lap_index
            """,  # noqa: S608
            ids_params,
        )
        for row in laps_rows:
            aid = str(row["activity_id"])
            laps_by_activity.setdefault(aid, []).append(row)
        _logger.info("Laps chargés depuis DWH : %d", len(laps_rows))
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Impossible de charger les laps depuis DWH : %s", exc)

    # ── 2. Stream stats (résumé par type) ─────────────────────────────
    stream_stats_by_activity: dict[str, list[dict[str, Any]]] = {}
    try:
        stats_rows = wh.query(
            f"""
            SELECT
                activity_id, stream_type,
                data_count, data_min, data_max, data_avg, resolution
            FROM staging.stg_strava_streams
            WHERE activity_id IN ({ids_placeholder})
            ORDER BY activity_id, stream_type
            """,  # noqa: S608
            ids_params,
        )
        for row in stats_rows:
            aid = str(row["activity_id"])
            stream_stats_by_activity.setdefault(aid, []).append(row)
        _logger.info("Stream stats chargées depuis DWH : %d", len(stats_rows))
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Impossible de charger les stream stats depuis DWH : %s", exc)

    # ── 3. Km-splits (agrégation des stream_points par km entier) ─────
    km_splits_by_activity: dict[str, list[dict[str, Any]]] = {}
    try:
        km_rows = wh.query(
            f"""
            SELECT
                activity_id,
                FLOOR(distance_m / 1000) + 1   AS km_split,
                COUNT(*)                        AS point_count,
                ROUND(AVG(velocity_kmh), 2)     AS avg_speed_kmh,
                ROUND(AVG(heartrate_bpm), 1)    AS avg_hr,
                ROUND(MAX(heartrate_bpm), 1)    AS max_hr,
                ROUND(AVG(altitude_m), 1)       AS avg_altitude_m,
                ROUND(MAX(altitude_m), 1)       AS max_altitude_m,
                ROUND(MIN(altitude_m), 1)       AS min_altitude_m,
                ROUND(AVG(grade_pct), 2)        AS avg_grade_pct,
                SUM(CASE WHEN moving THEN 1 ELSE 0 END) AS moving_points
            FROM staging.stg_strava_stream_points
            WHERE activity_id IN ({ids_placeholder})
              AND distance_m IS NOT NULL
            GROUP BY activity_id, FLOOR(distance_m / 1000)
            ORDER BY activity_id, km_split
            """,  # noqa: S608
            ids_params,
        )
        for row in km_rows:
            aid = str(row["activity_id"])
            # Compute implied pace (min/km) from avg speed
            spd = row.get("avg_speed_kmh") or 0
            row["implied_pace"] = (
                f"{int(60 / spd)}:{int((60 / spd % 1) * 60):02d}" if spd > 0 else None
            )
            km_splits_by_activity.setdefault(aid, []).append(row)
        _logger.info("Km-splits chargés depuis DWH : %d", len(km_rows))
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Impossible de charger les km-splits depuis DWH : %s", exc)

    # ── 4. Distribution FC (zones d'intensité) ────────────────────────
    # Zones Garmin/Strava standard : Z1<60%, Z2=60-70%, Z3=70-80%, Z4=80-90%, Z5>90%
    # On approxime sur max HR (si disponible depuis stg_strava_activities)
    hr_zones_by_activity: dict[str, dict[str, Any]] = {}
    try:
        hr_rows = wh.query(
            f"""
            SELECT
                activity_id,
                max_heartrate     AS hr_max_activity,
                average_heartrate AS hr_avg_activity
            FROM staging.stg_strava_activities
            WHERE activity_id IN ({ids_placeholder})
            """,  # noqa: S608
            ids_params,
        )
        hr_meta = {str(r["activity_id"]): r for r in hr_rows}

        zone_rows = wh.query(
            f"""
            SELECT
                activity_id,
                COUNT(*) AS total_points,
                SUM(CASE WHEN heartrate_bpm IS NOT NULL THEN 1 ELSE 0 END) AS hr_points,
                ROUND(AVG(heartrate_bpm), 1)  AS hr_avg,
                ROUND(MIN(heartrate_bpm), 0)  AS hr_min,
                ROUND(MAX(heartrate_bpm), 0)  AS hr_max,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY heartrate_bpm), 0) AS hr_p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY heartrate_bpm), 0) AS hr_median,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY heartrate_bpm), 0) AS hr_p75
            FROM staging.stg_strava_stream_points
            WHERE activity_id IN ({ids_placeholder})
              AND heartrate_bpm IS NOT NULL
            GROUP BY activity_id
            """,  # noqa: S608
            ids_params,
        )
        for row in zone_rows:
            aid = str(row["activity_id"])
            meta = hr_meta.get(aid, {})
            hr_max_ref = meta.get("hr_max_activity") or row.get("hr_max") or 0
            zones: dict[str, Any] = dict(row)
            if hr_max_ref:
                zones["hr_max_reference"] = hr_max_ref
                zones["time_above_80pct"] = None  # computed below
                # Compute zone distribution from stream_points inline
                # (we avoid a 5th query — approximate from percentiles)
                zones["note"] = (
                    f"FC max référence : {hr_max_ref:.0f} bpm. "
                    f"Médiane : {row.get('hr_median', '?')} bpm "
                    f"({round(100 * (row.get('hr_median', 0) or 0) / hr_max_ref, 1) if hr_max_ref else '?'}% FCmax). "
                    f"P75 : {row.get('hr_p75', '?')} bpm "
                    f"({round(100 * (row.get('hr_p75', 0) or 0) / hr_max_ref, 1) if hr_max_ref else '?'}% FCmax)."
                )
            hr_zones_by_activity[aid] = zones
        _logger.info("Zones FC chargées depuis DWH : %d activité(s)", len(zone_rows))
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Impossible de charger les zones FC depuis DWH : %s", exc)

    has_detail = bool(
        laps_by_activity or stream_stats_by_activity or km_splits_by_activity
    )

    # ── 5. Segment efforts from Data Lake details.json ─────────────────
    segments_by_activity: dict[str, list[dict[str, Any]]] = {}
    try:
        dl = DataLake.from_env()
        for act in acts:
            act_id = str(act.get("id", ""))
            if not act_id:
                continue
            details_path = (
                dl.root
                / f"raw/strava/daily/{partition}/activities/{act_id}/details.json"
            )
            if not details_path.exists():
                continue
            import json as _json  # noqa: PLC0415

            details_data = _json.loads(details_path.read_text())
            segs = details_data.get("segment_efforts", [])
            notable = []
            for s in segs:
                pr_rank = s.get("pr_rank")
                # Include PR 1/2/3, skip null ranks unless effort is exceptional
                if pr_rank is None:
                    continue
                seg_info = s.get("segment", {})
                dist_m = s.get("distance") or 0
                elapsed_s = s.get("elapsed_time") or 0
                dist_km = dist_m / 1000
                # Compute pace on segment
                pace_str: str | None = None
                if dist_m > 0 and elapsed_s > 0:
                    pace_s = elapsed_s / dist_km
                    p_min, p_sec = divmod(int(pace_s), 60)
                    pace_str = f"{p_min}:{p_sec:02d}"
                notable.append(
                    {
                        "name": s.get("name", "?"),
                        "pr_rank": pr_rank,
                        "distance_km": round(dist_km, 2),
                        "elapsed_time_s": elapsed_s,
                        "moving_time_s": s.get("moving_time") or elapsed_s,
                        "pace_min_per_km": pace_str,
                        "average_grade": seg_info.get("average_grade"),
                        "average_heartrate": s.get("average_heartrate"),
                    }
                )
            # Sort: PR1 first, then PR2, then PR3+, by distance desc within rank
            notable.sort(key=lambda x: (x["pr_rank"], -x["distance_km"]))
            if notable:
                segments_by_activity[act_id] = notable
        _logger.info(
            "Segment efforts chargés depuis Data Lake : %d activité(s)",
            len(segments_by_activity),
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Impossible de charger les segments depuis Data Lake : %s", exc)

    has_detail = bool(
        laps_by_activity
        or stream_stats_by_activity
        or km_splits_by_activity
        or segments_by_activity
    )

    _logger.success(  # type: ignore[attr-defined]
        "✅ load_session_details — laps=%d act · splits=%d act · hr_zones=%d act · segments=%d act",
        len(laps_by_activity),
        len(km_splits_by_activity),
        len(hr_zones_by_activity),
        len(segments_by_activity),
    )
    return {
        "laps_by_activity": laps_by_activity,
        "stream_stats_by_activity": stream_stats_by_activity,
        "km_splits_by_activity": km_splits_by_activity,
        "hr_zones_by_activity": hr_zones_by_activity,
        "segments_by_activity": segments_by_activity,
        "has_detail": has_detail,
    }


@step(
    name="build_coaching_prompt",
    dependencies=["load_daily_data", "load_session_details"],
)
def build_coaching_prompt(
    activities: list[dict[str, Any]] | None = None,
    athlete: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    partition: str = "",
    activity_count: int = 0,
    # Injected from load_session_details
    laps_by_activity: dict[str, Any] | None = None,
    stream_stats_by_activity: dict[str, Any] | None = None,
    km_splits_by_activity: dict[str, Any] | None = None,
    hr_zones_by_activity: dict[str, Any] | None = None,
    segments_by_activity: dict[str, Any] | None = None,
    has_detail: bool = False,
) -> dict[str, Any]:
    """Construit le prompt utilisateur enrichi pour l'agent coach IA.

    Formate les activités du jour, le contexte récent (YTD, 4 semaines)
    et le profil athlète en sections textuelles lisibles par le LLM.
    Intègre les données de détail depuis le DWH (laps, km-splits, zones FC)
    quand elles sont disponibles.

    Args:
        activities:              Injecté depuis ``load_daily_data``.
        athlete:                 Injecté depuis ``load_daily_data``.
        stats:                   Injecté depuis ``load_daily_data``.
        partition:               Injecté depuis ``load_daily_data``.
        activity_count:          Injecté depuis ``load_daily_data``.
        laps_by_activity:        Injecté depuis ``load_session_details``.
        stream_stats_by_activity: Injecté depuis ``load_session_details``.
        km_splits_by_activity:   Injecté depuis ``load_session_details``.
        hr_zones_by_activity:    Injecté depuis ``load_session_details``.
        segments_by_activity:    Injecté depuis ``load_session_details``.
        has_detail:              Injecté depuis ``load_session_details``.

    Returns:
        ``{"user_prompt": str, "partition": str, "activity_count": int}``
    """
    ath = athlete or {}
    st = stats or {}
    acts = activities or []
    laps_map = laps_by_activity or {}
    km_map = km_splits_by_activity or {}
    hr_map = hr_zones_by_activity or {}
    seg_map = segments_by_activity or {}

    # ── Section athlète ───────────────────────────────────────────────
    name = f"{ath.get('firstname', '')} {ath.get('lastname', '')}".strip()
    weight = ath.get("weight")
    athlete_line = f"Athlète : {name}"
    if weight:
        athlete_line += f" · {weight} kg"

    # ── Section activités du jour ─────────────────────────────────────
    if acts:
        activity_lines = []
        for a in acts:
            sp = _sport_fr(a.get("sport_type", "?"))
            nm = a.get("name", "Sans nom")
            dist_m = a.get("distance", 0) or 0
            dist_km = dist_m / 1000
            dur_s = a.get("moving_time", 0) or 0
            elev = a.get("total_elevation_gain", 0) or 0
            hr_avg = a.get("average_heartrate")
            hr_max = a.get("max_heartrate")
            pace = (
                _fmt_pace(dist_m, dur_s)
                if a.get("sport_type") == "Run" and dist_m > 0
                else None
            )

            line = (
                f"- [{sp}] {nm}\n"
                f"  Distance : {dist_km:.2f} km | Durée : {_fmt_duration(dur_s)} | D+ : {elev:.0f} m"
            )
            if pace:
                line += f" | Allure : {pace} /km"
            if hr_avg:
                line += f" | FC moy : {hr_avg:.0f} bpm"
            if hr_max:
                line += f" · max : {hr_max:.0f} bpm"
            if a.get("suffer_score"):
                line += f" | Suffer score : {a['suffer_score']}"
            activity_lines.append(line)

            # ── Détail DWH : laps ──────────────────────────────────────
            act_id_str = str(a.get("id", ""))
            laps = laps_map.get(act_id_str, [])
            if laps:
                line += "\n  Laps :"
                for lap in laps:
                    lap_pace = lap.get("pace_min_per_km")
                    pace_str = ""
                    if lap_pace:
                        mins = int(lap_pace)
                        secs = int((lap_pace - mins) * 60)
                        pace_str = f" · {mins}:{secs:02d}/km"
                    lap_hr = lap.get("average_heartrate")
                    hr_str = f" · FC {lap_hr:.0f}" if lap_hr else ""
                    lap_d = lap.get("distance_km") or 0
                    line += (
                        f"\n    Lap {lap.get('lap_index', '?')} — "
                        f"{lap_d:.2f} km{pace_str}{hr_str}"
                    )
                # Replace last appended line with enriched version
                activity_lines[-1] = line

            # ── Détail DWH : km-splits ─────────────────────────────────
            splits = km_map.get(act_id_str, [])
            if splits:
                splits_parts = []
                for s in splits:
                    km_n = int(s.get("km_split") or 0)
                    spd = s.get("avg_speed_kmh") or 0
                    implied = s.get("implied_pace")
                    avg_hr = s.get("avg_hr")
                    avg_alt = s.get("avg_altitude_m")
                    parts = [f"km{km_n}"]
                    if implied:
                        parts.append(f"{implied}/km")
                    elif spd:
                        parts.append(f"{spd:.1f}km/h")
                    if avg_hr:
                        parts.append(f"FC{avg_hr:.0f}")
                    if avg_alt:
                        parts.append(f"alt{avg_alt:.0f}m")
                    splits_parts.append(" ".join(parts))
                activity_lines[-1] += "\n  Km-splits : " + " | ".join(splits_parts)

            # ── Détail DWH : zones FC ──────────────────────────────────
            hr_zone = hr_map.get(act_id_str)
            if hr_zone and hr_zone.get("note"):
                activity_lines[-1] += f"\n  FC analyse : {hr_zone['note']}"

        activities_section = "\n".join(activity_lines)
    else:
        activities_section = "(Aucune activité enregistrée ce jour — jour de repos)"

    # ── Section stats récentes ────────────────────────────────────────
    def _totals(key: str) -> str:
        t = st.get(key, {}) or {}
        return (
            f"{t.get('count', 0)} séances · "
            f"{(t.get('distance', 0) or 0) / 1000:.1f} km · "
            f"{_fmt_duration(t.get('moving_time', 0) or 0)}"
        )

    recent_section = (
        "4 dernières semaines :\n"
        f"  Course   : {_totals('recent_run_totals')}\n"
        f"  Vélo     : {_totals('recent_ride_totals')}\n"
        "YTD (année en cours) :\n"
        f"  Course   : {_totals('ytd_run_totals')}\n"
        f"  Vélo     : {_totals('ytd_ride_totals')}"
    )

    # ── Note sur la disponibilité des données granulaires ────────────
    detail_note = (
        "\n## Données granulaires (DWH)\n"
        "Les sections ci-dessus incluent, pour chaque activité :\n"
        "- Laps détaillés (allure + FC par lap)\n"
        "- Km-splits (allure, FC, altitude moyennes par km entier)\n"
        "- Analyse de fréquence cardiaque (médiane, P75 en % FCmax)\n"
        "Utilise ces données pour qualifier la régularité d'allure, les zones "
        "d'intensité cardio et l'effort par rapport au dénivelé."
        if has_detail
        else ""
    )

    # ── Section Segments & Records PR ────────────────────────────────
    segments_section = ""
    if seg_map:
        seg_lines: list[str] = []
        for act_id_str, segs in seg_map.items():
            if not segs:
                continue
            for s in segs:
                pr = s.get("pr_rank")
                name = s.get("name", "?")
                dist = s.get("distance_km", 0)
                pace = s.get("pace_min_per_km")
                grade = s.get("average_grade")
                hr = s.get("average_heartrate")

                rank_str = (
                    f"PR #{pr}"
                    if pr == 1
                    else f"{pr}e meilleur temps perso" if pr else "Effort notable"
                )
                parts = [f"[{rank_str}] {name} — {dist:.2f} km"]
                if pace:
                    parts.append(f"allure : {pace}/km")
                if grade is not None:
                    parts.append(f"pente moy : {grade:+.1f}%")
                if hr:
                    parts.append(f"FC moy : {hr:.0f} bpm")
                seg_lines.append("- " + " · ".join(parts))
        if seg_lines:
            segments_section = (
                "\n## Segments & Records PR\n"
                + "\n".join(seg_lines)
                + "\nPour chaque segment notable, commente la performance dans "
                "``segments_highlights`` (PR, contexte dénivelé, comparaison effort global)."
            )

    # ── Assemblage du prompt ──────────────────────────────────────────
    schema_str = json.dumps(_COACHING_SCHEMA, ensure_ascii=False, indent=2)
    user_prompt = (
        f"Date du rapport : {partition}\n"
        f"{athlete_line}\n\n"
        f"## Activités du {partition}\n"
        f"{activities_section}\n\n"
        f"## Contexte récent (stats all-time)\n"
        f"{recent_section}"
        f"{detail_note}"
        f"{segments_section}\n\n"
        f"---\nSchéma JSON attendu :\n{schema_str}"
    )

    _logger.info(
        "Prompt construit : %d chars · %d activité(s)",
        len(user_prompt),
        len(acts),
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ build_coaching_prompt — %d chars", len(user_prompt)
    )
    return {
        "user_prompt": user_prompt,
        "partition": partition,
        "activity_count": len(acts),
        # Pass DWH granular data forward to run_coaching_agent → save_coaching_report
        "km_splits_by_activity": km_map,
        "laps_by_activity": laps_map,
        "stream_stats_by_activity": stream_stats_by_activity or {},
        "segments_by_activity": seg_map,
    }


@step(
    name="run_coaching_agent",
    dependencies=["build_coaching_prompt"],
    timeout=180.0,
    retry_count=2,
    retry_delay=15.0,
)
def run_coaching_agent(
    user_prompt: str = "",
    partition: str = "",
    activity_count: int = 0,
    model: str = "default",
    # Granular DWH data — passed through to save_coaching_report for email rendering
    km_splits_by_activity: dict[str, Any] | None = None,
    laps_by_activity: dict[str, Any] | None = None,
    stream_stats_by_activity: dict[str, Any] | None = None,
    segments_by_activity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Soumet le rapport au coach IA et retourne l'analyse structurée.

    Utilise ``response_format={"type": "json_object"}`` pour garantir
    une réponse JSON parseable. Retry ×2 (délai 15 s) sur erreur réseau.

    Args:
        user_prompt:    Injecté depuis ``build_coaching_prompt``.
        partition:      Injecté depuis ``build_coaching_prompt``.
        activity_count: Injecté depuis ``build_coaching_prompt``.
        model:          Nom du modèle OpenAI. Injecté depuis ``initial_context``
                        ou ``"default"`` → env ``OPENAI_MODEL``.

    Returns:
        ``{"coaching": {...}, "model_used": str,
           "prompt_tokens": int, "completion_tokens": int, "total_tokens": int}``

    Raises:
        EnvironmentError: Si ``OPENAI_API_KEY`` manque.
        ValueError: Si la réponse n'est pas un JSON valide.
    """
    from openai import OpenAI  # noqa: PLC0415

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY non défini. Ajoutez-le dans votre .env.")

    resolved_model = (
        model
        if model and model != "default"
        else os.environ.get("OPENAI_MODEL", "gpt-4o")
    )
    timeout = float(os.environ.get("OPENAI_TIMEOUT", "120"))

    _logger.info(
        "Appel agent coach — modèle=%s · prompt=%d chars · %d activité(s)",
        resolved_model,
        len(user_prompt),
        activity_count,
    )

    client = OpenAI(api_key=api_key, timeout=timeout)
    response = client.chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    raw = response.choices[0].message.content or ""
    usage = response.usage

    _logger.info(
        "Réponse reçue — %d tokens (prompt=%d, completion=%d)",
        usage.total_tokens if usage else 0,
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )

    try:
        coaching: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Réponse LLM invalide (JSON) : {exc}\n" f"Extrait : {raw[:120]}"
        ) from exc

    # Injecter / compléter les métadonnées
    coaching.setdefault("metadata", {})
    coaching["metadata"].update(
        {
            "model_used": resolved_model,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "partition": partition,
            "activity_count": activity_count,
        }
    )
    # Garantir le champ date
    coaching.setdefault("date", partition)

    _logger.success(  # type: ignore[attr-defined]
        "✅ run_coaching_agent — modèle=%s · %d tokens",
        resolved_model,
        usage.total_tokens if usage else 0,
    )
    return {
        "coaching": coaching,
        "model_used": resolved_model,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
        # Pass DWH data through for email rendering
        "km_splits_by_activity": km_splits_by_activity or {},
        "laps_by_activity": laps_by_activity or {},
        "stream_stats_by_activity": stream_stats_by_activity or {},
        "segments_by_activity": segments_by_activity or {},
    }


_NOTIFY_TO = "thomas.awounfouet@yahoo.com"


def _build_coaching_html(data: dict[str, Any], date: str) -> str:
    """Construit le corps HTML du mail de coaching journalier."""
    session_type = data.get("session_type", "unknown")
    session_summary = data.get("session_summary", "")
    coach_message = data.get("coach_message", "")
    podcast_commentary = data.get("podcast_commentary", "")
    weekly_tip = data.get("weekly_tip", "")
    load = data.get("load_assessment", {})
    tomorrow = data.get("tomorrow_recommendation", {})
    acts_analysis = data.get("activities_analysis", [])
    meta = data.get("metadata", {})
    # DWH granular data embedded into coaching.json by save_coaching_report
    km_splits_by_activity: dict[str, list[dict[str, Any]]] = data.get(
        "_km_splits_by_activity", {}
    )
    laps_by_activity: dict[str, list[dict[str, Any]]] = data.get(
        "_laps_by_activity", {}
    )
    segments_by_activity: dict[str, list[dict[str, Any]]] = data.get(
        "_segments_by_activity", {}
    )
    # LLM-generated segment highlights (commentary per segment)
    llm_segments: list[dict[str, Any]] = data.get("segments_highlights", [])

    # ── Palette selon session_type ─────────────────────────────────────
    theme = {
        "rest_day": {
            "color": "#6b7280",
            "bg": "#f3f4f6",
            "emoji": "😴",
            "label": "Jour de repos",
        },
        "easy": {
            "color": "#16a34a",
            "bg": "#dcfce7",
            "emoji": "🟢",
            "label": "Séance légère",
        },
        "moderate": {
            "color": "#d97706",
            "bg": "#fef3c7",
            "emoji": "🟡",
            "label": "Séance modérée",
        },
        "hard": {
            "color": "#dc2626",
            "bg": "#fee2e2",
            "emoji": "🔴",
            "label": "Séance intensive",
        },
        "race": {
            "color": "#7c3aed",
            "bg": "#ede9fe",
            "emoji": "🏆",
            "label": "Compétition",
        },
        "mixed": {
            "color": "#0ea5e9",
            "bg": "#e0f2fe",
            "emoji": "🔵",
            "label": "Séance mixte",
        },
    }.get(
        session_type,
        {"color": "#374151", "bg": "#f9fafb", "emoji": "📋", "label": session_type},
    )

    accent = theme["color"]
    badge_bg = theme["bg"]
    emoji = theme["emoji"]
    label = theme["label"]

    load_color = {
        "none": "#6b7280",
        "light": "#16a34a",
        "moderate": "#d97706",
        "high": "#dc2626",
        "very_high": "#7c3aed",
    }.get(load.get("daily_load", "none"), "#6b7280")

    fatigue_color = {
        "none": "#16a34a",
        "low": "#84cc16",
        "moderate": "#d97706",
        "high": "#dc2626",
    }.get(load.get("fatigue_signal", "none"), "#6b7280")

    # ── Activités — tableau enrichi ────────────────────────────────────
    acts_rows = ""
    for a in acts_analysis:
        score = a.get("intensity_score", 0)
        bar_color = "#16a34a" if score <= 4 else "#d97706" if score <= 7 else "#dc2626"
        bar_width = score * 10
        pace_badge = (
            f"<br><small style='color:#6b7280'>⏱ {a['pace_min_per_km']} /km</small>"
            if a.get("pace_min_per_km")
            else ""
        )
        pace_profile = a.get("pace_profile") or ""
        hr_profile = a.get("hr_profile") or ""
        km_analysis = a.get("km_splits_analysis") or ""
        profiles_html = ""
        if pace_profile:
            profiles_html += (
                f'<br><small style="color:#6b7280">📈 {pace_profile}</small>'
            )
        if hr_profile:
            profiles_html += f'<br><small style="color:#6b7280">❤️ {hr_profile}</small>'

        detail_html = ""
        if km_analysis:
            detail_html = (
                f'<tr><td colspan="3" style="padding:0 8px 12px;font-size:12px;'
                f'color:#4b5563;line-height:1.6;background:#fafafa;border-bottom:1px solid #f3f4f6">'
                f"<em>{km_analysis}</em></td></tr>"
            )

        acts_rows += f"""
        <tr>
          <td style="padding:10px 8px;border-bottom:1px solid #f3f4f6;">
            <strong style="color:#111827">{a.get('name','?')}</strong>
            <span style="font-size:12px;color:#6b7280;margin-left:6px">{a.get('sport','')}</span>{pace_badge}{profiles_html}
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #f3f4f6;text-align:center;white-space:nowrap">
            <div style="background:#f3f4f6;border-radius:6px;height:10px;width:90px;display:inline-block;vertical-align:middle">
              <div style="background:{bar_color};width:{bar_width}%;height:10px;border-radius:6px"></div>
            </div>
            <span style="font-size:12px;color:{bar_color};margin-left:6px;font-weight:600">{score}/10</span>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #f3f4f6;font-size:13px;color:#374151">
            {a.get('quality_assessment','')}
          </td>
        </tr>{detail_html}"""

    acts_section = ""
    if acts_rows:
        acts_section = f"""
      <div style="margin-bottom:24px">
        <h3 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 12px">
          📊 Analyse des séances
        </h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f9fafb">
              <th style="padding:8px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Activité</th>
              <th style="padding:8px;text-align:center;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Intensité</th>
              <th style="padding:8px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Évaluation</th>
            </tr>
          </thead>
          <tbody>{acts_rows}</tbody>
        </table>
      </div>"""

    # ── Tableau km-splits (données DWH) ───────────────────────────────
    km_splits_section = ""
    all_splits: list[dict[str, Any]] = []
    for splits in km_splits_by_activity.values():
        all_splits.extend(splits)

    if all_splits:
        # Colour-code the pace bar: fastest km = green, slowest = red
        implied_paces = [
            s.get("implied_pace") for s in all_splits if s.get("implied_pace")
        ]

        def _pace_to_s(p: str) -> int:
            try:
                m, s = p.split(":")
                return int(m) * 60 + int(s)
            except Exception:  # noqa: BLE001
                return 9999

        pace_seconds = [_pace_to_s(p) for p in implied_paces] if implied_paces else [0]
        p_min = min(pace_seconds) if pace_seconds else 0
        p_max = max(pace_seconds) if pace_seconds else 1
        p_range = max(p_max - p_min, 1)

        split_rows = ""
        for s in all_splits:
            km_n = int(s.get("km_split") or 0)
            pace_str = s.get("implied_pace") or "—"
            avg_alt = s.get("avg_altitude_m")
            alt_str = f"{avg_alt:.0f} m" if avg_alt is not None else "—"
            avg_hr = s.get("avg_hr")
            hr_str = f"{avg_hr:.0f}" if avg_hr else "—"

            # Bar width: faster = wider green bar
            p_s = _pace_to_s(pace_str) if pace_str != "—" else p_max
            bar_pct = max(0, min(100, int(100 * (p_max - p_s) / p_range)))
            # Red → green gradient: slow = red (#dc2626), fast = green (#16a34a)
            g = int(bar_pct * 1.6)  # 0-160
            r = int((100 - bar_pct) * 1.6)  # 160-0
            bar_col = (
                f"rgb({min(r,220)},{min(g,163)},42)" if bar_pct < 100 else "#16a34a"
            )

            split_rows += f"""
            <tr>
              <td style="padding:5px 8px;border-bottom:1px solid #f9fafb;font-size:12px;
                         color:#374151;font-weight:600;text-align:center">km {km_n}</td>
              <td style="padding:5px 8px;border-bottom:1px solid #f9fafb;font-size:12px">
                <div style="display:flex;align-items:center;gap:6px">
                  <div style="background:#f3f4f6;border-radius:4px;height:8px;width:70px;flex-shrink:0">
                    <div style="background:{bar_col};width:{bar_pct}%;height:8px;border-radius:4px"></div>
                  </div>
                  <span style="color:#111827;font-weight:600">{pace_str}</span>
                </div>
              </td>
              <td style="padding:5px 8px;border-bottom:1px solid #f9fafb;font-size:12px;
                         color:#6b7280;text-align:center">{hr_str}</td>
              <td style="padding:5px 8px;border-bottom:1px solid #f9fafb;font-size:12px;
                         color:#6b7280;text-align:center">{alt_str}</td>
            </tr>"""

        km_splits_section = f"""
      <div style="margin-bottom:24px">
        <h3 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 12px">
          📉 Splits au kilomètre
        </h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f9fafb">
              <th style="padding:6px 8px;text-align:center;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Km</th>
              <th style="padding:6px 8px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Allure</th>
              <th style="padding:6px 8px;text-align:center;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">FC moy</th>
              <th style="padding:6px 8px;text-align:center;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Altitude</th>
            </tr>
          </thead>
          <tbody>{split_rows}</tbody>
        </table>
      </div>"""

    # ── Segments & Records PR ─────────────────────────────────────────
    # Build from LLM output (segments_highlights) enriched with raw DWH data
    segments_section = ""
    # Merge: build a name-indexed lookup from raw DWH data
    raw_segs_by_name: dict[str, dict[str, Any]] = {}
    for segs in segments_by_activity.values():
        for s in segs:
            raw_segs_by_name[s.get("name", "")] = s

    # Use LLM highlights if available, fall back to raw DWH segments filtered by PR 1/2
    seg_items: list[dict[str, Any]] = llm_segments or []
    if not seg_items:
        # Fallback: use raw DWH data directly (no LLM comment)
        for segs in segments_by_activity.values():
            for s in segs:
                if (s.get("pr_rank") or 99) <= 2:
                    seg_items.append(
                        {
                            "name": s.get("name", "?"),
                            "pr_rank": s.get("pr_rank"),
                            "distance_km": s.get("distance_km"),
                            "pace_min_per_km": s.get("pace_min_per_km"),
                            "comment": "",
                        }
                    )

    if seg_items:
        seg_rows = ""
        for seg in seg_items:
            pr = seg.get("pr_rank")
            if pr == 1:
                badge_bg_s = "#fef3c7"
                badge_color = "#92400e"
                badge_text = "🥇 PR #1"
            elif pr == 2:
                badge_bg_s = "#e0f2fe"
                badge_color = "#0c4a6e"
                badge_text = "🥈 #2 perso"
            elif pr == 3:
                badge_bg_s = "#f0fdf4"
                badge_color = "#14532d"
                badge_text = "🥉 #3 perso"
            else:
                badge_bg_s = "#f9fafb"
                badge_color = "#374151"
                badge_text = "Segment"

            name_s = seg.get("name", "?")
            dist_s = seg.get("distance_km")
            pace_s = seg.get("pace_min_per_km")
            comment_s = seg.get("comment", "")
            raw = raw_segs_by_name.get(name_s, {})
            grade_s = raw.get("average_grade")

            meta_parts = []
            if dist_s is not None:
                meta_parts.append(f"{dist_s:.2f} km")
            if pace_s:
                meta_parts.append(f"⏱ {pace_s}/km")
            if grade_s is not None:
                meta_parts.append(f"pente {grade_s:+.1f}%")
            meta_str = " · ".join(meta_parts)

            seg_rows += f"""
            <tr>
              <td style="padding:10px 8px;border-bottom:1px solid #f3f4f6;vertical-align:top">
                <span style="display:inline-block;background:{badge_bg_s};color:{badge_color};
                             font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px;
                             margin-bottom:4px">{badge_text}</span><br>
                <strong style="font-size:13px;color:#111827">{name_s}</strong>
                <span style="font-size:11px;color:#6b7280;margin-left:6px">{meta_str}</span>
              </td>
              <td style="padding:10px 8px;border-bottom:1px solid #f3f4f6;font-size:12px;
                         color:#4b5563;line-height:1.6;vertical-align:top">
                {comment_s}
              </td>
            </tr>"""

        segments_section = f"""
      <div style="margin-bottom:24px">
        <h3 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 12px">
          🏅 Segments &amp; Records
        </h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f9fafb">
              <th style="padding:8px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;width:40%">Segment</th>
              <th style="padding:8px;text-align:left;font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Analyse coach</th>
            </tr>
          </thead>
          <tbody>{seg_rows}</tbody>
        </table>
      </div>"""

    # ── Métadonnées ────────────────────────────────────────────────────
    model_used = meta.get("model_used", "")
    footer_model = f"🤖 {model_used}" if model_used else ""

    # ── Blocs conditionnels ────────────────────────────────────────────
    if weekly_tip:
        tip_section = (
            '<div style="margin-bottom:24px">'
            '<h3 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 12px">'
            "💡 Conseil de la semaine"
            "</h3>"
            '<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:14px 16px">'
            f'<p style="margin:0;font-size:13px;color:#92400e;line-height:1.6">{weekly_tip}</p>'
            "</div></div>"
        )
    else:
        tip_section = ""

    if podcast_commentary:
        # Replace newlines with <br> for HTML rendering
        podcast_html = podcast_commentary.replace("\n", "<br>")
        podcast_section = (
            '<div style="margin-bottom:24px">'
            '<h3 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 12px">'
            "🎙️ Analyse complète du coach"
            "</h3>"
            '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
            'padding:18px 20px">'
            f'<p style="margin:0;font-size:13px;color:#1e293b;line-height:1.8">{podcast_html}</p>'
            "</div></div>"
        )
    else:
        podcast_section = ""

    if coach_message:
        coach_section = (
            f'<div style="background:linear-gradient(135deg,{accent} 0%,{accent}cc 100%);'
            'border-radius:10px;padding:20px 22px;margin-bottom:8px">'
            '<p style="margin:0 0 6px;font-size:12px;color:rgba(255,255,255,.75);'
            'font-weight:600;text-transform:uppercase;letter-spacing:1px">'
            "💬 Message du coach"
            "</p>"
            '<p style="margin:0;font-size:14px;color:#fff;line-height:1.7;font-style:italic">'
            f"&ldquo;{coach_message}&rdquo;"
            "</p></div>"
        )
    else:
        coach_section = ""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Coaching Strava — {date}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

        <!-- ── Header ── -->
        <tr>
          <td style="background:{accent};border-radius:12px 12px 0 0;padding:28px 32px">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <p style="margin:0 0 4px;font-size:12px;color:rgba(255,255,255,.7);
                             text-transform:uppercase;letter-spacing:1px;font-weight:600">
                    Strava Daily Coaching
                  </p>
                  <h1 style="margin:0;font-size:24px;font-weight:700;color:#fff">
                    {emoji} {date}
                  </h1>
                </td>
                <td align="right">
                  <span style="display:inline-block;background:rgba(255,255,255,.2);
                               color:#fff;font-size:13px;font-weight:600;
                               padding:6px 14px;border-radius:20px">
                    {label}
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ── Body ── -->
        <tr>
          <td style="background:#fff;padding:28px 32px">

            <!-- Résumé de session -->
            <div style="background:{badge_bg};border-left:4px solid {accent};
                        border-radius:6px;padding:14px 16px;margin-bottom:24px">
              <p style="margin:0;font-size:14px;color:#374151;line-height:1.6">
                {session_summary}
              </p>
            </div>

            {acts_section}

            {km_splits_section}

            {segments_section}

            <!-- Charge & Fatigue -->
            <div style="margin-bottom:24px">
              <h3 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 12px">
                ⚡ Charge & Récupération
              </h3>
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="33%" style="padding-right:8px">
                    <div style="background:#f9fafb;border-radius:8px;padding:12px;text-align:center">
                      <p style="margin:0 0 4px;font-size:11px;color:#6b7280;
                                 text-transform:uppercase;font-weight:600">Charge du jour</p>
                      <p style="margin:0;font-size:16px;font-weight:700;color:{load_color}">
                        {load.get('daily_load','—').replace('_',' ').title()}
                      </p>
                    </div>
                  </td>
                  <td width="33%" style="padding-right:8px">
                    <div style="background:#f9fafb;border-radius:8px;padding:12px;text-align:center">
                      <p style="margin:0 0 4px;font-size:11px;color:#6b7280;
                                 text-transform:uppercase;font-weight:600">Signal fatigue</p>
                      <p style="margin:0;font-size:16px;font-weight:700;color:{fatigue_color}">
                        {load.get('fatigue_signal','—').title()}
                      </p>
                    </div>
                  </td>
                  <td width="33%">
                    <div style="background:#f9fafb;border-radius:8px;padding:12px;text-align:center">
                      <p style="margin:0 0 4px;font-size:11px;color:#6b7280;
                                 text-transform:uppercase;font-weight:600">Tendance semaine</p>
                      <p style="margin:0;font-size:13px;font-weight:600;color:#374151;line-height:1.3">
                        {load.get('weekly_trend','—')}
                      </p>
                    </div>
                  </td>
                </tr>
              </table>
            </div>

            <!-- Recommandation demain -->
            <div style="margin-bottom:24px">
              <h3 style="font-size:15px;font-weight:700;color:#111827;margin:0 0 12px">
                ➡️ Recommandation pour demain
              </h3>
              <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px">
                <p style="margin:0 0 6px;font-size:15px;font-weight:700;color:#15803d">
                  {tomorrow.get('type','—')}
                </p>
                <p style="margin:0;font-size:13px;color:#374151;line-height:1.6">
                  {tomorrow.get('rationale','')}
                </p>
              </div>
            </div>

            <!-- Conseil de la semaine -->
            {tip_section}

            <!-- Analyse complète du coach -->
            {podcast_section}

            <!-- Message du coach -->
            {coach_section}

          </td>
        </tr>

        <!-- ── Footer ── -->
        <tr>
          <td style="background:#f9fafb;border-radius:0 0 12px 12px;
                     padding:16px 32px;border-top:1px solid #e5e7eb">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:11px;color:#9ca3af">
                  PyWorkflow Engine — pipeline <em>ingestion-strava-daily-coaching</em>
                </td>
                <td align="right" style="font-size:11px;color:#9ca3af">
                  {footer_model}
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


@step(
    name="notify_coaching_by_email",
    dependencies=["save_coaching_report"],
)
def notify_coaching_by_email(
    output_path: str = "",
    partition: str = "",
    session_type: str = "rest_day",
    total_tokens: int = 0,
) -> dict[str, Any]:
    """Envoie le rapport de coaching LLM par e-mail au format HTML.

    Relit le coaching.json depuis le Data Lake (chemin fourni par
    ``save_coaching_report``) pour garantir que toutes les données sont
    disponibles, indépendamment de l'injection de contexte du moteur.

    Args:
        output_path:  Chemin Data Lake écrit (injecté depuis ``save_coaching_report``).
        partition:    Date analysée (injecté depuis ``save_coaching_report``).
        session_type: Type de journée (injecté depuis ``save_coaching_report``).
        total_tokens: Tokens consommés (injecté depuis ``save_coaching_report``).

    Returns:
        ``{"status": "sent"|"failed", "to": str, "subject": str}``
    """
    import json as _json  # noqa: PLC0415
    import os  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from pyconnectors.config import ConnectorConfig  # noqa: PLC0415
    from pyconnectors.services.factory import ConnectorFactory  # noqa: PLC0415

    # ── Lecture du rapport depuis le Data Lake ────────────────────────
    data: dict[str, Any] = {}
    if output_path and Path(output_path).exists():
        try:
            data = _json.loads(Path(output_path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Impossible de lire %s : %s", output_path, exc)

    date_label = partition or "N/A"

    # session_type injecté par save_coaching_report, mais on prend aussi data comme fallback
    resolved_session_type = data.get("session_type", session_type) or session_type

    session_icon = {
        "rest_day": "😴",
        "easy": "🟢",
        "moderate": "🟡",
        "hard": "🔴",
        "race": "🏆",
        "mixed": "🔵",
    }.get(resolved_session_type, "📋")

    act_count = data.get("metadata", {}).get("activity_count", 0)
    subject = (
        f"[Strava Coaching] {session_icon} {date_label} — "
        f"{act_count} activité(s) · {resolved_session_type}"
    )

    html_body = _build_coaching_html(data, date_label)

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

    to_addr = os.environ.get("NOTIFY_EMAIL", _NOTIFY_TO)
    connector = ConnectorFactory.create("email.smtp", config=smtp_config)
    result = connector.safe_execute(
        to_addr=to_addr,
        subject=subject,
        body=html_body,
        html=True,
    )

    if not result.success:
        _logger.warning("Échec envoi email coaching : %s", result.error)
        return {
            "status": "failed",
            "to": to_addr,
            "subject": subject,
            "error": result.error,
        }

    _logger.success(  # type: ignore[attr-defined]
        "✅ notify_coaching_by_email — envoyé à %s", to_addr
    )
    return {"status": "sent", "to": to_addr, "subject": subject}


@step(name="save_coaching_report", dependencies=["run_coaching_agent"])
def save_coaching_report(
    coaching: dict[str, Any] | None = None,
    model_used: str = "",
    total_tokens: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    partition: str = "",
    # DWH granular data passed through from run_coaching_agent
    km_splits_by_activity: dict[str, Any] | None = None,
    laps_by_activity: dict[str, Any] | None = None,
    segments_by_activity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Écrit le rapport de coaching dans le Data Lake et affiche un résumé.

    Chemin de sortie :
    ``llm/strava/daily_coaching/{partition}/coaching.json``

    Embed les données granulaires DWH (km-splits, laps, segments) sous les
    clés ``_km_splits_by_activity``, ``_laps_by_activity`` et
    ``_segments_by_activity`` pour que ``_build_coaching_html`` puisse les
    relire sans dépendre du contexte d'injection du moteur.

    Args:
        coaching:              Injecté depuis ``run_coaching_agent``.
        model_used:            Injecté depuis ``run_coaching_agent``.
        total_tokens:          Injecté depuis ``run_coaching_agent``.
        prompt_tokens:         Injecté depuis ``run_coaching_agent``.
        completion_tokens:     Injecté depuis ``run_coaching_agent``.
        partition:             Injecté depuis ``build_coaching_prompt``.
        km_splits_by_activity: Injecté depuis ``run_coaching_agent`` (passthrough DWH).
        laps_by_activity:      Injecté depuis ``run_coaching_agent`` (passthrough DWH).
        segments_by_activity:  Injecté depuis ``run_coaching_agent`` (passthrough DWH).

    Returns:
        ``{"output_path": str, "partition": str, "total_tokens": int,
           "session_type": str}``
    """
    dl = DataLake.from_env()
    data = dict(coaching or {})
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    date = partition or settings.today()

    # Embed granular data so notify_coaching_by_email can read them from the file
    if km_splits_by_activity:
        data["_km_splits_by_activity"] = km_splits_by_activity
    if laps_by_activity:
        data["_laps_by_activity"] = laps_by_activity
    if segments_by_activity:
        data["_segments_by_activity"] = segments_by_activity

    out_dir = f"llm/strava/daily_coaching/{date}"
    dest = dl.write_json_file(out_dir, "coaching.json", data)
    _logger.info("Rapport coaching écrit : %s", dest)

    # ── Résumé console ────────────────────────────────────────────────
    session_type = data.get("session_type", "?")
    summary = data.get("session_summary", "")
    load = data.get("load_assessment", {})
    tomorrow = data.get("tomorrow_recommendation", {})
    tip = data.get("weekly_tip", "")
    coach_msg = data.get("coach_message", "")

    session_icon = {
        "rest_day": "😴",
        "easy": "🟢",
        "moderate": "🟡",
        "hard": "🔴",
        "race": "🏆",
        "mixed": "🔵",
    }.get(session_type, "📋")

    _logger.info("─" * 60)
    _logger.info("🏃 COACHING JOURNALIER — %s", date)
    _logger.info("─" * 60)
    _logger.info("%s Type de journée : %s", session_icon, session_type.upper())
    _logger.info("   %s", summary)

    acts_analysis = data.get("activities_analysis", [])
    if acts_analysis:
        _logger.info("\n📊 Analyse des séances :")
        for a in acts_analysis:
            score = a.get("intensity_score", "?")
            _logger.info(
                "   [%s/10] %s — %s",
                score,
                a.get("sport", a.get("name", "?")),
                a.get("quality_assessment", ""),
            )

    _logger.info(
        "\n⚡ Charge : %s | Fatigue : %s",
        load.get("daily_load", "?"),
        load.get("fatigue_signal", "?"),
    )
    _logger.info("   Tendance semaine : %s", load.get("weekly_trend", ""))

    _logger.info("\n➡️  Demain : %s", tomorrow.get("type", "?"))
    _logger.info("   %s", tomorrow.get("rationale", ""))

    if tip:
        _logger.info("\n💡 Conseil de la semaine : %s", tip)

    if coach_msg:
        _logger.info("\n💬 Message du coach :")
        _logger.info("   %s", coach_msg)

    _logger.info("─" * 60)
    _logger.info(
        "🤖 %s · %d tokens (prompt=%d, completion=%d)",
        model_used,
        total_tokens,
        prompt_tokens,
        completion_tokens,
    )

    _logger.success("✅ save_coaching_report — %s", dest)  # type: ignore[attr-defined]
    return {
        "output_path": str(dest),
        "partition": date,
        "total_tokens": total_tokens,
        "session_type": session_type,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="llm-strava-daily-coaching",
    version="1.0.0",
    description=(
        "Coaching journalier Strava via agent IA GPT-4o. "
        "Pipeline : lecture snapshot journalier → chargement détails DWH → "
        "construction prompt enrichi (laps + km-splits + zones FC) → "
        "agent IA (JSON structuré, retry ×2) → sauvegarde datalake → notification email HTML."
    ),
    steps=[
        load_daily_data,
        load_session_details,
        build_coaching_prompt,
        run_coaching_agent,
        save_coaching_report,
        notify_coaching_by_email,
    ],
)
def coach_strava_daily() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    load_daily_data()
    load_session_details()
    build_coaching_prompt()
    run_coaching_agent()
    save_coaching_report()
    notify_coaching_by_email()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse  # noqa: PLC0415

    from dotenv import load_dotenv  # noqa: PLC0415
    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.storage import SQLiteStorage  # noqa: PLC0415

    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Coaching journalier Strava via agent IA"
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date à analyser (défaut : aujourd'hui).",
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Modèle OpenAI (défaut : OPENAI_MODEL env ou gpt-4o).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Charge les données + affiche le prompt sans appeler l'API.",
    )
    args = parser.parse_args()

    configure_platform_logging()

    from datetime import UTC, datetime  # noqa: PLC0415
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    today = args.date or settings.today()
    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-4o")

    if args.dry_run:
        dl = DataLake.from_env()
        # Simuler load_daily_data + load_session_details + build_coaching_prompt
        data = load_daily_data(partition=today)
        details = load_session_details(
            activities=data["activities"],
            partition=data["partition"],
        )
        ctx = build_coaching_prompt(
            activities=data["activities"],
            athlete=data["athlete"],
            stats=data["stats"],
            partition=data["partition"],
            activity_count=data["activity_count"],
            laps_by_activity=details["laps_by_activity"],
            stream_stats_by_activity=details["stream_stats_by_activity"],
            km_splits_by_activity=details["km_splits_by_activity"],
            hr_zones_by_activity=details["hr_zones_by_activity"],
            segments_by_activity=details.get("segments_by_activity", {}),
            has_detail=details["has_detail"],
        )
        print("\n" + "═" * 60)  # noqa: T201
        print("SYSTEM PROMPT :")  # noqa: T201
        print(_SYSTEM_PROMPT)  # noqa: T201
        print("─" * 60)  # noqa: T201
        print(f"USER PROMPT ({len(ctx['user_prompt'])} chars) :")  # noqa: T201
        print(ctx["user_prompt"][:3000])  # noqa: T201
        if len(ctx["user_prompt"]) > 3000:
            print(
                f"\n[... {len(ctx['user_prompt']) - 3000} chars tronqués]"
            )  # noqa: T201
        print("═" * 60)  # noqa: T201
        print("\n✅ Dry-run OK — aucun appel API effectué")  # noqa: T201
    else:
        engine = WorkflowEngine(storage=SQLiteStorage(database_path="workflow.db"))
        result = engine.run_with_storage(
            coach_strava_daily.build(),
            initial_context={"partition": today, "model": model},
        )
        for step_run in result.step_runs:
            ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
            print(
                f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
            )  # noqa: T201
        print(f"\nStatut final : {result.status}")  # noqa: T201
