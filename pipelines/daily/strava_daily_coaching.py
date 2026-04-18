# filepath: pipelines/daily/strava_daily_coaching.py
"""
Pipeline quotidienne — Strava Daily Coaching.

Fréquence : quotidien (20h30 UTC, après la journée sportive)
Owner     : data-team@company.com

Chaîne d'exécution :
    1. ``ingestion-strava-daily``        — Strava API → Data Lake (raw/strava/daily/{date}/)
    2. ``llm-strava-daily-coaching``     — Agent IA GPT-4o → Data Lake (llm/strava/daily_coaching/{date}/)
    3. ``transform-stg-strava-coaching`` — Data Lake → Staging DWH (staging.stg_strava_coaching)

Flux de données :
    Strava API
        │  GET /athlete, /stats, /athlete/activities (filtre after/before)
        ▼
    Data Lake  raw/strava/daily/{date}/
        │  athlete.json · stats.json · activities.json
        ▼
    Agent IA (GPT-4o)
        │  Analyse séance + charge + recommandations
        ▼
    Data Lake  llm/strava/daily_coaching/{date}/coaching.json
        │  JSON structuré (session_type, load, tomorrow...)
        ▼
    DWH  staging.stg_strava_coaching + staging.stg_strava_coaching_acts

Variables d'environnement :
    STRAVA_CLIENT_ID      : Client ID Strava
    STRAVA_CLIENT_SECRET  : Client Secret Strava
    STRAVA_REFRESH_TOKEN  : Refresh token OAuth2
    OPENAI_API_KEY        : Clé API OpenAI
    OPENAI_MODEL          : Modèle LLM (défaut : gpt-4o)
    DATALAKE_PATH         : Répertoire racine du Data Lake
    WAREHOUSE_BACKEND     : ``duckdb`` (défaut) ou ``postgres``
    WAREHOUSE_CONN        : Chemin DuckDB ou DSN Postgres

Usage CLI :
    python -m pipelines.daily.strava_daily_coaching
    python -m pipelines.daily.strava_daily_coaching --date 2026-04-11
    python -m pipelines.daily.strava_daily_coaching --model gpt-4o-mini
    python -m pipelines.daily.strava_daily_coaching --skip-ingestion
    python -m pipelines.daily.strava_daily_coaching --skip-transform
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from pyworkflow_engine.decorators import pipeline, stage
from pyworkflow_engine.logging import get_logger

from jobs.ingestion.strava.fetch_today_activities import ingest_strava_daily
from jobs.llm.strava_daily_coaching.coach_daily import coach_strava_daily
from jobs.shared.logging import configure_platform_logging, get_engine
from jobs.transformation.staging.stg_strava_coaching import (
    transform_stg_strava_coaching,
)
from pipelines.shared.notifications import notify_pipeline
from pipelines.shared.runner import run_pipeline

_logger = get_logger("pipelines.daily.strava_daily_coaching")


# ---------------------------------------------------------------------------
# Stage factories
# ---------------------------------------------------------------------------
# Les stages sont construits dynamiquement pour injecter date/model/flags.


def _make_stages(
    target_date: str,
    llm_model: str,
    skip_ingestion: bool,
    skip_transform: bool,
) -> tuple[Any, Any, Any]:
    """Retourne (stage_ingest, stage_coach, stage_transform) prets a l'emploi."""

    @stage(
        job=ingest_strava_daily,
        initial_context={"target_date": target_date},
        enabled=not skip_ingestion,
    )
    def ingestion_strava_daily() -> None:
        """Job 1 — Ingestion Strava API vers Data Lake."""

    @stage(
        job=coach_strava_daily,
        initial_context={"partition": target_date, "model": llm_model},
    )
    def llm_strava_daily_coaching() -> None:
        """Job 2 — Agent IA GPT-4o, coaching JSON vers Data Lake."""

    @stage(
        job=transform_stg_strava_coaching,
        initial_context={"partition": target_date},
        enabled=not skip_transform,
    )
    def transform_stg_strava_coaching_stage() -> None:
        """Job 3 — Data Lake vers Staging DWH."""

    return (
        ingestion_strava_daily,
        llm_strava_daily_coaching,
        transform_stg_strava_coaching_stage,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_pipeline(
    date: str | None = None,
    model: str | None = None,
    skip_ingestion: bool = False,
    skip_transform: bool = False,
):
    """Construit la ``Pipeline`` Strava Daily Coaching (ADR-014).

    Args:
        date:           Date ``YYYY-MM-DD``. Defaut : aujourd'hui.
        model:          Modele OpenAI (defaut : ``OPENAI_MODEL`` env ou ``gpt-4o``).
        skip_ingestion: Desactive le stage d'ingestion (``enabled=False``).
        skip_transform: Desactive le stage de transformation (``enabled=False``).

    Returns:
        ``Pipeline`` prete a etre executee via ``engine.run_pipeline()``
        ou le bridge ``run_pipeline()``.
    """
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    target_date = date or settings.today()
    llm_model = model or "default"

    stage_ingest, stage_coach, stage_transform = _make_stages(
        target_date, llm_model, skip_ingestion, skip_transform
    )

    @pipeline(
        name="daily-strava-coaching",
        version="2.0.0",
        description="Pipeline quotidienne Strava : ingestion API -> coaching LLM -> warehouse DWH.",
        schedule="30 20 * * *",
        owner="data-team@company.com",
        tags=["strava", "coaching", "daily", "llm"],
        stages=[stage_ingest, stage_coach, stage_transform],
    )
    def daily_strava_coaching_pipeline() -> None:
        """Pipeline orchestratrice Strava Daily Coaching."""

    return daily_strava_coaching_pipeline.build()


def main(
    date: str | None = None,
    model: str | None = None,
    skip_ingestion: bool = False,
    skip_transform: bool = False,
) -> None:
    """Point d'entree principal de la pipeline."""
    configure_platform_logging()

    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    target_date = date or settings.today()

    _logger.info("=" * 60)
    _logger.info("STRAVA DAILY COACHING PIPELINE -- %s", target_date)
    _logger.info("=" * 60)

    pipeline_obj = build_pipeline(
        date=target_date,
        model=model,
        skip_ingestion=skip_ingestion,
        skip_transform=skip_transform,
    )

    engine = get_engine()

    # run_pipeline() bridge -> engine.run_pipeline() -> _storage.save_pipeline_run()
    # Persiste dans pipeline_runs + pl_pipeline_runs (+ stage_runs + pl_stage_runs)
    pipeline_run = run_pipeline(
        pipeline_obj,
        engine=engine,
        triggered_by="manual",
    )

    # -- Resume ---------------------------------------------------------------
    from pyworkflow_engine.models import RunStatus  # noqa: PLC0415

    success = pipeline_run.status == RunStatus.SUCCESS
    status_icon = "SUCCESS" if success else "FAILED"

    sep = "─" * 64
    print()
    print(sep)
    print(
        f"  Pipeline '{pipeline_run.pipeline_name}'  {status_icon}"
        f"  ({(pipeline_run.duration_ms or 0) / 1000:.2f}s)"
    )
    print(sep)
    for sr in pipeline_run.stage_runs:
        if sr.status == RunStatus.SUCCESS:
            stage_icon = "✅"
        elif getattr(sr, "skipped", False):
            stage_icon = "⏭ "
        else:
            stage_icon = "❌"
        stage_dur = f"{(sr.duration_ms or 0) / 1000:.2f}s"
        print(f"  {stage_icon} [{sr.job_name}]  {sr.status.value}  ({stage_dur})")
        if sr.error and not getattr(sr, "skipped", False):
            print(f"       ⚠️  {sr.error}")

        # ── Steps individuels du job ──────────────────────────────────
        job_run = getattr(sr, "job_run", None)
        step_runs = getattr(job_run, "step_runs", []) if job_run else []
        for step in step_runs:
            if step.status == RunStatus.SUCCESS:
                s_icon = "  ✔"
            elif str(step.status) in ("SKIPPED", "RunStatus.SKIPPED"):
                s_icon = "  ⏭"
            else:
                s_icon = "  ✘"
            step_dur = f"{(getattr(step, 'duration_ms', 0) or 0) / 1000:.2f}s"
            print(f"     {s_icon}  {step.step_name}  ({step_dur})")
        print()

    # -- Notifications --------------------------------------------------------
    notify_pipeline(_PipelineRunAdapter(pipeline_run))

    # -- Sortie ---------------------------------------------------------------
    if not success:
        _logger.error("Pipeline 'daily-strava-coaching' terminee en ECHEC")
        sys.exit(1)

    _logger.info("Pipeline 'daily-strava-coaching' terminee avec succes")


# ---------------------------------------------------------------------------
# Duck-typing adapters  (PipelineRun ADR-014 -> PipelineResult legacy)
# ---------------------------------------------------------------------------


class _PipelineRunAdapter:
    """Adapte un PipelineRun (ADR-014) a l'interface PipelineResult attendue
    par notify_pipeline()."""

    def __init__(self, pipeline_run: Any) -> None:
        from pyworkflow_engine.models import RunStatus  # noqa: PLC0415

        self.pipeline_name = pipeline_run.pipeline_name
        self.success = pipeline_run.status == RunStatus.SUCCESS
        self.total_duration_s = (pipeline_run.duration_ms or 0) / 1000
        self.job_results = [_StageRunAdapter(sr) for sr in pipeline_run.stage_runs]

    @property
    def summary(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"Pipeline '{self.pipeline_name}' -- {status} "
            f"({self.total_duration_s:.2f}s)"
        )


class _StageRunAdapter:
    """Adapte un StageRun a l'interface JobResult legacy."""

    def __init__(self, stage_run: Any) -> None:
        self.job_name = stage_run.job_name
        self.status = stage_run.status
        self.duration_s = (stage_run.duration_ms or 0) / 1000
        self.error = stage_run.error if not stage_run.skipped else None


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Pipeline Strava Daily Coaching -- Ingestion -> LLM -> DWH",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python -m pipelines.daily.strava_daily_coaching
  python -m pipelines.daily.strava_daily_coaching --date 2026-04-13
  python -m pipelines.daily.strava_daily_coaching --model gpt-4o-mini
  python -m pipelines.daily.strava_daily_coaching --skip-ingestion
  python -m pipelines.daily.strava_daily_coaching --skip-transform
        """,
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date cible (defaut : aujourd'hui).",
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Modele OpenAI (defaut : OPENAI_MODEL env ou gpt-4o).",
    )
    parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Sauter le job d'ingestion Strava.",
    )
    parser.add_argument(
        "--skip-transform",
        action="store_true",
        help="Sauter la transformation warehouse.",
    )
    args = parser.parse_args()

    main(
        date=args.date,
        model=args.model,
        skip_ingestion=args.skip_ingestion,
        skip_transform=args.skip_transform,
    )
