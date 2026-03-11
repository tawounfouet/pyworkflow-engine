# Guide Logging : `pyworkflow-engine`

**Date**: 11 mars 2026  
**Status**: Implémenté (v2 — utilitaires, couleurs, adapters)  
**Principe**: Zero dépendance dans le core, structlog/snowflake en opt-in  

---

## 🎯 Architecture

Le système de logging suit le même principe que le reste du package : **stdlib dans le core, dépendances en adapters opt-in**.

```
┌──────────────────────────────────────────────────────────────┐
│  COUCHE 1 — Core (zero dépendance)                          │
│  logging/                                                    │
│  ├── __init__.py       # API publique (7 exports)            │
│  ├── config.py         # LoggingConfig (dataclass frozen)    │
│  ├── logger.py         # get_logger() + configure_logging()  │
│  ├── formatters.py     # StructuredFormatter (ANSI colors)   │
│  │                     # + JSONFormatter                     │
│  └── utils.py          # logged_operation, StepLogBridge,    │
│                        # LoggingConfigBuilder                │
├──────────────────────────────────────────────────────────────┤
│  COUCHE 2 — Handlers avancés (stdlib uniquement)             │
│  logging/                                                    │
│  └── handlers.py       # SQLiteLogHandler, create_queue_handler │
├──────────────────────────────────────────────────────────────┤
│  COUCHE 3 — Adapters (extras pip)                            │
│  adapters/                                                   │
│  ├── structlog/        # pip install pyworkflow-engine[structlog] │
│  │   ├── __init__.py                                         │
│  │   └── setup.py      # configure_structlog()               │
│  └── snowflake/        # pip install pyworkflow-engine[snowflake]│
│      ├── __init__.py                                         │
│      └── handler.py    # SnowflakeLogHandler                 │
└──────────────────────────────────────────────────────────────┘
```

### Pourquoi pas structlog dans le core ?

| Critère | stdlib `logging` | structlog |
|---|---|---|
| **Dépendance** | ✅ Zero | ❌ Package externe |
| **Contrat `dependencies = []`** | ✅ Respecté | ❌ Cassé |
| **QueueHandler async** | ✅ `logging.handlers` | ✅ Aussi |
| **JSON formatter** | ✅ `json` stdlib | ✅ Built-in |
| **File rotation** | ✅ `RotatingFileHandler` | ❌ Pas natif |
| **SQLite logs** | ✅ `sqlite3` stdlib | ❌ Nécessite adapter |
| **Processors avancés** | ❌ Manuel | ✅ Excellent |
| **Contextvars** | ❌ À gérer | ✅ Natif |

**→ Le core utilise la stdlib. Les utilisateurs qui veulent structlog l'activent en une ligne.**

---

## 🚀 Usage

### Basique (zero config)

```python
from pyworkflow_engine.logging import get_logger

# La lib est silencieuse par défaut (NullHandler, PEP 282)
logger = get_logger("my_module")
logger.info("This goes nowhere until configured")
```

### Configuration console

```python
from pyworkflow_engine.logging import configure_logging, LoggingConfig

# Format structuré lisible avec couleurs ANSI automatiques
configure_logging(LoggingConfig(level="DEBUG"))

logger = get_logger("core.engine")
logger.info("Workflow started", extra={"job_id": "abc-123"})
# → 2026-03-11 20:42:17 | INFO | core.engine | Workflow started
#   job_id=abc-123
#
# Couleurs ANSI par niveau (auto-détectées si terminal TTY) :
#   DEBUG   → bleu ciel       WARNING  → jaune
#   INFO    → cyan             ERROR    → rouge
#   CRITICAL → rouge vif       timestamp → gris
```

### Configuration avec le Builder

```python
from pyworkflow_engine.logging import configure_logging, LoggingConfigBuilder

# API fluide alternative au constructeur LoggingConfig
config = (LoggingConfigBuilder()
    .level("DEBUG")
    .json_output(False)
    .log_file("workflow.log", max_bytes=50*1024*1024, backup_count=10)
    .with_queue()
    .extra_fields(env="prod", service="etl-pipeline")
    .build())

configure_logging(config)
```

### Configuration JSON

```python
configure_logging(LoggingConfig(
    level="INFO",
    json_output=True,
    extra_fields={"service": "workflow-engine", "env": "production"},
))

logger = get_logger("core.engine")
logger.info("Workflow started", extra={"job_id": "abc-123"})
# → {"timestamp": "2026-03-11 20:42:17", "level": "INFO", 
#     "logger": "pyworkflow_engine.core.engine", "message": "Workflow started",
#     "service": "workflow-engine", "env": "production", "job_id": "abc-123"}
```

