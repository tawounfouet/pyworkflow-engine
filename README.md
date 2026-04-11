<p align="center">
  <strong>PyWorkflow Engine</strong><br>
  <em>Pure-Python workflow orchestration — zero dependencies, pluggable everything.</em>
</p>

<p align="center">
  <a href="https://github.com/awf/pyworkflow-engine/actions"><img src="https://img.shields.io/github/actions/workflow/status/awf/pyworkflow-engine/ci.yml?branch=main&style=flat-square&label=CI" alt="CI"></a>
  <a href="https://pypi.org/project/pyworkflow-engine/"><img src="https://img.shields.io/pypi/v/pyworkflow-engine?style=flat-square&color=blue" alt="PyPI version"></a>
  <a href="https://pypi.org/project/pyworkflow-engine/"><img src="https://img.shields.io/pypi/pyversions/pyworkflow-engine?style=flat-square" alt="Python versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/awf/pyworkflow-engine?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/dependencies-0-brightgreen?style=flat-square" alt="Zero deps">
  <img src="https://img.shields.io/badge/architecture-hexagonal-blueviolet?style=flat-square" alt="Hexagonal">
  <img src="https://img.shields.io/badge/tests-535%20passed-success?style=flat-square" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-84%25-yellowgreen?style=flat-square" alt="Coverage">
</p>

---

## Why PyWorkflow Engine?

Most workflow libraries force you into a framework. PyWorkflow Engine takes the opposite approach: **the core runs on the standard library alone**. Bring your own database, broker, or web framework — each integration is an opt-in adapter.

**Key principles:**

- 🚀 **Zero core dependencies** — stdlib only; extras are opt-in.
- 🏛️ **Hexagonal architecture** — clean separation between [ports](src/pyworkflow_engine/ports/) (interfaces) and [adapters](src/pyworkflow_engine/adapters/) (implementations).
- 🎨 **Dual API** — Declarative `@step`/`@job` decorators *and* imperative `Job`/`Step` builders.
- 🔧 **Pluggable** — Swap executors, persistence backends, and triggers without touching business logic.
- ⚡ **Concurrent** — Thread pool, process pool, and async executors built in.
- 🎯 **Type-safe** — Dataclasses + strict mypy throughout.
- 🌐 **Runs anywhere** — Notebooks, scripts, Django, FastAPI, CLI.

---

## Quick Start

### Installation

```bash
pip install pyworkflow-engine     


# Le mode éditable (`-e`) permet de modifier le code source sans réinstaller.

# Installation minimale (plan, journal, balance, états financiers, fiscalité)
pip install -e .

# Installation avec les outils de développement (pytest, ruff, mypy)
pip install -e ".[dev]"

# Installation avec la CLI (flowledger balance, flowledger statements)
pip install -e ".[dev,cli,api,tui,gui]"
       # core (zero dependencies)
```

Need more? Pick your extras:

| Extra | What it adds | Install |
|-------|-------------|---------|
| `celery` | Distributed execution (Celery + Redis) | `pip install pyworkflow-engine[celery]` |
| `sqlalchemy` | Database persistence | `pip install pyworkflow-engine[sqlalchemy]` |
| `snowflake` | Snowflake connector | `pip install pyworkflow-engine[snowflake]` |
| `django` | Django integration | `pip install pyworkflow-engine[django]` |
| `fastapi` | FastAPI integration | `pip install pyworkflow-engine[fastapi]` |
| `structlog` | Structured logging | `pip install pyworkflow-engine[structlog]` |
| `cli` | CLI with Click + Rich | `pip install pyworkflow-engine[cli]` |
| `all` | Everything above | `pip install pyworkflow-engine[all]` |

### Decorator API *(recommended, v0.5.0+)*

```python
from pyworkflow_engine import step, job, WorkflowEngine

@step(name="fetch", timeout=30.0)
def fetch_data(source: str = "api") -> dict:
    return {"records": [1, 2, 3], "source": source}

@step(name="transform", dependencies=["fetch"])
def transform(records: list | None = None) -> dict:
    return {"transformed": [r * 10 for r in (records or [])]}

@job(name="ETL Pipeline")
def etl_pipeline():
    fetch_data()
    transform()

engine = WorkflowEngine()
result = engine.run(etl_pipeline.build(), initial_context={"source": "db"})

print(result.status)       # RunStatus.SUCCESS
print(result.output_data)  # {"transformed": [10, 20, 30]}
```

> **Automatic injection** — parameters resolve in order: dependency outputs → initial context → default value → `None`.
> Functions stay **unit-testable** without a runner: `fetch_data(source="test")`.

### Imperative API

```python
from pyworkflow_engine import Job, Step, StepType, WorkflowEngine
from pyworkflow_engine.config import WorkflowConfig, EngineConfig

def fetch_data(context):
    return {"records": [1, 2, 3]}

def transform(context):
    records = context.get_step_output("fetch", {}).get("records", [])
    return {"transformed": [r * 10 for r in records]}

etl = Job(
    name="ETL Pipeline",
    steps=[
        Step(name="fetch", step_type=StepType.FUNCTION, handler=fetch_data),
        Step(name="transform", step_type=StepType.FUNCTION, handler=transform,
             dependencies=["fetch"]),
    ],
)

engine = WorkflowEngine(config=WorkflowConfig(engine=EngineConfig(parallel=True, max_workers=2)))
result = engine.run(etl)
```

---

## Architecture

PyWorkflow Engine follows **hexagonal architecture** (Ports & Adapters) since v0.6.0.
See [ADR-006](docs/changelog/2026-04-11_adr_006_hexagonal-ports-adapters.md) for the full rationale.

