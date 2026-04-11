"""
Logging Avancé — Utilitaires, handlers et patterns avancés.

Démontre les fonctionnalités avancées :
- LoggingConfigBuilder (API fluide)
- logged_operation (traçabilité automatique)
- StepLogBridge (pont logging → StepRun)
- SQLiteLogHandler (persistance SQLite)
- Queue async (logging non-bloquant)
- Combinaison des utilitaires

Run: uv run python examples/logging_advanced.py
"""

import time
import logging
from pyworkflow_engine.logging import (
    get_logger,
    configure_logging,
    shutdown_logging,
    LoggingConfig,
    LoggingConfigBuilder,
    logged_operation,
    StepLogBridge,
)
from pyworkflow_engine.logging.handlers import SQLiteLogHandler, create_queue_handler


def example_config_builder():
    """1. LoggingConfigBuilder — API fluide pour construire une config."""
    print("\n" + "=" * 60)
    print("1. LoggingConfigBuilder (API Fluide)")
    print("=" * 60)

    config = (
        LoggingConfigBuilder()
        .level("DEBUG")
        .json_output(False)
        .extra_fields(service="etl-pipeline", env="demo")
        .build()
    )

    configure_logging(config)
    logger = get_logger("demo.builder")

    logger.info("Config créée avec le builder", extra={"step": "init"})
    logger.debug("Les extra_fields globaux apparaissent automatiquement")

    print("\n   → LoggingConfigBuilder offre une alternative lisible à LoggingConfig()")


def example_logged_operation_success():
    """2. logged_operation — traçabilité automatique (succès)."""
    print("\n" + "=" * 60)
    print("2. logged_operation — Succès")
    print("=" * 60)

    configure_logging(LoggingConfig(level="DEBUG"))
    logger = get_logger("demo.operations")

    # Opération simple qui réussit
    with logged_operation(logger, "data extraction", source="customers.csv"):
        time.sleep(0.1)  # Simule du travail
        logger.debug("42 lignes extraites")

    print("\n   → Début, durée et succès tracés automatiquement.")


def example_logged_operation_failure():
    """3. logged_operation — traçabilité automatique (échec)."""
    print("\n" + "=" * 60)
    print("3. logged_operation — Échec")
    print("=" * 60)

    configure_logging(LoggingConfig(level="DEBUG"))
    logger = get_logger("demo.operations")

    # Opération qui échoue
    try:
        with logged_operation(logger, "data transformation", table="orders"):
            time.sleep(0.05)
            raise ValueError("Colonne 'price' manquante dans le dataset")
    except ValueError:
        pass  # L'erreur est loggée automatiquement, on continue

    print("\n   → L'échec est tracé avec durée + traceback, puis re-raise.")


def example_logged_operation_nested():
    """4. logged_operation — opérations imbriquées (pipeline ETL)."""
    print("\n" + "=" * 60)
    print("4. logged_operation — Pipeline Imbriqué")
    print("=" * 60)

    configure_logging(LoggingConfig(level="DEBUG"))
    logger = get_logger("demo.pipeline")

    with logged_operation(logger, "ETL pipeline") as log:
        with logged_operation(log, "extraction"):
            time.sleep(0.05)

        with logged_operation(log, "transformation"):
            log.info("Normalisation des données")
            time.sleep(0.03)

        with logged_operation(log, "chargement"):
            log.info("Insertion en base", extra={"rows": 150})
            time.sleep(0.02)

    print("\n   → Chaque sous-opération a sa propre trace durée/résultat.")


def example_step_log_bridge():
    """5. StepLogBridge — pont entre logging stdlib et StepRun."""
    print("\n" + "=" * 60)
    print("5. StepLogBridge (logging → StepRun)")
    print("=" * 60)

    from pyworkflow_engine.models.run import StepRun

    # Créer un StepRun (comme le moteur le fait en interne)
    step_run = StepRun(step_name="process_data", job_run_id="job-demo-001")

    # Brancher le bridge
    bridge = StepLogBridge(step_run)
    step_logger = logging.getLogger("step.process_data")
    step_logger.addHandler(bridge)
    step_logger.setLevel(logging.DEBUG)

    # Les logs passent dans step_run.logs
    step_logger.info("Début du traitement")
    step_logger.debug("Lecture du fichier source")
    step_logger.warning("3 lignes invalides ignorées")
    step_logger.info("Traitement terminé", extra={"rows_processed": 42})

    # Vérifier les logs capturés
    print(f"\n   Logs capturés dans StepRun: {len(step_run.logs)}")
    for log in step_run.logs:
        print(f"   [{log.level:<8}] {log.message}")

    # Nettoyage
    step_logger.removeHandler(bridge)


