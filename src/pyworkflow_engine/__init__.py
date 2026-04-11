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

Architecture hexagonale (v0.7.0 — ADR-006/ADR-007):
    - Ports: Interfaces abstraites (ABC/Protocol) — ``ports/``
    - Engine: Logique cœur d'exécution (dépend uniquement de ports/) — ``engine/``
    - Models: Structures de données (dataclasses) — ``models/``
    - Decorators: API déclarative @step/@job — ``decorators/``
    - Adapters: Implémentations concrètes des ports — ``adapters/``
      - Executors: local, thread, process, async (stdlib)
      - Persistence: memory, JSON, SQLite, SQLAlchemy
      - Triggers: manual, schedule/cron
      - Intégrations: Celery, Snowflake, structlog (extras opt-in)
    - Facade: WorkflowEngine assemble engine + ports + adapters — ``facade.py``
"""

__version__ = "0.7.0"
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
        # Executors — ports publics
        "BaseExecutor": (".ports.executor", "BaseExecutor"),
        "ExecutorRegistry": (".ports.executor", "ExecutorRegistry"),
        # Executors — adapters
        "LocalExecutor": (".adapters.executors.local", "LocalExecutor"),
        "ThreadPoolStepExecutor": (
            ".adapters.executors.thread_pool",
            "ThreadPoolStepExecutor",
        ),
        "ProcessPoolStepExecutor": (
            ".adapters.executors.process_pool",
            "ProcessPoolStepExecutor",
        ),
        "AsyncStepExecutor": (".adapters.executors.async_exec", "AsyncStepExecutor"),
        "RetryableExecutor": (".adapters.executors.retryable", "RetryableExecutor"),
        # Engine — parallel runner
        "ParallelRunner": (".engine.parallel_runner", "ParallelRunner"),
        # Triggers — ports publics
        "BaseTrigger": (".ports.trigger", "BaseTrigger"),
        "TriggerState": (".ports.trigger", "TriggerState"),
        # Triggers — adapters
        "ManualTrigger": (".adapters.triggers.manual", "ManualTrigger"),
        "ScheduleTrigger": (".adapters.triggers.schedule", "ScheduleTrigger"),
        "CronExpression": (".adapters.triggers.schedule", "CronExpression"),
        # Persistence — port public
        "BaseStorage": (".ports.storage", "BaseStorage"),
        # Persistence — adapters
        "InMemoryStorage": (".adapters.storage.memory", "InMemoryStorage"),
        # Celery adapter (ADR-007) — opt-in, requiert pip install pyworkflow-engine[celery]
        "CeleryExecutor": (".adapters.celery.executor", "CeleryExecutor"),
        "CeleryConfig": (".adapters.celery.config", "CeleryConfig"),
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
    "InMemoryStorage",
    "BaseStorage",
    # Decorators API (ADR-005)
    "step",
    "job",
    "StepSpec",
    "JobBuilder",
    # Celery adapter (ADR-007) — opt-in
    "CeleryExecutor",
    "CeleryConfig",
]
