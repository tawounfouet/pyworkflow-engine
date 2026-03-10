"""
IAS Workflow Engine - Moteur d'orchestration de workflows Python pur.

Un package zero-dépendance pour créer, exécuter et gérer des workflows complexes
dans n'importe quel environnement Python.

Usage basique:
    from pyworkflow_engine import Job, Step, WorkflowEngine

    def hello_world():
        return {"message": "Hello World!"}

    job = Job(name="Test", steps=[
        Step(name="Say Hello", callable=hello_world)
    ])

    engine = WorkflowEngine()
    result = engine.run(job)

Architecture modulaire:
    - Core: Modèles et moteur d'exécution (zero dépendance)
    - Executors: Comment les étapes sont exécutées (local, thread, async, human, etc.)
    - Triggers: Comment les workflows sont déclenchés (manuel, API, schedule, etc.)
    - Persistence: Où les données sont stockées (memory, JSON, SQLite, etc.)
    - Adapters: Intégrations framework-spécifiques (Django, FastAPI, Celery, etc.)
"""

__version__ = "0.1.0"
__author__ = "IAS"
__email__ = "dev@ias.com"


# ── Lazy imports ─────────────────────────────────────────────────────────────
# Le projet est en phase de construction progressive.  Les modules sont importés
# dynamiquement afin d'éviter des ImportError quand un sous-module n'est pas
# encore implémenté.  Au fur et à mesure que les modules sont créés, les imports
# correspondants se résoudront automatiquement.


def __getattr__(name: str):  # PEP 562 – module-level __getattr__
    """Import paresseux des symboles du package.

    Permet ``from pyworkflow_engine import Job`` dès que le module
    ``core.models.design_time`` existe, tout en évitant un crash si le
    module n'a pas encore été créé.
    """

    _LAZY_IMPORTS: dict[str, tuple[str, str]] = {
        # Core models
        "Job": (".core.models.design_time", "Job"),
        "Step": (".core.models.design_time", "Step"),
        "SubJob": (".core.models.design_time", "SubJob"),
        "JobRun": (".core.models.runtime", "JobRun"),
        "StepRun": (".core.models.runtime", "StepRun"),
        "StepLog": (".core.models.runtime", "StepLog"),
        # Enums
        "TriggerType": (".core.models.enums", "TriggerType"),
        "StepType": (".core.models.enums", "StepType"),
        "ExecutorType": (".core.models.enums", "ExecutorType"),
        "RunStatus": (".core.models.enums", "RunStatus"),
        "LogLevel": (".core.models.enums", "LogLevel"),
        # Engine
        "WorkflowEngine": (".core.engine", "WorkflowEngine"),
        "WorkflowContext": (".core.context", "WorkflowContext"),
        # Exceptions
        "WorkflowError": (".core.exceptions", "WorkflowError"),
        "WorkflowSuspended": (".core.exceptions", "WorkflowSuspended"),
        "WorkflowFailed": (".core.exceptions", "WorkflowFailed"),
        "StepTimeout": (".core.exceptions", "StepTimeout"),
        "DAGCycleError": (".core.exceptions", "DAGCycleError"),
        # Executors
        "ThreadPoolStepExecutor": (".core.executors", "ThreadPoolStepExecutor"),
        "ProcessPoolStepExecutor": (".core.executors", "ProcessPoolStepExecutor"),
        "AsyncStepExecutor": (".core.executors", "AsyncStepExecutor"),
        "RetryableExecutor": (".core.executors", "RetryableExecutor"),
        "ExecutorRegistry": (".core.executors", "ExecutorRegistry"),
        "LocalExecutor": (".executors.local", "LocalExecutor"),
        # Persistence
        "InMemoryPersistence": (".persistence.memory", "InMemoryPersistence"),
        "BasePersistence": (".persistence.base", "BasePersistence"),
    }

    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path, __name__)
        value = getattr(module, attr)
        # Cache dans le namespace du module pour les accès suivants
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__email__",
    # Core models
    "Job",
    "Step",
    "SubJob",
    "JobRun",
    "StepRun",
    "StepLog",
    # Enums
    "TriggerType",
    "StepType",
    "ExecutorType",
    "RunStatus",
    "LogLevel",
    # Engine
    "WorkflowEngine",
    "WorkflowContext",
    # Exceptions
    "WorkflowError",
    "WorkflowSuspended",
    "WorkflowFailed",
    "StepTimeout",
    "DAGCycleError",
    # Built-in executors
    "LocalExecutor",
    "ExecutorRegistry",
    "ThreadPoolStepExecutor",
    "ProcessPoolStepExecutor",
    "AsyncStepExecutor",
    "RetryableExecutor",
    # Built-in persistence
    "InMemoryPersistence",
    "BasePersistence",
]
