"""
jobs/shared/logging.py — Configuration centralisée du logging pour la data platform.

Active la persistance des logs vers :
    - ``logs/pyworkflow.log``   (fichier rotatif JSON)
    - ``workflow.db``           (table ``workflow_logs``, via SQLiteLogHandler)

Calqué sur le pattern de ``examples/gui_decorator_demo.py`` :
    settings.configure(...) → WorkflowEngine(config=settings.workflow_config)

Usage :
    # En tête de chaque pipeline ou entrypoint __main__ :
    from jobs.shared.logging import configure_platform_logging, get_engine

    configure_platform_logging()          # active fichier + SQLite
    engine = get_engine()                 # WorkflowEngine prêt à l'emploi

    # Ou en une seule ligne :
    from jobs.shared.logging import setup
    engine = setup()
"""

from __future__ import annotations

import os

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.config.settings import settings

# ── Valeurs par défaut (surchargeables via env vars) ─────────────────────────

_DEFAULT_DB = "workflow.db"
_DEFAULT_LOG_DIR = "logs"
_DEFAULT_LEVEL = "INFO"


def configure_platform_logging(
    database: str | None = None,
    log_dir: str | None = None,
    level: str | None = None,
    log_to_db: bool = True,
) -> None:
    """Configure le logging de la data platform (fichier + SQLite).

    Doit être appelé **avant** toute instanciation de ``WorkflowEngine``
    ou ``PipelineRunner`` pour que les logs des steps soient capturés.

    Lit les valeurs depuis les variables d'environnement si non fournies :
        - ``PYWORKFLOW_DB``        → database (défaut: ``workflow.db``)
        - ``PYWORKFLOW_LOG_DIR``   → log_dir  (défaut: ``logs``)
        - ``PYWORKFLOW_LOG_LEVEL`` → level    (défaut: ``INFO``)
        - ``PYWORKFLOW_LOG_TO_DB`` → log_to_db (défaut: ``true``)

    Args:
        database: Chemin du fichier SQLite (logs + persistance engine).
        log_dir:  Dossier pour le fichier de log rotatif JSON.
        level:    Niveau de log (DEBUG / INFO / WARNING / ERROR).
        log_to_db: Persiste les logs dans ``workflow_logs``. Défaut: ``True``.
    """
    db = database or os.environ.get("PYWORKFLOW_DB", _DEFAULT_DB)
    ld = log_dir or os.environ.get("PYWORKFLOW_LOG_DIR", _DEFAULT_LOG_DIR)
    lvl = (level or os.environ.get("PYWORKFLOW_LOG_LEVEL", _DEFAULT_LEVEL)).upper()

    env_to_db = os.environ.get("PYWORKFLOW_LOG_TO_DB", "").strip().lower()
    to_db = log_to_db if env_to_db == "" else env_to_db in ("1", "true", "yes", "on")

    settings.configure(
        DATABASE=db,
        LOGGING_LEVEL=lvl,
        LOGGING_DIR=ld,
        LOGGING_TO_DB=to_db,
        LOGGING_FORMAT="text",  # console = StructuredFormatter (ANSI colors)
        # Note : le file handler utilise toujours JSONFormatter (voir logger.py)
        # quel que soit LOGGING_FORMAT — seul le console handler est affecté.
    )

    # Déclenche la configuration effective (fichier + SQLiteLogHandler)
    # en instanciant un engine jetable — même pattern que gui_decorator_demo.py
    _apply_logging_from_settings()


def _apply_logging_from_settings() -> None:
    """Force l'application du logging via WorkflowConfig → _bootstrap_from_config.

    Instancie un WorkflowEngine avec la config courante des settings.
    L'engine appelle ``_bootstrap_from_config`` dans son ``__init__``,
    ce qui configure le fichier de log et le SQLiteLogHandler.
    L'engine jetable n'est pas conservé — seul l'effet de bord sur le
    logger racine ``pyworkflow_engine`` compte.
    """
    # Même pattern que gui_decorator_demo.py :
    #   WorkflowEngine(config=settings.workflow_config)
    WorkflowEngine(config=settings.workflow_config)


def get_engine() -> WorkflowEngine:
    """Retourne un ``WorkflowEngine`` avec le logging déjà configuré.

    Appelle ``configure_platform_logging()`` si pas encore fait, puis
    construit un engine à partir du ``settings.workflow_config`` courant.

    Returns:
        ``WorkflowEngine`` prêt à l'emploi avec fichier + SQLite logging.
    """
    return WorkflowEngine(config=settings.workflow_config)


def setup(
    database: str | None = None,
    log_dir: str | None = None,
    level: str | None = None,
) -> WorkflowEngine:
    """Raccourci : configure le logging **et** retourne un engine.

    Equivalent de::

        configure_platform_logging(database, log_dir, level)
        return get_engine()

    Args:
        database: Chemin SQLite. Défaut : ``workflow.db``.
        log_dir:  Dossier logs. Défaut : ``logs``.
        level:    Niveau log. Défaut : ``INFO``.

    Returns:
        ``WorkflowEngine`` configuré.
    """
    configure_platform_logging(database=database, log_dir=log_dir, level=level)
    return get_engine()