### Fichier rotatif

```python
configure_logging(LoggingConfig(
    level="DEBUG",
    log_file="workflows.log",
    log_file_max_bytes=10 * 1024 * 1024,  # 10 MB
    log_file_backup_count=5,
))
# → Console en mode structuré + fichier en JSON
```

### Logging asynchrone (Queue)

```python
configure_logging(LoggingConfig(
    level="INFO",
    enable_queue=True,  # Non-bloquant via QueueHandler
    log_file="workflows.log",
))
# Les logs sont mis en queue et écrits dans un thread séparé
# → Aucun impact sur la latence du workflow
```

### SQLite Handler

```python
import logging
from pyworkflow_engine.logging import configure_logging, get_logger, LoggingConfig
from pyworkflow_engine.logging.handlers import SQLiteLogHandler

configure_logging(LoggingConfig(level="DEBUG"))

# Ajouter le handler SQLite
db_handler = SQLiteLogHandler(
    db_path="workflow_logs.db",
    batch_size=10,  # Flush tous les 10 logs
)
get_logger().addHandler(db_handler)

# Logger normalement
logger = get_logger("core.engine")
logger.info("Step completed", extra={"step_id": "fetch", "duration_ms": 150})

# Requêter les logs
logs = db_handler.query_logs(level="ERROR", limit=50)
logs = db_handler.query_logs(logger_name="core", since=datetime(2026, 3, 10))
```

### Queue async + SQLite (production)

```python
from pyworkflow_engine.logging.handlers import SQLiteLogHandler, create_queue_handler

# Handler SQLite
sqlite_handler = SQLiteLogHandler("production_logs.db", batch_size=50)

# Wrapper async non-bloquant
q_handler, q_listener = create_queue_handler(sqlite_handler)
q_listener.start()

logger = get_logger()
logger.addHandler(q_handler)

# ... utilisation normale ...

# En fin de programme
q_listener.stop()
sqlite_handler.close()
```

### Adapter structlog (opt-in)

```bash
pip install pyworkflow-engine[structlog]
```

```python
from pyworkflow_engine.adapters.structlog import configure_structlog

# Branche structlog sur le logging du core
configure_structlog(level="DEBUG", json_output=False)

# Tous les logs du core passent maintenant par structlog
from pyworkflow_engine.logging import get_logger
logger = get_logger("core.engine")
logger.info("workflow started", extra={"job_id": "abc-123"})
# → Formaté par structlog avec couleurs, contexte, etc.
```

### Adapter Snowflake (opt-in)

```bash
pip install pyworkflow-engine[snowflake]
```

```python
import logging
from pyworkflow_engine.adapters.snowflake import SnowflakeLogHandler
from pyworkflow_engine.logging import get_logger, configure_logging, LoggingConfig

configure_logging(LoggingConfig(level="INFO"))

# Connexion factory injectable
def my_snowflake_connection():
    import snowflake.connector
    return snowflake.connector.connect(
        account="my_account", user="my_user", password="my_pass"
    )

# Handler Snowflake avec batching
handler = SnowflakeLogHandler(
    connection_factory=my_snowflake_connection,
    database="MONITORING_DB",
    schema="LOGS_SCHEMA",
    table="WORKFLOW_LOGS",
    batch_size=20,
)
get_logger().addHandler(handler)

# Logger normalement — les logs vont en console + Snowflake
logger = get_logger("etl.pipeline")
logger.info("Pipeline started", extra={"job_id": "abc-123"})

# En fin de programme
handler.close()
```

---

## 🔧 Utilitaires

### `logged_operation` — Traçabilité automatique

Context manager qui trace automatiquement le début, la durée et le résultat
(succès ou échec) d'une opération.

```python
from pyworkflow_engine.logging import get_logger, logged_operation, configure_logging, LoggingConfig

configure_logging(LoggingConfig(level="DEBUG"))
logger = get_logger("etl.pipeline")

with logged_operation(logger, "data extraction", source="customers.csv"):
    extract_data()

# → 2026-03-11 20:42:17 | INFO | etl.pipeline | Starting: data extraction
# → 2026-03-11 20:42:19 | INFO | etl.pipeline | Completed: data extraction (2.34s)

# En cas d'erreur :
with logged_operation(logger, "risky operation"):
    raise ValueError("boom")
# → 2026-03-11 20:42:19 | INFO  | etl.pipeline | Starting: risky operation
# → 2026-03-11 20:42:19 | ERROR | etl.pipeline | Failed: risky operation (0.00s)
#   Traceback: ValueError: boom
```

Le context manager yield le logger, permettant des logs intermédiaires :

