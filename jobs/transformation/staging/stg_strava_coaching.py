# filepath: jobs/transformation/staging/stg_strava_coaching.py
"""
Transformation — Coaching IA journalier Strava → Staging DWH.

3ème maillon de la pipeline ``pipelines/daily/strava_daily_coaching.py``.
Lit les rapports de coaching IA produits par ``coach_daily.py`` depuis le
Data Lake, les normalise en lignes plats et les upsert dans le DWH.

Source : datalake://llm/strava/daily_coaching/{date}/coaching.json
Cible  : DWH → staging.stg_strava_coaching

Tables créées / alimentées :
    staging.stg_strava_coaching         — 1 ligne par jour d'analyse
    staging.stg_strava_coaching_acts    — 1 ligne par activité analysée

Pipeline :
    read_coaching_from_datalake   (lecture JSON depuis Data Lake)
        ↓
    normalize_coaching            (aplatissement + typage)
        ↓
    load_coaching_to_warehouse    (upsert DuckDB / Postgres)
        ↓
    quality_check_coaching        (COUNT + intégrité)

Variables d'environnement :
    DATALAKE_PATH       : Répertoire racine du Data Lake
    WAREHOUSE_BACKEND   : ``duckdb`` (défaut) ou ``postgres``
    WAREHOUSE_CONN      : Chemin DuckDB ou DSN Postgres

Usage CLI :
    python -m jobs.transformation.staging.stg_strava_coaching
    python -m jobs.transformation.staging.stg_strava_coaching --date 2026-04-13
"""

from __future__ import annotations

from typing import Any

from pyworkflow_engine.decorators import job, step
from pyworkflow_engine.logging import get_logger

from jobs.shared.datalake import DataLake
from jobs.shared.warehouse import Warehouse

_logger = get_logger("jobs.transformation.staging.stg_strava_coaching")

# Tables cibles dans le warehouse
_TABLE_DAILY = "staging.stg_strava_coaching"
_TABLE_ACTS = "staging.stg_strava_coaching_acts"


# ═══════════════════════════════════════════════════════════════════════════
# Steps
# ═══════════════════════════════════════════════════════════════════════════


@step(name="read_coaching_from_datalake", timeout=30.0)
def read_coaching_from_datalake(
    partition: str = "today",
) -> dict[str, Any]:
    """Lit le rapport de coaching IA depuis le Data Lake.

    Cherche ``llm/strava/daily_coaching/{partition}/coaching.json``.
    Si ``partition="today"``, résout la date du jour.

    Args:
        partition: Date ``YYYY-MM-DD`` ou ``"today"``. Injecté depuis
                   ``initial_context``.

    Returns:
        ``{"coaching": {...}, "partition": str}``

    Raises:
        FileNotFoundError: Si le fichier coaching n'existe pas.
    """
    import json  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    dl = DataLake.from_env()

    if partition == "today":
        from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

        partition = settings.today()

    coaching_path = dl.root / f"llm/strava/daily_coaching/{partition}/coaching.json"
    if not coaching_path.exists():
        raise FileNotFoundError(
            f"Rapport coaching introuvable : {coaching_path}\n"
            "Lancez d'abord : python -m jobs.llm.strava_daily_coaching.coach_daily"
        )

    coaching: dict[str, Any] = json.loads(coaching_path.read_text())
    _logger.info(
        "Rapport coaching chargé : partition=%s · session_type=%s",
        partition,
        coaching.get("session_type", "?"),
    )
    _logger.success(  # type: ignore[attr-defined]
        "✅ read_coaching_from_datalake — partition=%s", partition
    )
    return {"coaching": coaching, "partition": partition}