def example_step_log_bridge_with_operation():
    """6. StepLogBridge + logged_operation combinés."""
    print("\n" + "=" * 60)
    print("6. StepLogBridge + logged_operation (combinés)")
    print("=" * 60)

    from pyworkflow_engine.models.run import StepRun

    step_run = StepRun(step_name="etl_step", job_run_id="job-demo-002")

    bridge = StepLogBridge(step_run)
    step_logger = logging.getLogger("step.etl")
    step_logger.addHandler(bridge)
    step_logger.setLevel(logging.DEBUG)

    # Les logged_operation génèrent des logs qui sont aussi capturés
    with logged_operation(step_logger, "data processing"):
        step_logger.info("Row batch 1/3 done", extra={"batch_size": 100})
        step_logger.info("Row batch 2/3 done", extra={"batch_size": 100})
        step_logger.info("Row batch 3/3 done", extra={"batch_size": 50})

    print(f"\n   Logs capturés : {len(step_run.logs)}")
    for log in step_run.logs:
        print(f"   [{log.level:<8}] {log.message}")
    print("\n   → Start + 3 batches + Completed = 5 logs dans StepRun")

    step_logger.removeHandler(bridge)


def example_sqlite_handler():
    """7. SQLiteLogHandler — persistance SQLite avec requêtes."""
    print("\n" + "=" * 60)
    print("7. SQLiteLogHandler (persistance SQLite)")
    print("=" * 60)

    configure_logging(LoggingConfig(level="DEBUG"))

    # Handler SQLite en mémoire (pas de fichier créé pour la démo)
    db_handler = SQLiteLogHandler(db_path=":memory:", batch_size=5)
    root = get_logger()
    root.addHandler(db_handler)

    logger = get_logger("demo.sqlite")

    # Écrire des logs
    logger.info("Workflow started", extra={"job_id": "job-100"})
    logger.debug("Step fetch_data executing")
    logger.info("Step fetch_data completed", extra={"rows": 250, "duration_ms": 340})
    logger.warning("Step transform_data: null values found", extra={"nulls": 12})
    logger.error("Step load_data failed", extra={"reason": "connection timeout"})
    logger.info("Workflow retried", extra={"attempt": 2})

    # Forcer le flush du batch
    db_handler.flush()

    # Requêter les logs depuis SQLite
    all_logs = db_handler.query_logs(limit=10)
    print(f"\n   Logs en base : {len(all_logs)}")
    for log in all_logs:
        print(f"   [{log['level']:<8}] {log['logger']:<25} {log['message']}")

    # Requête filtrée par niveau
    errors = db_handler.query_logs(level="ERROR")
    print(f"\n   Erreurs uniquement : {len(errors)}")
    for log in errors:
        print(f"   [{log['level']}] {log['message']} — extra: {log.get('extra', '')}")

    # Nettoyage
    root.removeHandler(db_handler)
    db_handler.close()


def example_queue_async():
    """8. Queue Handler — logging asynchrone non-bloquant."""
    print("\n" + "=" * 60)
    print("8. Queue Handler (async non-bloquant)")
    print("=" * 60)

    configure_logging(
        LoggingConfig(
            level="DEBUG",
            enable_queue=True,
        )
    )
    logger = get_logger("demo.queue")

    # Les logs sont mis en queue et écrits dans un thread séparé
    logger.info("Ce log est non-bloquant (via QueueHandler)")
    logger.debug("Aucun impact sur la latence du workflow")
    logger.warning("Même les warnings passent par la queue")

    # Laisser le temps au listener de consommer la queue
    time.sleep(0.1)
    print("\n   → Les logs passent par QueueHandler → QueueListener → handlers.")
    print("   → Aucun appel de logging ne bloque le thread principal.")


def example_production_pattern():
    """9. Pattern production — SQLite async via queue."""
    print("\n" + "=" * 60)
    print("9. Pattern Production (Queue + SQLite)")
    print("=" * 60)

    # Créer un handler SQLite
    sqlite_handler = SQLiteLogHandler(db_path=":memory:", batch_size=10)

    # Wrapper async non-bloquant
    q_handler, q_listener = create_queue_handler(sqlite_handler)
    q_listener.start()

    # Configurer le logging
    configure_logging(LoggingConfig(level="INFO"))
    root = get_logger()
    root.addHandler(q_handler)

    logger = get_logger("demo.production")

    # Simuler un workflow
    logger.info("Workflow production started", extra={"job_id": "prod-001"})
    for i in range(5):
        logger.info(f"Processing batch {i+1}/5", extra={"batch": i + 1})
        time.sleep(0.02)
    logger.info("Workflow completed", extra={"status": "success"})

    # Attendre que la queue soit consommée
    time.sleep(0.2)

    # Vérifier les logs persistés
    sqlite_handler.flush()
    logs = sqlite_handler.query_logs(limit=20)
    print(f"\n   Logs persistés en SQLite (via queue async) : {len(logs)}")
    for log in logs:
        print(f"   [{log['level']:<8}] {log['message']}")

    # Arrêt propre
    q_listener.stop()
    root.removeHandler(q_handler)
    sqlite_handler.close()


def main():
    """Exécute tous les exemples de logging avancé."""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     pyworkflow-engine — Advanced Logging Examples       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    example_config_builder()
    example_logged_operation_success()
    example_logged_operation_failure()
    example_logged_operation_nested()
    example_step_log_bridge()
    example_step_log_bridge_with_operation()
    example_sqlite_handler()
    example_queue_async()
    example_production_pattern()

    shutdown_logging()

    print("\n" + "=" * 60)
    print("✅ Tous les exemples avancés exécutés avec succès !")
    print("=" * 60)


if __name__ == "__main__":
    main()
