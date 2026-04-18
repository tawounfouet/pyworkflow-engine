# filepath: jobs/llm/strava_athlete_analysis/analyze_athlete.py
"""
LLM — Analyse du profil athlète Strava via GPT-4o.

Lit les données brutes ingérées par ``jobs.ingestion.strava.extract_strava``
depuis le Data Lake, prépare un contexte enrichi puis le soumet à GPT-4o
pour obtenir une analyse structurée de coach sportif.

Cible :
    datalake://llm/strava/athlete_analysis/{date}/analysis.json

Pipeline :
    load_athlete_data       (lecture datalake : athlete + stats + activities)
        ↓
    prepare_athlete_context (agrégats + résumé textuel pour le prompt)
        ↓
    analyze_with_llm        (appel GPT-4o, réponse JSON structurée)
        ↓
    save_analysis           (écriture datalake + affichage résumé)

Variables d'environnement :
    OPENAI_API_KEY   : Clé API OpenAI (obligatoire)
    OPENAI_MODEL     : Modèle à utiliser (défaut : gpt-4o)
    OPENAI_TIMEOUT   : Timeout en secondes (défaut : 120)
    DATALAKE_PATH    : Répertoire racine du Data Lake (défaut : ./data/datalake)

Usage CLI :
    python -m jobs.llm.strava_athlete_analysis.analyze_athlete
    python -m jobs.llm.strava_athlete_analysis.analyze_athlete --date 2026-04-12
    python -m jobs.llm.strava_athlete_analysis.analyze_athlete --model gpt-4o-mini
    python -m jobs.llm.strava_athlete_analysis.analyze_athlete --dry-run
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

from jobs.shared.datalake import DataLake

_logger = get_logger("jobs.llm.strava_athlete_analysis")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _latest_partition(dl: DataLake, prefix: str) -> str | None:
    """Retourne la partition la plus récente pour un préfixe donné."""
    partitions = dl.list_partitions(prefix)
    return partitions[-1] if partitions else None


def _fmt_distance(meters: float) -> str:
    """Formate une distance en mètres → km arrondi à 1 décimale."""
    return f"{meters / 1000:.1f} km"


def _fmt_duration(seconds: int | float) -> str:
    """Formate une durée en secondes → Xh Ym ou Xm."""
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _sport_label(sport_type: str) -> str:
    """Traduit les sport_type Strava en français."""
    labels = {
        "Run": "Course à pied",
        "Ride": "Vélo",
        "Swim": "Natation",
        "Walk": "Marche",
        "Yoga": "Yoga",
        "Workout": "Musculation / Cross-training",
        "Pilates": "Pilates",
        "WeightTraining": "Haltérophilie",
        "Hike": "Randonnée",
        "AlpineSki": "Ski alpin",
        "NordicSki": "Ski nordique",
        "VirtualRide": "Vélo virtuel",
        "VirtualRun": "Course virtuelle",
        "Kayaking": "Kayak",
        "StandUpPaddling": "Stand-up paddle",
    }
    return labels.get(sport_type, sport_type)


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="load_athlete_data", timeout=30.0)
def load_athlete_data(
    partition: str = "latest",
) -> dict[str, Any]:
    """Lit les données brutes Strava depuis le Data Lake.

    Charge athlete, stats et activities pour la partition demandée.
    Si ``partition="latest"``, détecte automatiquement la plus récente.

    Args:
        partition: Date de partition (``YYYY-MM-DD``) ou ``"latest"``.
                   Injecté depuis ``initial_context``.

    Returns:
        ``{"athlete": {...}, "stats": {...}, "activities": [...],
           "partition": "YYYY-MM-DD", "activity_count": int}``

    Raises:
        FileNotFoundError: Si aucune partition Strava n'existe dans le Data Lake.
        ValueError: Si les données athlete ou stats sont vides.
    """
    dl = DataLake.from_env()

    # ── Résolution de la partition ────────────────────────────────────
    if partition == "latest":
        resolved = _latest_partition(dl, "raw/strava/athlete")
        if not resolved:
            raise FileNotFoundError(
                "Aucune partition Strava trouvée dans le Data Lake. "
                "Lancez d'abord : python -m jobs.ingestion.strava.extract_strava"
            )
        _logger.info("Partition auto-détectée : %s", resolved)
    else:
        resolved = partition
        _logger.info("Partition demandée : %s", resolved)

    # ── Lecture athlete ───────────────────────────────────────────────
    athlete_path = f"raw/strava/athlete/{resolved}"
    athlete_raw = dl.read_json(athlete_path)
    # write_json stocke une liste ; athlete est un dict unique → on l'extrait
    athlete: dict[str, Any] = (
        athlete_raw[0] if isinstance(athlete_raw, list) else athlete_raw
    )
    if not athlete:
        raise ValueError(f"Données athlete vides pour la partition {resolved}")
    _logger.info(
        "Athlete : %s %s (id=%s)",
        athlete.get("firstname", "?"),
        athlete.get("lastname", "?"),
        athlete.get("id", "?"),
    )

    # ── Lecture stats ─────────────────────────────────────────────────
    stats_path = f"raw/strava/stats/{resolved}"
    stats_raw = dl.read_json(stats_path)
    stats: dict[str, Any] = stats_raw[0] if isinstance(stats_raw, list) else stats_raw
    if not stats:
        raise ValueError(f"Données stats vides pour la partition {resolved}")
    _logger.info(
        "Stats : %d km all-time run, %d km all-time ride",
        (stats.get("all_run_totals", {}).get("distance", 0) or 0) // 1000,
        (stats.get("all_ride_totals", {}).get("distance", 0) or 0) // 1000,
    )

    # ── Lecture activities ────────────────────────────────────────────
    activities_path = f"raw/strava/activities/{resolved}"
    activities: list[dict[str, Any]] = dl.read_json(activities_path)
    _logger.info("Activities : %d activités chargées", len(activities))

    _logger.success(  # type: ignore[attr-defined]
        "✅ load_athlete_data — partition=%s · %d activités",
        resolved,
        len(activities),
    )
    return {
        "athlete": athlete,
        "stats": stats,
        "activities": activities,
        "partition": resolved,
        "activity_count": len(activities),
    }


@step(name="prepare_athlete_context", dependencies=["load_athlete_data"])
def prepare_athlete_context(
    athlete: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    activities: list[dict[str, Any]] | None = None,
    partition: str = "",
    activity_count: int = 0,
) -> dict[str, Any]:
    """Prépare le contexte textuel enrichi pour le prompt LLM.

    Calcule des agrégats (répartition sports, activités récentes, records)
    et formate chaque section en texte lisible par le LLM.

    Args:
        athlete:        Injecté depuis ``load_athlete_data``.
        stats:          Injecté depuis ``load_athlete_data``.
        activities:     Injecté depuis ``load_athlete_data``.
        partition:      Injecté depuis ``load_athlete_data``.
        activity_count: Injecté depuis ``load_athlete_data``.

    Returns:
        ``{"athlete_section": str, "stats_section": str,
           "activities_summary_section": str, "recent_activities_section": str,
           "schema_section": str, "activity_count": int, "partition": str}``
    """
    ath = athlete or {}
    st = stats or {}
    acts = activities or []

    # ── Section athlete ───────────────────────────────────────────────
    bikes = ath.get("bikes") or []
    shoes = ath.get("shoes") or []
    gear_lines = []
    for b in bikes:
        km = (b.get("converted_distance") or b.get("distance", 0)) / (
            1000 if b.get("distance", 0) > 1000 else 1
        )
        gear_lines.append(f"  - Vélo : {b.get('name', '?')} ({km:.0f} km)")
    for s in shoes:
        km = (s.get("converted_distance") or s.get("distance", 0)) / (
            1000 if s.get("distance", 0) > 1000 else 1
        )
        gear_lines.append(f"  - Chaussures : {s.get('name', '?')} ({km:.0f} km)")

    athlete_section = (
        f"Nom : {ath.get('firstname', '')} {ath.get('lastname', '')}\n"
        f"Ville : {ath.get('city', 'N/A')}, {ath.get('country', 'N/A')}\n"
        f"Sexe : {ath.get('sex', 'N/A')} | Poids : {ath.get('weight') or 'N/A'} kg\n"
        f"Abonnés : {ath.get('follower_count', 0)} | Abonnements : {ath.get('friend_count', 0)}\n"
        f"Clubs : {len(ath.get('clubs') or [])}\n"
        f"Bio : {ath.get('bio') or 'Aucune bio'}\n"
        + ("\nÉquipement :\n" + "\n".join(gear_lines) if gear_lines else "")
    )
    _logger.info("Section athlete préparée (%d chars)", len(athlete_section))

    # ── Section stats ─────────────────────────────────────────────────
    def _totals_line(label: str, key: str) -> str:
        t = st.get(key, {}) or {}
        dist = _fmt_distance(t.get("distance", 0) or 0)
        dur = _fmt_duration(t.get("moving_time", 0) or 0)
        elev = f"{t.get('elevation_gain', 0) or 0:.0f} m D+"
        cnt = t.get("count", 0) or 0
        return f"  {label}: {cnt} activités · {dist} · {dur} · {elev}"

    stats_section = (
        "All-time :\n"
        + _totals_line("Course", "all_run_totals")
        + "\n"
        + _totals_line("Vélo  ", "all_ride_totals")
        + "\n"
        + _totals_line("Natation", "all_swim_totals")
        + "\n"
        + f"\nRecord distance vélo : {_fmt_distance(st.get('biggest_ride_distance') or 0)}\n"
        + f"Record dénivelé vélo : {st.get('biggest_climb_elevation_gain') or 0:.0f} m\n"
        + "\nYTD (année en cours) :\n"
        + _totals_line("Course", "ytd_run_totals")
        + "\n"
        + _totals_line("Vélo  ", "ytd_ride_totals")
        + "\n"
        + _totals_line("Natation", "ytd_swim_totals")
        + "\n"
        + "\nRécent (4 semaines) :\n"
        + _totals_line("Course", "recent_run_totals")
        + "\n"
        + _totals_line("Vélo  ", "recent_ride_totals")
    )
    _logger.info("Section stats préparée (%d chars)", len(stats_section))

    # ── Résumé activités ──────────────────────────────────────────────
    sport_counter = Counter(a.get("sport_type", "Unknown") for a in acts)
    total = len(acts)
    sport_lines = [
        f"  - {_sport_label(sp)}: {cnt} activités ({cnt / total * 100:.1f}%)"
        for sp, cnt in sport_counter.most_common(8)
    ]

    # Première et dernière activité
    sorted_acts = sorted(acts, key=lambda a: a.get("start_date_local", ""))
    first = sorted_acts[0] if sorted_acts else {}
    last = sorted_acts[-1] if sorted_acts else {}

    activities_summary_section = (
        f"Total : {total} activités\n"
        f"Période : {first.get('start_date_local', '?')[:10]} → {last.get('start_date_local', '?')[:10]}\n\n"
        "Répartition par sport :\n" + "\n".join(sport_lines)
    )
    _logger.info("Résumé activités préparé (%d chars)", len(activities_summary_section))

    # ── Activités récentes (30 derniers jours) ─────────────────────────
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    cutoff_date = partition if partition else settings.today()
    try:
        cutoff_dt = datetime.fromisoformat(cutoff_date)
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
    except ValueError:
        cutoff_str = cutoff_date

    recent = [
        a for a in acts if a.get("start_date_local", "")[:10] >= cutoff_str[:7] + "-01"
    ][
        -30:
    ]  # garde au max 30 activités récentes

    if recent:
        recent_lines = []
        for a in sorted(
            recent, key=lambda x: x.get("start_date_local", ""), reverse=True
        )[:20]:
            d = a.get("start_date_local", "")[:10]
            sp = _sport_label(a.get("sport_type", "?"))
            name = a.get("name", "?")[:40]
            dist = _fmt_distance(a.get("distance", 0) or 0)
            dur = _fmt_duration(a.get("moving_time", 0) or 0)
            elev = f"{a.get('total_elevation_gain', 0) or 0:.0f}m D+"
            hr = (
                f" · FC moy {a.get('average_heartrate'):.0f}"
                if a.get("average_heartrate")
                else ""
            )
            recent_lines.append(f"  [{d}] {sp} — {name} : {dist}, {dur}, {elev}{hr}")
        recent_activities_section = "\n".join(recent_lines)
    else:
        recent_activities_section = "Aucune activité récente dans cette période."
    _logger.info("Activités récentes : %d activités formatées", len(recent))

    # ── Schéma JSON ───────────────────────────────────────────────────
    from jobs.llm.strava_athlete_analysis.prompts import (
        ANALYSIS_SCHEMA,
    )  # noqa: PLC0415

    schema_section = json.dumps(ANALYSIS_SCHEMA, ensure_ascii=False, indent=2)

    _logger.success(  # type: ignore[attr-defined]
        "✅ prepare_athlete_context — contexte prêt (%d activités, partition=%s)",
        total,
        partition,
    )
    return {
        "athlete_section": athlete_section,
        "stats_section": stats_section,
        "activities_summary_section": activities_summary_section,
        "recent_activities_section": recent_activities_section,
        "schema_section": schema_section,
        "activity_count": total,
        "partition": partition,
    }


@step(
    name="analyze_with_llm",
    dependencies=["prepare_athlete_context"],
    timeout=180.0,
    retry_count=2,
    retry_delay=15.0,
)
def analyze_with_llm(
    athlete_section: str = "",
    stats_section: str = "",
    activities_summary_section: str = "",
    recent_activities_section: str = "",
    schema_section: str = "",
    activity_count: int = 0,
    partition: str = "",
    model: str = "default",
) -> dict[str, Any]:
    """Soumet le contexte athlète à GPT-4o et retourne l'analyse structurée.

    Utilise ``response_format={"type": "json_object"}`` pour garantir
    une réponse JSON parseable. Retry ×2 (délai 15 s) en cas d'erreur réseau.

    Args:
        athlete_section:            Injecté depuis ``prepare_athlete_context``.
        stats_section:              Injecté depuis ``prepare_athlete_context``.
        activities_summary_section: Injecté depuis ``prepare_athlete_context``.
        recent_activities_section:  Injecté depuis ``prepare_athlete_context``.
        schema_section:             Injecté depuis ``prepare_athlete_context``.
        activity_count:             Injecté depuis ``prepare_athlete_context``.
        partition:                  Injecté depuis ``prepare_athlete_context``.
        model:                      Nom du modèle OpenAI. Injecté depuis
                                    ``initial_context`` ou ``"default"`` → env.

    Returns:
        ``{"analysis": {...}, "model_used": str, "prompt_tokens": int,
           "completion_tokens": int, "total_tokens": int}``

    Raises:
        EnvironmentError: Si ``OPENAI_API_KEY`` n'est pas défini.
        ValueError: Si la réponse n'est pas un JSON valide.
    """
    from openai import OpenAI  # noqa: PLC0415

    from jobs.llm.strava_athlete_analysis.prompts import (  # noqa: PLC0415
        SYSTEM_PROMPT,
        USER_PROMPT_TEMPLATE,
    )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY non défini. "
            "Ajoutez-le dans votre fichier .env ou variables d'environnement."
        )

    resolved_model = (
        model
        if model and model != "default"
        else os.environ.get("OPENAI_MODEL", "gpt-4o")
    )
    timeout = float(os.environ.get("OPENAI_TIMEOUT", "120"))

    user_prompt = USER_PROMPT_TEMPLATE.format(
        athlete_section=athlete_section,
        stats_section=stats_section,
        activity_count=activity_count,
        activities_summary_section=activities_summary_section,
        recent_activities_section=recent_activities_section,
        schema_section=schema_section,
    )

    _logger.info(
        "Appel LLM — modèle=%s · prompt=%d chars",
        resolved_model,
        len(user_prompt),
    )

    client = OpenAI(api_key=api_key, timeout=timeout)

    response = client.chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )

    raw_content = response.choices[0].message.content or ""
    usage = response.usage

    _logger.info(
        "Réponse LLM reçue — %d tokens (prompt=%d, completion=%d)",
        usage.total_tokens if usage else 0,
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )

    try:
        analysis = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"La réponse LLM n'est pas un JSON valide : {exc}\n"
            f"Contenu reçu (100 premiers chars) : {raw_content[:100]}"
        ) from exc

    # Injecter les métadonnées d'analyse
    analysis.setdefault("analysis_metadata", {})
    analysis["analysis_metadata"].update(
        {
            "data_partition": partition,
            "activities_analyzed": activity_count,
            "model_used": resolved_model,
            "generated_at": datetime.now(tz=UTC).isoformat(),
        }
    )

    _logger.success(  # type: ignore[attr-defined]
        "✅ analyze_with_llm — modèle=%s · %d tokens · analyse générée",
        resolved_model,
        usage.total_tokens if usage else 0,
    )
    return {
        "analysis": analysis,
        "model_used": resolved_model,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }


@step(name="save_analysis", dependencies=["analyze_with_llm"])
def save_analysis(
    analysis: dict[str, Any] | None = None,
    model_used: str = "",
    total_tokens: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    partition: str = "",
) -> dict[str, Any]:
    """Écrit l'analyse JSON dans le Data Lake et affiche un résumé console.

    Chemin de sortie :
    ``llm/strava/athlete_analysis/{partition}/analysis.json``

    Args:
        analysis:          Injecté depuis ``analyze_with_llm``.
        model_used:        Injecté depuis ``analyze_with_llm``.
        total_tokens:      Injecté depuis ``analyze_with_llm``.
        prompt_tokens:     Injecté depuis ``analyze_with_llm``.
        completion_tokens: Injecté depuis ``analyze_with_llm``.
        partition:         Injecté depuis ``prepare_athlete_context``.

    Returns:
        ``{"output_path": str, "rows_written": int, "total_tokens": int}``
    """
    dl = DataLake.from_env()
    data = analysis or {}
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    date = partition or settings.today()

    out_dir = f"llm/strava/athlete_analysis/{date}"
    dest_file = dl.write_json_file(out_dir, "analysis.json", data)
    _logger.info("Analyse écrite : %s", dest_file)

    # ── Résumé console ─────────────────────────────────────────────────
    summary = data.get("athlete_summary", {})
    insights = data.get("performance_insights", [])
    strengths = data.get("strengths", [])
    improvements = data.get("areas_for_improvement", [])
    goals = data.get("next_goals", [])
    coach_msg = data.get("coach_message", "")

    _logger.info("─" * 60)
    _logger.info("📊  ANALYSE ATHLÈTE STRAVA — %s", date)
    _logger.info("─" * 60)
    _logger.info("🏃 %s", summary.get("profile_headline", ""))
    _logger.info(
        "   Sport principal : %s | Actif depuis : %s | %d activités",
        summary.get("primary_sport", ""),
        summary.get("active_since", ""),
        summary.get("total_activities", 0),
    )

    if insights:
        _logger.info("\n🔍 Insights clés :")
        for ins in insights:
            icon = (
                "✅"
                if ins.get("sentiment") == "positive"
                else ("⚠️" if ins.get("sentiment") == "improvement_needed" else "ℹ️")
            )
            _logger.info(
                "   %s %s — %s", icon, ins.get("title", ""), ins.get("detail", "")
            )

    if strengths:
        _logger.info("\n💪 Points forts :")
        for s in strengths:
            _logger.info("   • %s", s)

    if improvements:
        _logger.info("\n📈 Axes de progression :")
        for imp in improvements:
            _logger.info(
                "   • %s → %s", imp.get("area", ""), imp.get("recommendation", "")
            )

    if goals:
        _logger.info("\n🎯 Objectifs suggérés :")
        for g in goals:
            _logger.info("   • [%s] %s", g.get("timeframe", ""), g.get("goal", ""))

    if coach_msg:
        _logger.info("\n💬 Message du coach :")
        _logger.info("   %s", coach_msg)

    _logger.info("─" * 60)
    _logger.info(
        "🤖 Modèle : %s | Tokens : %d (prompt=%d, completion=%d)",
        model_used,
        total_tokens,
        prompt_tokens,
        completion_tokens,
    )

    _logger.success(  # type: ignore[attr-defined]
        "✅ save_analysis — écrit dans %s", dest_file
    )
    return {
        "output_path": str(dest_file),
        "rows_written": 1,
        "total_tokens": total_tokens,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="llm-strava-athlete-analysis",
    version="1.0.0",
    description=(
        "Analyse du profil athlète Strava via GPT-4o. "
        "Pipeline : lecture datalake → préparation contexte → appel LLM "
        "→ sauvegarde analyse JSON partitionnée par date."
    ),
    steps=[
        load_athlete_data,
        prepare_athlete_context,
        analyze_with_llm,
        save_analysis,
    ],
)
def analyze_strava_athlete() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    load_athlete_data()
    prepare_athlete_context()
    analyze_with_llm()
    save_analysis()


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
        description="Analyse du profil athlète Strava via LLM (GPT-4o)"
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "Date de partition Strava à analyser (défaut : dernière partition disponible). "
            "Exemple : --date 2026-04-12"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Modèle OpenAI à utiliser (défaut : OPENAI_MODEL env ou gpt-4o).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Prépare le contexte et affiche le prompt sans appeler l'API OpenAI. "
            "Utile pour valider les données avant de consommer des tokens."
        ),
    )
    args = parser.parse_args()

    configure_platform_logging()

    if args.dry_run:
        # ── Mode dry-run : charge les données + affiche le prompt ────
        from jobs.llm.strava_athlete_analysis.prompts import (  # noqa: PLC0415
            SYSTEM_PROMPT,
            USER_PROMPT_TEMPLATE,
        )

        dl = DataLake.from_env()
        partition = args.date or _latest_partition(dl, "raw/strava/athlete") or "latest"

        # Simuler load_athlete_data
        athlete_raw = dl.read_json(f"raw/strava/athlete/{partition}")
        athlete = athlete_raw[0] if isinstance(athlete_raw, list) else athlete_raw
        stats_raw = dl.read_json(f"raw/strava/stats/{partition}")
        stats = stats_raw[0] if isinstance(stats_raw, list) else stats_raw
        activities = dl.read_json(f"raw/strava/activities/{partition}")

        _logger.info(
            "DRY-RUN — partition=%s · %d activités chargées",
            partition,
            len(activities),
        )

        # On réutilise directement la logique de prepare_athlete_context
        # via l'appel à la step function (sans passer par le moteur)
        context = prepare_athlete_context(
            athlete=athlete,
            stats=stats,
            activities=activities,
            partition=partition,
            activity_count=len(activities),
        )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            athlete_section=context["athlete_section"],
            stats_section=context["stats_section"],
            activity_count=context["activity_count"],
            activities_summary_section=context["activities_summary_section"],
            recent_activities_section=context["recent_activities_section"],
            schema_section=context["schema_section"],
        )

        print("\n" + "═" * 60)  # noqa: T201
        print("SYSTEM PROMPT :")  # noqa: T201
        print(SYSTEM_PROMPT)  # noqa: T201
        print("─" * 60)  # noqa: T201
        print(f"USER PROMPT ({len(user_prompt)} chars) :")  # noqa: T201
        print(user_prompt[:3000])  # noqa: T201
        if len(user_prompt) > 3000:
            print(f"\n[... {len(user_prompt) - 3000} chars tronqués]")  # noqa: T201
        print("═" * 60)  # noqa: T201
        print("\n✅ Dry-run OK — aucun appel API effectué")  # noqa: T201

    else:
        # ── Mode complet : pipeline 4 steps ──────────────────────────
        partition = args.date or "latest"
        model = args.model or os.environ.get("OPENAI_MODEL", "gpt-4o")

        engine = WorkflowEngine(
            storage=SQLiteStorage(database_path="workflow.db"),
        )
        result = engine.run_with_storage(
            analyze_strava_athlete.build(),
            initial_context={
                "partition": partition,
                "model": model,
            },
        )

        for step_run in result.step_runs:
            ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
            print(  # noqa: T201
                f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
            )

        print(f"\nStatut final : {result.status}")  # noqa: T201

        # Afficher le chemin de sortie si succès
        if str(result.status) in ("SUCCESS", "RunStatus.SUCCESS"):
            dl = DataLake.from_env()
            resolved_partition = args.date or (
                _latest_partition(dl, "raw/strava/athlete") or "latest"
            )
            out_path = (
                dl.root
                / f"llm/strava/athlete_analysis/{resolved_partition}/analysis.json"
            )
            print(f"\n📄 Analyse disponible : {out_path}")  # noqa: T201
