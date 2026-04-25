#!/usr/bin/env python3
# filepath: /Users/awf/Projects/software-engineering/python-packages/pyworkflow-engine/scripts/python/migrate.py
"""
Script de migration — crée/met à jour les tables IA (ADR-017).

Usage::

    # Appliquer les migrations (créer les tables manquantes)
    python -m scripts.python.migrate

    # Voir le DDL sans exécuter
    python -m scripts.python.migrate --dry-run

    # Base de données personnalisée
    python -m scripts.python.migrate --db ./my_database.db

Équivalent de ``python manage.py migrate`` en Django.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ajouter le src/ au sys.path pour permettre les imports
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main() -> None:
    """Point d'entrée CLI pour la migration."""
    parser = argparse.ArgumentParser(
        prog="migrate",
        description="Crée/met à jour les tables de persistence IA (ADR-017).",
    )
    parser.add_argument(
        "--db",
        default="./workflow.db",
        help="Chemin vers la base de données SQLite (default: ./workflow.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le DDL sans l'exécuter.",
    )

    args = parser.parse_args()

    # Ensure models are registered by importing them
    import pyworkflow_engine.models.ai  # noqa: F401
    from pyworkflow_engine.adapters.storage.schema_generator import SchemaGenerator
    from pyworkflow_engine.ports.persistable import ModelRegistry

    models = ModelRegistry.get_all()
    print(f"📦 {len(models)} modèles enregistrés dans le ModelRegistry:")
    for table_name, model_cls in models.items():
        print(f"   • {table_name} → {model_cls.__name__}")
    print()

    if args.dry_run:
        print("🔍 Mode dry-run — DDL généré (non exécuté) :\n")
        ddl = SchemaGenerator.generate_full_schema()
        print(ddl)
        print(f"\n✅ {len(models)} tables seraient créées.")
    else:
        from pyworkflow_engine.adapters.storage.unified import UnifiedStorage

        db_path = Path(args.db).resolve()
        print(f"🗄️  Base de données : {db_path}")
        print(f"🚀 Migration en cours...\n")

        storage = UnifiedStorage(str(db_path))
        try:
            statements = storage.migrate()
            print(f"✅ Migration terminée — {len(statements)} instructions exécutées.")
            print()

            # Afficher les tables existantes
            tables = storage.get_table_names()
            print(f"📋 Tables existantes ({len(tables)}) :")
            for table in tables:
                print(f"   • {table}")
        finally:
            storage.close()


if __name__ == "__main__":
    main()
