"""
PyWorkflow Engine - Moteur d'orchestration de workflows Python pur.

Un package zero-dépendance pour créer, exécuter et gérer des workflows complexes
dans n'importe quel environnement Python.

Usage basique:
    from pyworkflow_engine import Job, Step, WorkflowEngine

    def hello_world():
        return {"message": "Hello World!"}

    job = Job(name="Test", steps=[
        Step(name="Say Hello", step_type=StepType.FUNCTION, handler=hello_world)
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

__version__ = "0.5.0"
__author__ = "PyWorkflow Contributors"
__email__ = "dev@pyworkflow.dev"


# ── Lazy imports ─────────────────────────────────────────────────────────────
# Le projet est en phase de construction progressive.  Les modules sont importés
# dynamiquement afin d'éviter des ImportError quand un sous-module n'est pas
# encore implémenté.  Au fur et à mesure que les modules sont créés, les imports
# correspondants se résoudront automatiquement.


def __getattr__(name: str):  # PEP 562 – module-level __getattr__
    """Import paresseux des symboles du package.

    Permet ``from pyworkflow_engine import Job`` sans importer tous les
    sous-modules à l'initialisation du package. Chaque symbole est importé
    à la première utilisation puis mis en cache dans ``globals()``.
    """

    _LAZY_IMPORTS: dict[str, tuple[str, str]] = {
        # Models
        "Job": (".models.job", "Job"),
        "Step": (".models.step", "Step"),
        "SubJob": (".models.step", "SubJob"),
        "JobRun": (".models.run", "JobRun"),
        "StepRun": (".models.run", "StepRun"),
        "StepLog": (".models.run", "StepLog"),
        # Enums
        "TriggerType": (".models.enums", "TriggerType"),
        "StepType": (".models.enums", "StepType"),
        "ExecutorType": (".models.enums", "ExecutorType"),
        "RunStatus": (".models.enums", "RunStatus"),
        # Engine
        "WorkflowEngine": (".facade", "WorkflowEngine"),
        "WorkflowContext": (".engine.context", "WorkflowContext"),
        # Exceptions
        "WorkflowError": (".exceptions", "WorkflowError"),
        "WorkflowSuspended": (".exceptions", "WorkflowSuspended"),
        "WorkflowFailed": (".exceptions", "WorkflowFailed"),
        "StepExecutionError": (".exceptions", "StepExecutionError"),
        "DAGValidationError": (".exceptions", "DAGValidationError"),
        # Executors
        "ThreadPoolStepExecutor": (".executors.thread_pool", "ThreadPoolStepExecutor"),
        "ProcessPoolStepExecutor": (
            ".executors.thread_pool",
            "ProcessPoolStepExecutor",
        ),
        "AsyncStepExecutor": (".executors.async_exec", "AsyncStepExecutor"),
        "RetryableExecutor": (".executors.retryable", "RetryableExecutor"),
        "ExecutorRegistry": (".executors.base", "ExecutorRegistry"),
        "LocalExecutor": (".executors.local", "LocalExecutor"),
        # Engine — parallel runner
        "ParallelRunner": (".engine.parallel_runner", "ParallelRunner"),
        # Triggers
        "BaseTrigger": (".triggers.base", "BaseTrigger"),
        "TriggerState": (".triggers.base", "TriggerState"),
        "ManualTrigger": (".triggers.manual", "ManualTrigger"),
        "ScheduleTrigger": (".triggers.schedule", "ScheduleTrigger"),
        "CronExpression": (".triggers.schedule", "CronExpression"),
        # Persistence
        "InMemoryPersistence": (".persistence.memory", "InMemoryPersistence"),
        "BasePersistence": (".persistence.base", "BasePersistence"),
        # Decorators API (ADR-005)
        "step": (".decorators.step_decorator", "step"),
        "job": (".decorators.job_decorator", "job"),
        "StepSpec": (".decorators.step_decorator", "StepSpec"),
        "JobBuilder": (".decorators.job_decorator", "JobBuilder"),
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
    # Engine
    "WorkflowEngine",
    "WorkflowContext",
    # Exceptions
    "WorkflowError",
    "WorkflowSuspended",
    "WorkflowFailed",
    "StepExecutionError",
    "DAGValidationError",
    # Built-in executors
    "LocalExecutor",
    "ExecutorRegistry",
    "ThreadPoolStepExecutor",
    "ProcessPoolStepExecutor",
    "AsyncStepExecutor",
    "RetryableExecutor",
    # Engine extras
    "ParallelRunner",
    # Triggers
    "BaseTrigger",
    "TriggerState",
    "ManualTrigger",
    "ScheduleTrigger",
    "CronExpression",
    # Built-in persistence
    "InMemoryPersistence",
    "BasePersistence",
    # Decorators API (ADR-005)
    "step",
    "job",
    "StepSpec",
    "JobBuilder",
]
