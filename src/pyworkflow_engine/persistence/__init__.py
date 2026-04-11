"""
Persistence layer for the PyWorkflow Engine.

This module provides a pluggable persistence architecture that allows workflows
to be stored and retrieved from various backends while maintaining the zero-dependency
core principle.

Architecture:
    - BasePersistence: Abstract interface for all persistence backends
    - InMemoryPersistence: Fast in-memory storage (testing, development)
    - JSONFilePersistence: Simple file-based storage using JSON
    - SQLitePersistence: SQLite database storage using stdlib sqlite3
    - SQLAlchemyPersistence: Advanced SQL storage via optional SQLAlchemy

Usage:
    from pyworkflow_engine.persistence import InMemoryPersistence
    from pyworkflow_engine import WorkflowEngine

    persistence = InMemoryPersistence()
    engine = WorkflowEngine(persistence=persistence)

Optional Dependencies:
    - SQLAlchemy: pip install ias-workflow-engine[sqlalchemy]
    - PostgreSQL: pip install ias-workflow-engine[postgresql]
    - MySQL: pip install ias-workflow-engine[mysql]
"""


# Lazy imports for optional dependencies
def __getattr__(name: str):
    """Lazy import for optional persistence backends."""

    _LAZY_IMPORTS = {
        # Core persistence (no dependencies)
        "BasePersistence": (".base", "BasePersistence"),
        "InMemoryPersistence": (".memory", "InMemoryPersistence"),
        "JSONFilePersistence": (".json_file", "JSONFilePersistence"),
        "SQLitePersistence": (".sqlite", "SQLitePersistence"),
        # Optional persistence (requires extras)
        "SQLAlchemyPersistence": (".sqlalchemy", "SQLAlchemyPersistence"),
    }

    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        try:
            module = importlib.import_module(module_path, __name__)
            value = getattr(module, attr)
            # Cache in module namespace
            globals()[name] = value
            return value
        except ImportError as e:
            if "sqlalchemy" in module_path:
                raise ImportError(
                    "SQLAlchemy persistence requires: pip install ias-workflow-engine[sqlalchemy]"
                ) from e
            raise

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Core persistence interfaces
    "BasePersistence",
    # Built-in backends (no dependencies)
    "InMemoryPersistence",
    "JSONFilePersistence",
    "SQLitePersistence",
    # Optional backends (require extras)
    "SQLAlchemyPersistence",
]