```
                        ┌──────────────────────────────────┐
                        │       WorkflowEngine (facade)     │
                        └──────────┬───────────────────────┘
                                   │
               ┌───────────────────┼───────────────────┐
               ▼                   ▼                   ▼
        ┌─────────────┐   ┌──────────────┐   ┌──────────────┐
        │   engine/    │   │   models/     │   │  decorators/ │
        │   runner     │   │   dataclasses │   │  @step @job  │
        └──────┬───────┘   └──────────────┘   └──────────────┘
               │
               │  depends on interfaces only
               ▼
        ┌─────────────────────────────────────────────────┐
        │                    ports/                        │
        │  executor.py · persistence.py · trigger.py      │
        │  (pure ABCs — no implementation detail)         │
        └──────────────────────┬──────────────────────────┘
                               │
                               │  implemented by
                               ▼
        ┌─────────────────────────────────────────────────┐
        │                  adapters/                       │
        │  executors/    local · thread · process · async  │
        │  persistence/  memory · json · sqlite · sqla    │
        │  triggers/     manual · schedule/cron           │
        │  celery/       (v0.7.0 — distributed execution) │
        │  snowflake/ · structlog/ · api/ · cli/ · …      │
        └─────────────────────────────────────────────────┘
```

**Rule:** `engine/` depends on `ports/` only. `adapters/` implements `ports/`. Business logic never imports a concrete adapter.

---

## Project Structure

```
pyworkflow-engine/
├── src/pyworkflow_engine/
│   ├── __init__.py            # PEP 562 lazy imports, public API
│   ├── facade.py              # WorkflowEngine — assembles the stack
│   ├── exceptions.py          # Domain exceptions
│   ├── py.typed               # PEP 561 marker
│   ├── engine/                # Core execution logic
│   │   ├── runner.py          # WorkflowRunner (sequential + DAG)
│   │   ├── parallel_runner.py # ParallelRunner (concurrent execution)
│   │   └── context.py         # WorkflowContext (step I/O routing)
│   ├── models/                # Pure dataclasses
│   │   ├── job.py             # Job, job builder
│   │   ├── step.py            # Step, SubJob
│   │   ├── run.py             # JobRun, StepRun, StepLog
│   │   └── enums.py           # StepType, RunStatus, ExecutorType, …
│   ├── decorators/            # Declarative API
│   │   ├── step_decorator.py  # @step + StepSpec
│   │   └── job_decorator.py   # @job + JobBuilder
│   ├── config/                # WorkflowConfig, EngineConfig
│   ├── logging/               # Structured logging
│   ├── ports/                 # ⬡ Pure interfaces (ABCs)
│   │   ├── executor.py        # BaseExecutor, ExecutorRegistry
│   │   ├── persistence.py     # BaseStorage + exceptions
│   │   └── trigger.py         # BaseTrigger, TriggerState
│   └── adapters/              # ⬡ Concrete implementations
│       ├── executors/         # Local, ThreadPool, ProcessPool, Async, Retryable
│       ├── persistence/       # InMemory, JSON, SQLite, SQLAlchemy
│       ├── triggers/          # Manual, Schedule/Cron
│       ├── celery/            # Distributed execution (v0.7.0)
│       ├── snowflake/         # Snowflake integration
│       ├── structlog/         # structlog adapter
│       └── api/ cli/ mcp/ …   # Future interface adapters
├── tests/
│   ├── unit/                  # Fast, isolated tests
│   ├── integration/           # Cross-component tests
│   ├── executors/             # Executor-specific tests
│   ├── persistence/           # Persistence-specific tests
│   └── triggers/              # Trigger-specific tests
├── docs/
│   ├── changelog/             # ADR-001 → ADR-007
│   └── guides/                # Action plans, migration guides
├── examples/                  # Runnable examples
├── pyproject.toml             # Hatch build, extras, tool config
├── CHANGELOG.md
└── LICENSE                    # MIT
```

---

## Testing

```bash
# Run the full suite
pytest

# With coverage report
pytest --cov=pyworkflow_engine --cov-report=term-missing

# Run a specific category
pytest tests/unit/
pytest tests/executors/
pytest tests/persistence/
```

| Metric | Value |
|--------|-------|
| Total tests | 535 |
| Coverage | 84 % |
| Async tests | via `pytest-asyncio` |
| Linting | `ruff` |
| Type checking | `mypy --strict` |

---

## Roadmap

| Version | Milestone | Status |
|---------|-----------|--------|
| v0.3.0 | Modular refactoring (God Object → specialized components) | ✅ Done |
| v0.4.0 | Triggers, ParallelRunner, ADR documentation | ✅ Done |
| v0.5.0 | Declarative `@step` / `@job` API ([ADR-005](docs/changelog/2026-04-11_adr_005_decorator-api.md)) | ✅ Done |
| **v0.6.0** | **Hexagonal architecture — `ports/` + `adapters/`** ([ADR-006](docs/changelog/2026-04-11_adr_006_hexagonal-ports-adapters.md)) | ✅ **Current** |
| v0.7.0 | Celery distributed executor ([ADR-007](docs/changelog/2026-04-11_adr_007_celery-adapter-integration.md)) | 🔜 Next |
| v0.8.0 | CLI + MCP interface adapters | 📋 Planned |
| v1.0.0 | Stable public API, full documentation | 🎯 Goal |

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Setup dev environment
git clone https://github.com/awf/pyworkflow-engine.git
cd pyworkflow-engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# Verify everything works
pytest
ruff check src/ tests/
mypy src/
```

---

## License

[MIT](LICENSE) © 2026 IAS

---

<p align="center">
  <sub>Built with ❤️ as a pure Python library — extract workflow logic from monoliths, run it anywhere.</sub>
</p>