@step(name="normalize_coaching", dependencies=["read_coaching_from_datalake"])
def normalize_coaching(
    coaching: dict[str, Any] | None = None,
    partition: str = "",
) -> dict[str, Any]:
    """Aplatit le rapport JSON en lignes relationnelles normalisées.

    Produit deux jeux de records :
    - ``daily_row`` : 1 ligne résumant la journée (charge, recommandations…)
    - ``act_rows``  : 1 ligne par activité analysée

    Args:
        coaching:  Injecté depuis ``read_coaching_from_datalake``.
        partition: Injecté depuis ``read_coaching_from_datalake``.

    Returns:
        ``{"daily_row": {...}, "act_rows": [...], "partition": str,
           "act_count": int}``
    """
    data = coaching or {}
    meta = data.get("metadata", {})
    load = data.get("load_assessment", {})
    tomorrow = data.get("tomorrow_recommendation", {})
    generated_at = meta.get("generated_at", "")

    # ── Ligne journalière ─────────────────────────────────────────────
    daily_row: dict[str, Any] = {
        "partition_date": partition,
        "session_type": data.get("session_type"),
        "session_summary": data.get("session_summary"),
        "daily_load": load.get("daily_load"),
        "weekly_trend": load.get("weekly_trend"),
        "fatigue_signal": load.get("fatigue_signal"),
        "tomorrow_type": tomorrow.get("type"),
        "tomorrow_rationale": tomorrow.get("rationale"),
        "weekly_tip": data.get("weekly_tip"),
        "coach_message": data.get("coach_message"),
        "model_used": meta.get("model_used"),
        "activity_count": meta.get("activity_count", 0),
        "generated_at": generated_at,
    }
    _logger.info(
        "Ligne journalière : date=%s · session_type=%s · daily_load=%s",
        partition,
        daily_row["session_type"],
        daily_row["daily_load"],
    )

    # ── Lignes par activité ───────────────────────────────────────────
    act_rows: list[dict[str, Any]] = []
    for idx, a in enumerate(data.get("activities_analysis", [])):
        act_rows.append(
            {
                "partition_date": partition,
                "activity_idx": idx,
                "name": a.get("name"),
                "sport": a.get("sport"),
                "distance_km": a.get("distance_km"),
                "duration_min": a.get("duration_min"),
                "elevation_m": a.get("elevation_m"),
                "intensity_score": a.get("intensity_score"),
                "quality_assessment": a.get("quality_assessment"),
                "pace_min_per_km": a.get("pace_min_per_km"),
                "generated_at": generated_at,
            }
        )
    _logger.info("Activités normalisées : %d ligne(s)", len(act_rows))
    _logger.success(  # type: ignore[attr-defined]
        "✅ normalize_coaching — 1 ligne journalière + %d activité(s)", len(act_rows)
    )
    return {
        "daily_row": daily_row,
        "act_rows": act_rows,
        "partition": partition,
        "act_count": len(act_rows),
    }


@step(name="load_coaching_to_warehouse", dependencies=["normalize_coaching"])
def load_coaching_to_warehouse(
    daily_row: dict[str, Any] | None = None,
    act_rows: list[dict[str, Any]] | None = None,
    partition: str = "",
) -> dict[str, Any]:
    """Upsert les records normalisés dans le DWH (DuckDB en dev).

    Table ``staging.stg_strava_coaching``      → 1 ligne upsertée (clé : partition_date)
    Table ``staging.stg_strava_coaching_acts`` → N lignes upsertées (clé : partition_date + activity_idx)

    Args:
        daily_row: Injecté depuis ``normalize_coaching``.
        act_rows:  Injecté depuis ``normalize_coaching``.
        partition: Injecté depuis ``normalize_coaching``.

    Returns:
        ``{"daily_rows_upserted": int, "act_rows_upserted": int}``
    """
    wh = Warehouse.from_env()

    # ── Créer le schema staging si nécessaire (DuckDB) ────────────────
    conn = wh._get_connection()
    conn.execute("CREATE SCHEMA IF NOT EXISTS staging")
    _logger.info("Schema 'staging' vérifié / créé")

    # ── Ligne journalière ─────────────────────────────────────────────
    daily_rows_upserted = 0
    if daily_row:
        daily_rows_upserted = wh.upsert(
            table=_TABLE_DAILY,
            data=[daily_row],
            key="partition_date",
        )
        _logger.info("Upsert %s : %d ligne(s)", _TABLE_DAILY, daily_rows_upserted)

    # ── Activités ─────────────────────────────────────────────────────
    act_rows_upserted = 0
    rows = act_rows or []
    if rows:
        # Clé composite : partition_date + activity_idx (pas de support natif
        # → on passe un champ synthétique)
        for r in rows:
            r["_pk"] = f"{r['partition_date']}__{r['activity_idx']}"
        act_rows_upserted = wh.upsert(
            table=_TABLE_ACTS,
            data=rows,
            key="_pk",
        )
        _logger.info("Upsert %s : %d ligne(s)", _TABLE_ACTS, act_rows_upserted)

    _logger.success(  # type: ignore[attr-defined]
        "✅ load_coaching_to_warehouse — daily=%d · acts=%d",
        daily_rows_upserted,
        act_rows_upserted,
    )
    return {
        "daily_rows_upserted": daily_rows_upserted,
        "act_rows_upserted": act_rows_upserted,
    }


