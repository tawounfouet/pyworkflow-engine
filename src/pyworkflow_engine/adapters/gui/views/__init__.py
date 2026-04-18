"""Vues NiceGUI pour le GUI adapter.

Chaque vue est une fonction ``build_*`` qui construit le contenu
d'une page NiceGUI dans le contexte du routeur actif.
"""

from pyworkflow_engine.adapters.gui.views.agents import (
    build_agent_detail_page,
    build_agents_page,
)
from pyworkflow_engine.adapters.gui.views.conversations import (
    build_conversation_detail,
    build_conversations_page,
)
from pyworkflow_engine.adapters.gui.views.dashboard import build_dashboard
from pyworkflow_engine.adapters.gui.views.executions import (
    build_execution_detail,
    build_executions_page,
)
from pyworkflow_engine.adapters.gui.views.jobs import (
    build_job_detail_page,
    build_jobs_page,
)
from pyworkflow_engine.adapters.gui.views.pipeline_runs import (
    build_pipeline_run_detail,
    build_pipeline_runs_page,
)
from pyworkflow_engine.adapters.gui.views.pipelines import (
    build_pipeline_detail_page,
    build_pipelines_page,
)
from pyworkflow_engine.adapters.gui.views.run_detail import build_run_detail
from pyworkflow_engine.adapters.gui.views.run_history import build_run_history
from pyworkflow_engine.adapters.gui.views.scheduler import build_scheduler_page
from pyworkflow_engine.adapters.gui.views.settings import build_settings

__all__ = [
    # Workflow
    "build_dashboard",
    "build_jobs_page",
    "build_job_detail_page",
    "build_run_history",
    "build_run_detail",
    # Pipelines
    "build_pipelines_page",
    "build_pipeline_detail_page",
    "build_pipeline_runs_page",
    "build_pipeline_run_detail",
    # IA
    "build_agents_page",
    "build_agent_detail_page",
    "build_executions_page",
    "build_execution_detail",
    "build_conversations_page",
    "build_conversation_detail",
    # Misc
    "build_settings",
    "build_scheduler_page",
]
