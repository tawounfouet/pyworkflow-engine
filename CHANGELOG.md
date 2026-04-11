# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_(aucun changement planifié pour l'instant)_

---

## [0.5.0] - 2026-04-11

> Voir [ADR-005](docs/changelog/2026-04-11-decorator-api.md) pour le contexte architectural complet.

### Added

#### 🎨 API déclarative — `@step` / `@job` (ADR-005)

- **`decorators/step_decorator.py`** — `@step` : décore une fonction Python comme step de workflow
  - `StepSpec` (frozen dataclass) : `name`, `step_type`, `dependencies`, `retry_count`, `retry_delay`, `timeout`, `executor_type`, `tags`, `condition`, `metadata`
  - Usage sans parenthèses (`@step`) et avec paramètres (`@step(name=..., timeout=...)`)
  - La fonction décorée reste **appelable normalement** — aucun mock nécessaire dans les tests unitaires
  - Métadonnées stockées dans `fn.__step_spec__`, fonction originale accessible via `fn.__wrapped_fn__`
- **`decorators/job_decorator.py`** — `@job` : compose des fonctions `@step` en `Job`
  - Retourne un `JobBuilder` — appelable comme la fonction originale + méthode `build()` → `Job`
  - **Mode implicite** : `build()` inspecte le bytecode (`co_names` + `__globals__`) pour collecter automatiquement les steps référencés
  - **Mode explicite** : `@job(steps=[fn1, fn2])` — robuste pour les steps importés dynamiquement
  - Support closures via `co_freevars` + `__closure__` (steps définis en scope local / tests)
  - `_make_context_adapter` : injection automatique des paramètres (dépendances > contexte global > défaut > `None`) sans `__wrapped__` pour ne pas tromper `WorkflowRunner`
  - Mode legacy : `fn(context)` passthrough transparent pour la compatibilité avec l'API impérative
- **`decorators/__init__.py`** — re-exports publics : `step`, `job`, `StepSpec`, `JobBuilder`
- **`examples/decorator_api.py`** — 8 exemples end-to-end

#### 🔢 Exports publics

- `from pyworkflow_engine import step, job, StepSpec, JobBuilder` désormais disponibles

### Tests

- **`tests/unit/test_decorators.py`** — 67 tests unitaires (métadonnées, injection, mode legacy, closure edge-cases, condition/metadata)
- **`tests/integration/test_decorator_workflow.py`** — 21 tests d'intégration (workflows end-to-end avec `WorkflowEngine`)
- **540 passed**, 0 failed, 0 errors
- Couverture `decorators/` : **96 %** (`job_decorator.py`) · **95 %** (`step_decorator.py`) · **100 %** (`__init__.py`)

### Changed

- `__version__` : `0.4.0` → `0.5.0`

---

## [0.4.0] - 2026-04-11

### Breaking Changes

- **`core/` supprimé** (suite v0.3.0) — rupture nette, aucun shim de compatibilité maintenu
- **Nouveau point d'entrée public** : `from pyworkflow_engine import WorkflowEngine, Job, Step, StepType, ManualTrigger, ScheduleTrigger, CronExpression`

### Added

#### 🎯 Triggers — `ManualTrigger`, `ScheduleTrigger`, `CronExpression`

