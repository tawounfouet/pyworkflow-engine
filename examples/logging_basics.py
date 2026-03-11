"""
Logging Basics — Configuration et utilisation du système de logging.

Démontre les fonctionnalités de base :
- Configuration console (format structuré avec couleurs)
- Configuration JSON (machine-parseable)
- Fichier rotatif
- Champs extra globaux et par message
- Arrêt propre avec shutdown_logging

Run: uv run python examples/logging_basics.py
"""

from pyworkflow_engine.logging import (
    get_logger,
    configure_logging,
    shutdown_logging,
    LoggingConfig,
)


def example_zero_config():
    """1. Zero config — la librairie est silencieuse par défaut (PEP 282)."""
    print("\n" + "=" * 60)
    print("1. Zero Config (NullHandler — silencieux)")
    print("=" * 60)

    logger = get_logger("my_module")
    logger.info("Ce message ne s'affiche pas (NullHandler par défaut)")
    print("   → Aucun log affiché, comme prévu pour une librairie.")


def example_console_structured():
    """2. Format structuré console avec couleurs ANSI automatiques."""
    print("\n" + "=" * 60)
    print("2. Console Structurée (couleurs ANSI)")
    print("=" * 60)

    configure_logging(LoggingConfig(level="DEBUG"))
    logger = get_logger("demo.structured")

    logger.debug("Variable initialisée", extra={"var": "x", "value": 42})
    logger.info("Workflow démarré", extra={"job_id": "job-001"})
    logger.warning("Fichier volumineux détecté", extra={"size_mb": 512})
    logger.error("Connexion perdue", extra={"host": "db.example.com", "retry": 3})
    logger.critical("Espace disque insuffisant", extra={"free_gb": 0.2})


def example_console_json():
    """3. Format JSON pour collecteurs de logs (ELK, Datadog, etc.)."""
    print("\n" + "=" * 60)
    print("3. Console JSON (machine-parseable)")
    print("=" * 60)

    configure_logging(LoggingConfig(level="INFO", json_output=True))
    logger = get_logger("demo.json")

    logger.info("Pipeline started", extra={"pipeline": "etl-daily", "env": "staging"})
    logger.warning("Slow query", extra={"query_ms": 1500, "table": "customers"})


def example_extra_fields():
    """4. Champs extra globaux — ajoutés à chaque log automatiquement."""
    print("\n" + "=" * 60)
    print("4. Champs Extra Globaux")
    print("=" * 60)

    configure_logging(LoggingConfig(
        level="INFO",
        extra_fields={"service": "payment-api", "env": "production", "version": "2.1.0"},
    ))
    logger = get_logger("demo.extras")

    logger.info("Requête reçue", extra={"endpoint": "/pay", "method": "POST"})
    logger.info("Transaction validée", extra={"tx_id": "tx-9876"})
    print("\n   → Chaque log contient service, env, version + les extras locaux.")


def example_file_rotation():
    """5. Fichier rotatif — console + fichier JSON avec rotation automatique."""
    print("\n" + "=" * 60)
    print("5. Fichier Rotatif (console + fichier JSON)")
    print("=" * 60)

    import tempfile
    import os

    log_file = os.path.join(tempfile.gettempdir(), "pyworkflow_demo.log")

    configure_logging(LoggingConfig(
        level="DEBUG",
        log_file=log_file,
        log_file_max_bytes=1024 * 1024,  # 1 MB
        log_file_backup_count=3,
    ))
    logger = get_logger("demo.file")

    logger.info("Ce log va en console ET dans le fichier")
    logger.debug("Debug info aussi persistée en JSON dans le fichier")

    # Vérifier le contenu du fichier
    shutdown_logging()  # Flush avant lecture

    with open(log_file, encoding="utf-8") as f:
        content = f.read()
    print(f"\n   → Fichier créé : {log_file}")
    print(f"   → Contenu ({len(content)} bytes) :")
    for line in content.strip().split("\n"):
        print(f"     {line[:100]}...")

    # Nettoyage
    os.remove(log_file)


def example_level_filtering():
    """6. Filtrage par niveau — seuls les logs >= niveau configuré passent."""
    print("\n" + "=" * 60)
    print("6. Filtrage par Niveau (WARNING)")
    print("=" * 60)

    configure_logging(LoggingConfig(level="WARNING"))
    logger = get_logger("demo.filter")

    logger.debug("Invisible (DEBUG < WARNING)")
    logger.info("Invisible aussi (INFO < WARNING)")
    logger.warning("✓ Visible (WARNING)")
    logger.error("✓ Visible (ERROR)")
    logger.critical("✓ Visible (CRITICAL)")


def main():
    """Exécute tous les exemples de logging basique."""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       pyworkflow-engine — Logging Basics Examples       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    example_zero_config()
    example_console_structured()
    example_console_json()
    example_extra_fields()
    example_file_rotation()
    example_level_filtering()

    # Arrêt propre
    shutdown_logging()

    print("\n" + "=" * 60)
    print("✅ Tous les exemples exécutés avec succès !")
    print("=" * 60)


if __name__ == "__main__":
    main()