@step(name="quality_check_coaching", dependencies=["load_coaching_to_warehouse"])
def quality_check_coaching(
    partition: str = "",
) -> dict[str, Any]:
    """Vérifie l'intégrité post-chargement dans le DWH.

    Contrôles :
    - La ligne journalière pour cette partition existe bien.
    - ``session_type`` est non-null.
    - Le nombre de lignes global est cohérent.

    Args:
        partition: Injecté depuis ``normalize_coaching``.

    Returns:
        ``{"quality_passed": bool, "total_daily_rows": int,
           "partition_found": bool, "null_session_type": int}``
    """
    wh = Warehouse.from_env()

    total_daily = wh.query_scalar(f"SELECT COUNT(*) FROM {_TABLE_DAILY}")  # noqa: S608
    partition_found_count = wh.query_scalar(  # noqa: S608
        f"SELECT COUNT(*) FROM {_TABLE_DAILY} WHERE partition_date = ?",
        (partition,),
    )
    null_session = wh.query_scalar(  # noqa: S608
        f"SELECT COUNT(*) FROM {_TABLE_DAILY} WHERE session_type IS NULL"
    )

    partition_found = bool(partition_found_count and int(partition_found_count) > 0)
    null_session_count = int(null_session or 0)
    quality_passed = partition_found and null_session_count == 0

    _logger.info(
        "QC : total_rows=%s · partition_found=%s · null_session_type=%s · passed=%s",
        total_daily,
        partition_found,
        null_session_count,
        quality_passed,
    )

    if not quality_passed:
        if not partition_found:
            _logger.warning(
                "QC ÉCHEC : partition %s introuvable dans %s", partition, _TABLE_DAILY
            )
        if null_session_count:
            _logger.warning("QC ÉCHEC : %d session_type NULL", null_session_count)
    else:
        _logger.success(  # type: ignore[attr-defined]
            "✅ quality_check_coaching — QC passé · %d lignes total", total_daily
        )

    return {
        "quality_passed": quality_passed,
        "total_daily_rows": int(total_daily or 0),
        "partition_found": partition_found,
        "null_session_type": null_session_count,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Job
# ═══════════════════════════════════════════════════════════════════════════


@job(
    name="transform-stg-strava-coaching",
    version="1.0.0",
    description=(
        "Transformation coaching IA Strava → Staging DWH. "
        "Pipeline : lecture coaching.json (Data Lake) → normalisation → "
        "upsert DuckDB (staging.stg_strava_coaching + _acts) → quality check."
    ),
    steps=[
        read_coaching_from_datalake,
        normalize_coaching,
        load_coaching_to_warehouse,
        quality_check_coaching,
    ],
)
def transform_stg_strava_coaching() -> None:
    """Déclaration du pipeline — le corps n'est pas exécuté par ``build()``."""
    read_coaching_from_datalake()
    normalize_coaching()
    load_coaching_to_warehouse()
    quality_check_coaching()


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    from pyworkflow_engine import WorkflowEngine  # noqa: PLC0415
    from pyworkflow_engine.adapters.storage import SQLiteStorage  # noqa: PLC0415

    from jobs.shared.logging import configure_platform_logging  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Transformation coaching Strava → Staging DWH"
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
        transform_stg_strava_coaching.build(),
        initial_context={"partition": today},
    )
    for step_run in result.step_runs:
        ok = str(step_run.status) in ("SUCCESS", "RunStatus.SUCCESS")
        print(
            f"  {'✅' if ok else '❌'} {step_run.step_name}: {step_run.status}"
        )  # noqa: T201
    print(f"\nStatut final : {result.status}")  # noqa: T201
