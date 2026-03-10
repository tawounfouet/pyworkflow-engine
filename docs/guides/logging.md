# Guide Logging : `ias-workflow-engine`

**Date**: 10 mars 2026  
**Status**: Implémenté  
**Principe**: Zero dépendance dans le core, structlog en opt-in  

---

## 🎯 Architecture

Le système de logging suit le même principe que le reste du package : **stdlib dans le core, dépendances en adapters opt-in**.

```
┌──────────────────────────────────────────────────────────────┐
│  COUCHE 1 — Core (zero dépendance)                          │
│  logging/                                                    │
│  ├── __init__.py       # API publique                        │
│  ├── config.py         # LoggingConfig (dataclass frozen)    │
│  ├── logger.py         # get_logger() + configure_logging()  │
│  └── formatters.py     # StructuredFormatter, JSONFormatter  │
├──────────────────────────────────────────────────────────────┤
│  COUCHE 2 — Handlers avancés (stdlib uniquement)             │
│  logging/                                                    │
│  └── handlers.py       # SQLiteLogHandler, create_queue_handler │
├──────────────────────────────────────────────────────────────┤
│  COUCHE 3 — Adapters (extras pip)                            │
│  adapters/                                                   │
│  └── structlog/        # pip install ias-workflow-engine[structlog] │
│      ├── __init__.py                                         │
│      └── setup.py      # configure_structlog()               │
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
from ias_workflow_engine.logging import get_logger

# La lib est silencieuse par défaut (NullHandler, PEP 282)
logger = get_logger("my_module")
logger.info("This goes nowhere until configured")
```

### Configuration console

```python
from ias_workflow_engine.logging import configure_logging, LoggingConfig

# Format structuré lisible
configure_logging(LoggingConfig(level="DEBUG"))

logger = get_logger("core.engine")
logger.info("Workflow started", extra={"job_id": "abc-123"})
# → 2026-03-10T14:30:00+00:00 [INFO    ] core.engine — Workflow started
#     job_id=abc-123
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
# → {"timestamp": "2026-03-10T14:30:00+00:00", "level": "INFO", 
#     "logger": "ias_workflow_engine.core.engine", "message": "Workflow started",
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
from ias_workflow_engine.logging import configure_logging, get_logger, LoggingConfig
from ias_workflow_engine.logging.handlers import SQLiteLogHandler

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
from ias_workflow_engine.logging.handlers import SQLiteLogHandler, create_queue_handler

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
pip install ias-workflow-engine[structlog]
```

```python
from ias_workflow_engine.adapters.structlog import configure_structlog

# Branche structlog sur le logging du core
configure_structlog(level="DEBUG", json_output=False)

# Tous les logs du core passent maintenant par structlog
from ias_workflow_engine.logging import get_logger
logger = get_logger("core.engine")
logger.info("workflow started", extra={"job_id": "abc-123"})
# → Formaté par structlog avec couleurs, contexte, etc.
```

---

## 🏗️ Patterns Recommandés

### Dans le core du package (pour les développeurs du moteur)

```python
# core/engine.py
from ias_workflow_engine.logging import get_logger

logger = get_logger(__name__)  # → ias_workflow_engine.core.engine

class WorkflowEngine:
    def run(self, job, context=None):
        logger.info("Starting workflow", extra={
            "job_id": job.id, 
            "job_name": job.name,
            "step_count": len(job.steps),
        })
        # ...
        logger.info("Workflow completed", extra={
            "job_id": job.id,
            "status": result.status.value,
            "duration_ms": duration,
        })
```

### Dans une application Django

```python
# settings.py
from ias_workflow_engine.logging import configure_logging, LoggingConfig

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
from ias_workflow_engine.logging import configure_logging, LoggingConfig

configure_logging(LoggingConfig(level="DEBUG"))
# → Logs visibles dans le notebook en mode structuré
```

### Dans un script CLI

```python
from ias_workflow_engine.logging import configure_logging, LoggingConfig

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
# Lancer les tests du module logging
pytest tests/unit/test_logging.py -v

# Avec couverture
pytest tests/unit/test_logging.py -v --cov=ias_workflow_engine.logging
```

Les tests sont 100% stdlib — pas de base de données externe, pas de broker, exécution < 1s.
