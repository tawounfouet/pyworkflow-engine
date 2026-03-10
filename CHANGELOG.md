# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure
- Core models (Job, Step, JobRun, StepRun)
- WorkflowEngine with DAG resolution
- Zero-dependency core implementation
- **Logging module** : stdlib-based structured logging (zero dépendance)
  - `get_logger()` with hierarchical namespace (`pyworkflow_engine.*`)
  - `LoggingConfig` dataclass for immutable configuration
  - `StructuredFormatter` (console) and `JSONFormatter` (NDJSON)
  - `SQLiteLogHandler` with batch mode and query API
  - `create_queue_handler()` for async non-blocking logging
  - `configure_logging()` one-liner setup
- **Adapter structlog** : opt-in via `pip install ias-workflow-engine[structlog]`

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [0.1.0-alpha] - 2026-03-10

### Added
- Initial release
- Core framework-free implementation
- Basic executors (local, thread, async)
- In-memory persistence
- Development tooling (ruff, mypy, pytest)
