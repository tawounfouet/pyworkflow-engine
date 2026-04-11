"""Vues NiceGUI pour le GUI adapter.

Chaque vue est une fonction ``build_*`` qui construit le contenu
d'une page NiceGUI dans le contexte du routeur actif.
"""

from pyworkflow_engine.adapters.gui.views.dashboard import build_dashboard
from pyworkflow_engine.adapters.gui.views.jobs import (
    build_jobs_page,
    build_job_detail_page,
)
from pyworkflow_engine.adapters.gui.views.run_history import build_run_history
from pyworkflow_engine.adapters.gui.views.run_detail import build_run_detail
from pyworkflow_engine.adapters.gui.views.settings import build_settings

__all__ = [
    "build_dashboard",
    "build_jobs_page",
    "build_job_detail_page",
    "build_run_history",
    "build_run_detail",
    "build_settings",
]
