"""
Adapter persistence — implémentations concrètes du port BaseStorage.

Chaque backend implémente le contrat défini dans
``pyworkflow_engine.ports.storage.BaseStorage``.

Backends disponibles (sans dépendances optionnelles) :
    - :class:`InMemoryStorage`  — stockage en mémoire (tests/dev)
    - :class:`JSONFileStorage`  — stockage JSON sur disque
    - :class:`SQLiteStorage`    — SQLite via stdlib ``sqlite3``

Backend optionnel (``pip install pyworkflow-engine[sqlalchemy]``) :
    - :class:`SQLAlchemyStorage` — PostgreSQL / MySQL / SQLite via SQLAlchemy
"""

from __future__ import annotations


def __getattr__(name: str):
    """Lazy import — évite de charger SQLAlchemy si non installé."""
    _LAZY = {
        "InMemoryStorage": (".memory", "InMemoryStorage"),
        "JSONFileStorage": (".json_file", "JSONFileStorage"),
        "SQLiteStorage": (".sqlite", "SQLiteStorage"),
        "SQLAlchemyStorage": (".sqlalchemy", "SQLAlchemyStorage"),
    }

    if name in _LAZY:
        module_path, attr = _LAZY[name]
        import importlib

        try:
            module = importlib.import_module(module_path, __name__)
            value = getattr(module, attr)
            globals()[name] = value
            return value
        except ImportError as e:
            if "sqlalchemy" in module_path:
                raise ImportError(
                    "SQLAlchemy persistence requires: pip install pyworkflow-engine[sqlalchemy]"
                ) from e
            raise

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "InMemoryStorage",
    "JSONFileStorage",
    "SQLiteStorage",
    "SQLAlchemyStorage",
]