- **`triggers/base.py`** — `BaseTrigger` (ABC), `TriggerState` (enum : IDLE / RUNNING / STOPPED)
- **`triggers/manual.py`** — `ManualTrigger` : déclenchement explicite par code, callbacks `on_run_complete` / `on_run_error`
- **`triggers/schedule.py`** — `ScheduleTrigger` : déclenchement par expression cron via thread d'arrière-plan, `initial_context_factory`, `on_run_complete` / `on_run_error`, méthode `fire()` directe
- **`triggers/schedule.py`** — `CronExpression` : parser cron stdlib (5 champs), `matches(dt)`, `next_occurrence(after)` — zéro dépendance externe
- **`examples/triggers.py`** — 4 démos : ManualTrigger, CronExpression, ScheduleTrigger (thread), ScheduleTrigger (callback d'erreur)

#### 🔀 ParallelRunner

- **`engine/parallel_runner.py`** — `ParallelRunner(WorkflowRunner)` : exécution concurrente des steps sans dépendances mutuelles via `concurrent.futures.ThreadPoolExecutor`
- `WorkflowEngine(parallel=True, max_workers=N)` active `ParallelRunner`
- `DAGResolver.get_parallel_groups()` expose les groupes de steps parallélisables

#### 📝 Documentation architecturale (ADR)

- `docs/changelog/README.md` — index du journal des décisions
- `docs/changelog/2026-04-10-naming-decision.md` — ADR-001 : nommage du package
- `docs/changelog/2026-04-10-architecture-refactoring-proposal.md` — ADR-002 : God Object → couches modulaires
- `docs/changelog/2026-04-10-architecture-critique-integration.md` — ADR-003 : intégration de l'analyse critique
- `docs/changelog/2026-04-11-import-style-and-config-module.md` — ADR-004 : imports absolus + module `config/` *(décision prise, implémentation à venir)*
- `docs/architecture.md`, `docs/architecture_critique.md`, `docs/architecture_critique_v2.md`
- `docs/project_status.md`, `docs/guides/implementation-plan-v2.md`

### Changed

- `WorkflowEngine.__init__` : accepte désormais `parallel: bool` et `max_workers: int | None` pour router vers `ParallelRunner`
- `run_with_persistence()` : checkpoints step-by-step (sauvegarde après chaque step individuel)

### Tests

- `tests/integration/test_parallel_runner.py` — nouveau
- `tests/integration/test_persistence_roundtrip.py` — nouveau
- `tests/unit/test_coverage_boost.py` — nouveau
- **338 passed**, 15 skipped, 0 failed, 0 errors

---

## [0.3.0] - 2026-04-10

### Breaking Changes

- **`core/` déprécié** — début du refactoring, les imports publics sont migrés vers la racine du package. Suppression effective en v0.4.0.
- **`StepRun.timeout()` → `mark_timeout()`** — évite la collision avec le champ `Step.timeout`

### Added

#### 🏗️ Refactoring architectural — God Object → composants spécialisés

- **`facade.py`** — `WorkflowEngine` : point d'entrée unique, compose les composants
- **`engine/runner.py`** — `WorkflowRunner` : exécution pure des steps (pas de retry/persistence/suspension)
- **`engine/retry.py`** — `RetryHandler` : retry unifié
- **`engine/suspension.py`** — `SuspensionManager` : persistence-aware, fallback mémoire
- **`engine/dag.py`** — `DAGResolver` (déplacé depuis `core/`)
- **`engine/context.py`** — `WorkflowContext` (déplacé depuis `core/`)
- **`exceptions.py`** — déplacé à la racine du package
- **`executors/local.py`** — `LocalExecutor` : executor synchrone dans le même processus

#### 🔀 Routing `ExecutorType`

- `WorkflowRunner._resolve_executor(step)` route `step.executor_type` vers l'executor approprié :
  - `LOCAL` → `_execute_function_step` (direct, zéro overhead)
  - `THREAD` → `ThreadPoolStepExecutor`
  - `PROCESS` → `ProcessPoolStepExecutor`
  - `ASYNC` → `AsyncStepExecutor`
  - `CUSTOM` → `ExecutorRegistry` lookup via `step.executor_name`
- `ExecutorType.CUSTOM` ajouté à l'enum
- Docstrings `ExecutorType` enrichis avec la sémantique de routing

#### 🗂️ Restructuration des modèles

- `core/models/design_time.py` → `models/step.py` + `models/job.py`
- `core/models/runtime.py` → `models/run.py`
- Sérialisation intégrée : `to_dict()` + `from_dict(cls)` sur chaque modèle
- `models/__init__.py` conserve des thin wrappers (`step_to_dict`, etc.) pour la compatibilité des backends

#### 📦 Persistence

- `cleanup_old_runs(older_than, dry_run=False)` : contrat LSP aligné sur tous les backends
- Tests paramétrés `dry_run=True` / `dry_run=False` ajoutés pour tous les backends
- Tests d'intégration `tests/integration/test_persistence_roundtrip.py`

#### 📝 Documentation

- `run()` : docstring explicite — exécution pure, sans side-effect de persistence
- `run_with_persistence()` : checkpoints intermédiaires (initial + par step + final), docstring explicite
- `docs/architecture.md` mis à jour vers v0.3.0

### Changed

- `run_with_persistence()` effectue maintenant des **checkpoints step-by-step** (sauvegarde après chaque step) plutôt qu'une sauvegarde finale uniquement
- `inspect.signature()` utilisé partout (remplace `co_argcount`) pour la détection de signature
- `_suspended_workflows` dict supprimé de la façade → délégué à `SuspensionManager`

### Removed

- `core/` (8 fichiers) — suppression totale, rupture nette
- `models/serialization.py` standalone — absorbé dans chaque classe
- `serialization/`, `triggers/` (répertoires vides)

### Tests

- **338 passed**, 15 skipped, 0 failed, 0 errors
- Couverture : 81% → cible 85%

---

## [0.2.1] - 2026-03-11

### Added

#### 📝 **Logging Utilities (from database_logger.py analysis)**
- **`logged_operation`**: Context manager for automatic operation tracing (start, duration, success/failure)
- **`StepLogBridge`**: `logging.Handler` bridging stdlib logging → `StepRun.add_log()` (dual-logging connected)
- **`LoggingConfigBuilder`**: Fluent builder API for constructing `LoggingConfig`
- **`SnowflakeLogHandler`** adapter: `logging.Handler` for Snowflake persistence with batching (`pip install pyworkflow-engine[snowflake]`)
- **ANSI color support** in `StructuredFormatter` with auto-detection (TTY) or explicit `colorize=True/False`
- **Example scripts**: `logging_basics.py` (6 examples) and `logging_advanced.py` (9 examples)
- **32 new tests** in `test_logging_utils.py` (logged_operation, StepLogBridge, LoggingConfigBuilder)

### Changed
- **Log format**: Pipe-separated columns — `2026-03-11 20:42:17 | INFO | core.engine | message`
- **Date format**: Simplified to `YYYY-MM-DD HH:MM:SS` (was ISO 8601 with timezone)
- **`engine.py`**: Now uses `get_logger("core.engine")` with module-level logger (was inline `logging.getLogger(__name__)`)
- **`basic_etl.py`**: Integrated logging system (replaced `print()` with `logger` + `logged_operation`)
- **`logging/__init__.py`**: Exports updated to 7 items (`shutdown_logging`, `logged_operation`, `StepLogBridge`, `LoggingConfigBuilder`)
- **Documentation**: Updated `logging.md` and `logging-implementation-summary.md` with new format, utilities, and examples

### Tests
- **111 tests passing** across logging (52), logging utils (32), and engine (27) — 0 regressions

---

## [0.2.0] - 2026-03-10

### Added

#### 🔄 **BREAKING: Package Rename**
- **Renamed package** from `ias_workflow_engine` to `pyworkflow_engine`
- Updated all imports, configuration, and documentation
- Generic package name suitable for any project (not IAS-specific)
- Migration guide (`MIGRATION.md`) with complete upgrade instructions

#### 🏗️ **Phase 2: Comprehensive Persistence Layer**
- **Four complete persistence backends**:
  - `InMemoryPersistence`: Thread-safe, transaction support, memory estimation
  - `JSONFilePersistence`: Human-readable, atomic operations, cross-platform  
  - `SQLitePersistence`: ACID transactions, WAL mode, schema versioning
  - `SQLAlchemyPersistence`: Multi-database support, connection pooling, enterprise features
- **Base persistence interface** (`BasePersistence`) with comprehensive API:
  - CRUD operations for jobs, job runs, step runs, and step logs
  - Transaction management with context managers
  - Advanced querying with filters (status, time ranges, pagination)
  - Health checks and statistics
  - Error handling with custom exceptions
- **Optional dependencies** system:
  - `pip install pyworkflow-engine[sqlalchemy]` for SQL support
  - `pip install pyworkflow-engine[postgresql]` for PostgreSQL
  - `pip install pyworkflow-engine[mysql]` for MySQL support
- **WorkflowEngine integration**:
  - `run_with_persistence()` method for persistent execution
  - Automatic job and run storage during execution
  - Persistence property for easy backend switching

#### ⏱️ **Phase 1 Week 4: Timeout & Advanced Executors**
- **Thread-based timeout system** with proper cleanup and thread management
- **Advanced executor framework**:
  - `ThreadPoolStepExecutor`: Concurrent execution with configurable thread pools
  - `ProcessPoolStepExecutor`: Multi-process execution for CPU-intensive tasks
  - `AsyncStepExecutor`: Async/await support for I/O-bound operations
  - `RetryableExecutor`: Wrapper for automatic retry logic with configurable strategies
  - `ExecutorRegistry`: Centralized executor management and discovery
- **WorkflowEngine enhancements**:
  - Executor registry integration
  - Timeout configuration per step
  - Advanced execution strategies

#### 📝 **Comprehensive Examples & Documentation**
- Complete persistence backend examples (`examples/persistence_backends.py`)
- Simple persistence test (`examples/persistence_simple.py`)
- Timeout and executors demonstrations (`examples/timeout_and_executors.py`)
- Phase implementation guides in `docs/guides/`

#### 🧪 **Extensive Test Coverage**
- **185+ total tests** with 88% code coverage
- Comprehensive persistence layer testing (18 tests)
- Timeout and executor testing (24 tests)  
- Model validation and edge case coverage
- Integration testing across all components

### Changed

#### 🔄 **Breaking Changes**
- **Package name**: `ias_workflow_engine` → `pyworkflow_engine`
- **Import statements**: All imports must be updated
- **Installation**: `pip install pyworkflow-engine` (new PyPI name)
- **CLI command**: Updated entry point to `pyworkflow_engine.cli.main:cli`
- **Logger namespace**: `pyworkflow_engine.*` (updated from `ias_workflow_engine.*`)

#### 📦 **Package Configuration**
- Updated `pyproject.toml` with new package metadata
- Generic GitHub URLs for broader distribution
- Version bump to 0.2.0 to reflect breaking changes
- Enhanced optional dependencies structure

#### 🏗️ **Architecture Improvements**
- Zero-dependency core maintained (persistence base uses only stdlib)
- Lazy import system for optional backends
- Thread-safe operations across all components
- Enhanced error handling and validation

### Fixed
- API consistency issues in Step constructor parameters
- Parameter naming: `callable` (not `callable_func`), `dependencies` (not `depends_on`)
- StepType enumeration: `StepType.FUNCTION` (correct naming)
- Import path corrections across all modules
- Configuration file syntax errors

### Documentation
- Added comprehensive `MIGRATION.md` guide
- Updated all code examples with correct API usage
- Phase implementation summaries in `docs/guides/`
- API reference documentation improvements

---

## 📊 Project Statistics (v0.2.0)

### 📁 **Codebase Overview**
- **Total Lines of Code**: 7,069 lines (src/ only)
- **Python Modules**: 24 source files + 8 test files
- **Test Coverage**: 88% (185+ tests across 8 test modules)
- **Examples**: 7 complete working examples with documentation
- **Documentation**: 5+ comprehensive implementation guides

### 🏗️ **Architecture Components**
- **Core Engine**: Workflow orchestration, DAG resolution, execution management
- **Models**: 10+ immutable dataclasses with full validation
- **Executors**: 5 execution backends (Local, ThreadPool, ProcessPool, Async, Retryable)
- **Persistence**: 4 storage backends (Memory, JSON, SQLite, SQLAlchemy)
- **Logging**: Structured logging system with multiple formatters and handlers

### 🧪 **Testing & Quality**
- **Unit Tests**: 185+ tests across 8 test modules
- **Integration Tests**: Full workflow execution scenarios
- **Code Coverage**: 88% with detailed HTML reports
- **Static Analysis**: Ruff (linting) + MyPy (type checking)
- **Pre-commit Hooks**: Automated quality checks
- **Continuous Validation**: All examples tested and working

### 🚀 **Performance & Reliability**
- **Thread Safety**: All operations protected with appropriate locking
- **Memory Management**: Efficient resource usage with cleanup
- **Error Handling**: Comprehensive exception hierarchy with meaningful messages
- **Transaction Support**: ACID compliance across all persistence backends
- **Timeout Management**: Configurable timeouts with proper cleanup
- **Retry Logic**: Configurable retry strategies with exponential backoff

### 📦 **Package Structure**
```
pyworkflow_engine/
├── core/           # Zero-dependency core (engine, models, DAG, context)
├── persistence/    # Optional persistence backends  
├── logging/        # Structured logging system
└── adapters/       # Optional framework integrations
```

### 🎯 **Key Features Delivered**
- ✅ **Zero Framework Dependencies**: Pure Python stdlib core
- ✅ **Library-First Design**: Use as library or with framework adapters  
- ✅ **Production Ready**: Thread-safe, ACID transactions, comprehensive testing
- ✅ **Extensible Architecture**: Plugin system for executors and persistence
- ✅ **Developer Experience**: Rich examples, comprehensive documentation
- ✅ **Enterprise Ready**: Multi-database support, connection pooling, monitoring hooks

---

## [0.1.0-alpha] - 2026-03-10

### Added
- Initial release
- Core framework-free implementation  
- Basic executors (local, thread, async)
- In-memory persistence
- **Logging module**: stdlib-based structured logging (zero dependency)
  - `get_logger()` with hierarchical namespace
  - `LoggingConfig` dataclass for immutable configuration  
  - `StructuredFormatter` (console) and `JSONFormatter` (NDJSON)
  - `SQLiteLogHandler` with batch mode and query API
  - `create_queue_handler()` for async non-blocking logging
  - `configure_logging()` one-liner setup
- **Adapter structlog**: opt-in via `pip install pyworkflow-engine[structlog]`
- Development tooling (ruff, mypy, pytest)