```python
with logged_operation(logger, "ETL pipeline") as log:
    log.info("Step 1: extracting")
    extract()
    log.info("Step 2: transforming")
    transform()
    log.info("Step 3: loading")
    load()
```

### `StepLogBridge` — Pont logging ↔ StepRun

Connecte le dual-logging du projet : les logs émis via stdlib `logging`
sont automatiquement capturés dans les `StepLog` du `StepRun`, et donc
persistés avec les données d'exécution du workflow.

```python
import logging
from pyworkflow_engine.logging import StepLogBridge
from pyworkflow_engine.core.models.runtime import StepRun

step_run = StepRun(step_name="process_data", job_run_id="job-123")

# Brancher le bridge
bridge = StepLogBridge(step_run)
logger = logging.getLogger("my_step_logger")
logger.addHandler(bridge)
logger.setLevel(logging.DEBUG)

# Les logs stdlib sont capturés dans step_run.logs
logger.info("Processing 42 rows")
logger.warning("Skipped 3 invalid rows")

assert len(step_run.logs) == 2
assert step_run.logs[0].message == "Processing 42 rows"
assert step_run.logs[1].level == "WARNING"

# Combinaison puissante avec logged_operation :
from pyworkflow_engine.logging import logged_operation

with logged_operation(logger, "data processing"):
    logger.info("Row 1 done")
    logger.info("Row 2 done")
# → step_run.logs contient: Starting + Row 1 + Row 2 + Completed
```

---

## 🏗️ Patterns Recommandés

### Dans le core du package (pour les développeurs du moteur)

Le moteur utilise `get_logger()` avec un logger module-level :

```python
# core/engine.py — implémentation actuelle
from pyworkflow_engine.logging import get_logger

_logger = get_logger("core.engine")

class WorkflowEngine:
    def _log_workflow_error(self, job, job_run, error):
        _logger.error(
            "WORKFLOW ERROR [%s] %s: %s",
            job_run.job_run_id, job.name, error,
        )
```

### Dans une application Django

```python
# settings.py
from pyworkflow_engine.logging import configure_logging, LoggingConfig

configure_logging(LoggingConfig(
    level="INFO",
    json_output=True,
    log_file="/var/log/workflows/engine.log",
    enable_queue=True,
    extra_fields={"service": "django-app", "env": os.getenv("ENV", "dev")},
))
```

### Dans un notebook Jupyter

```python
from pyworkflow_engine.logging import configure_logging, LoggingConfig

configure_logging(LoggingConfig(level="DEBUG"))
# → Logs visibles dans le notebook en mode structuré
```

### Dans un script CLI

```python
from pyworkflow_engine.logging import configure_logging, LoggingConfig

configure_logging(LoggingConfig(
    level="DEBUG" if verbose else "INFO",
    json_output=False,
))
```

---

## 📊 Comparaison avec la proposition initiale

| Composant proposé | Ce qui est implémenté | Justification |
|---|---|---|
| `structlog` dans le core | stdlib `logging` + structlog en adapter | Préserve `dependencies = []` |
| `SQLAlchemy` log model | `sqlite3` SQLiteLogHandler | Stdlib, zero dépendance |
| `Pydantic` config | `dataclass(frozen=True)` | Stdlib, immuable, type-safe |
| `Typer` CLI | Intégré dans `cli/` existant (click) | Déjà prévu dans le projet |
| DB handler obligatoire | DB handler opt-in | L'utilisateur choisit ses handlers |

**Résultat** : 100% des fonctionnalités couvertes, 0 dépendance ajoutée au core.

---

## 🧪 Tests

```bash
# Lancer tous les tests logging
pytest tests/unit/test_logging.py tests/unit/test_logging_utils.py -v

# Avec couverture
pytest tests/unit/test_logging.py tests/unit/test_logging_utils.py -v --cov=pyworkflow_engine.logging
```

| Fichier de test | Couverture |
|---|---|
| `test_logging.py` | Config, logger, formatters, handlers, intégration (52 tests) |
| `test_logging_utils.py` | logged_operation, StepLogBridge, LoggingConfigBuilder (32 tests) |

Les tests sont 100% stdlib — pas de base de données externe, pas de broker, exécution < 1s.

---

## 📦 API Publique

```python
from pyworkflow_engine.logging import (
    get_logger,            # Logger dans le namespace pyworkflow_engine
    configure_logging,     # Configure le système complet (idempotent)
    shutdown_logging,      # Arrêt propre (flush + fermeture)
    LoggingConfig,         # Dataclass immuable de configuration
    LoggingConfigBuilder,  # Builder fluide pour LoggingConfig
    logged_operation,      # Context manager traçabilité opérations
    StepLogBridge,         # Handler pont logging ↔ StepRun.logs
)
```
