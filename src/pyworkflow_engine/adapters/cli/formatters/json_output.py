"""
Sérialisation JSON pour --format json.

Fonctions pures : aucun I/O, retournent des str JSON.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyworkflow_engine.models.workflow.job import Job
    from pyworkflow_engine.models.workflow.run import JobRun


def _default(obj: Any) -> Any:
    """Fallback pour json.dumps sur les types non-sérialisables."""
    if hasattr(obj, "isoformat"):  # datetime
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if hasattr(obj, "total_seconds"):  # timedelta
        return obj.total_seconds()
    return str(obj)


def jobs_to_json(jobs: list[Job]) -> str:
    """Sérialise une liste de Jobs en JSON."""
    data = [
        {
            "name": j.name,
            "description": j.description,
            "version": j.version,
            "steps_count": len(j.steps),
            "step_names": [s.name for s in j.steps],
            "executor": j.default_executor.value if j.default_executor else "local",
            "tags": j.tags,
            "enabled": j.enabled,
        }
        for j in jobs
    ]
    return json.dumps(data, indent=2, default=_default)


def run_to_json(job_run: JobRun) -> str:
    """Sérialise un JobRun en JSON."""
    data = {
        "run_id": job_run.job_run_id,
        "job_name": job_run.job_name,
        "job_version": job_run.job_version,
        "status": job_run.status.value,
        "start_time": job_run.start_time,
        "end_time": job_run.end_time,
        "input_data": job_run.input_data,
        "output_data": job_run.output_data,
        "step_runs": [
            {
                "step_name": sr.step_name,
                "status": sr.status.value,
                "start_time": sr.start_time,
                "end_time": sr.end_time,
                "duration_ms": sr.duration_ms,
                "error": sr.error,
                "output_data": sr.output_data,
            }
            for sr in job_run.step_runs
        ],
    }
    return json.dumps(data, indent=2, default=_default)


def runs_to_json(runs: list[JobRun]) -> str:
    """Sérialise une liste de JobRuns en JSON."""
    data = [
        {
            "run_id": r.job_run_id,
            "job_name": r.job_name,
            "status": r.status.value,
            "start_time": r.start_time,
            "end_time": r.end_time,
        }
        for r in runs
    ]
    return json.dumps(data, indent=2, default=_default)


def execution_plan_to_json(plan: dict[str, Any]) -> str:
    """Sérialise un plan d'exécution en JSON."""
    return json.dumps(plan, indent=2, default=_default)
