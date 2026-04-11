# ADR-004 — Style d'imports et introduction d'un module `config/`

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-004                             |
| **Date**    | 11 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-002 (refactoring modulaire) |

---

## Contexte

Deux questions architecturales de fond ont été soulevées lors de la revue du code de `src/pyworkflow_engine` :

1. **Style des imports internes** : l'ensemble du package utilise des imports relatifs (`from .engine.context import …`). Est-ce conforme aux standards Python pour un package redistribuable ?

2. **Centralisation de la configuration** : les paramètres de configuration (max_retries, pool_size, log_level, stratégie d'exécution…) sont actuellement dispersés dans plusieurs sous-modules sans point d'entrée unifié. Faut-il introduire un dossier `config/` ?

Ces deux décisions doivent être tranchées avant d'engager des modifications de code, car elles impactent l'ensemble de l'arborescence `src/pyworkflow_engine/`.

---

## Décision 1 — Migrer vers les imports absolus

### Constat actuel

Tous les fichiers du package utilisent des imports relatifs explicites :

```python
# facade.py — état actuel
from .engine.context import WorkflowContext
from .engine.dag import DAGResolver
from .engine.parallel_runner import ParallelRunner
from .executors import BaseExecutor, ExecutorRegistry
from .persistence.base import PersistenceError
from .logging import get_logger
from .models import Job, JobRun, RunStatus, StepType
```

### Analyse

| Critère | Imports relatifs | Imports absolus |
|---|---|---|
| PEP 8 | Acceptables (mais absolus recommandés) | ✅ Recommandés |
| Lisibilité à 2+ niveaux (`from ...models`) | ❌ Dégradée | ✅ Toujours claire |
| Refactoring (renommage du package) | ✅ Rien ne casse | ❌ Mise à jour globale |
| Refactoring (déplacement d'un module) | ❌ Les `.` changent | ✅ Import stable |
| Standard des packages redistribuables | ❌ Minoritaire | ✅ Dominant (FastAPI, Pydantic, SQLAlchemy, Celery) |
| Outils (mypy, ruff, IDE) | Supporté | ✅ Résolution plus fiable |
| Messages d'erreur (`ImportError`) | Parfois cryptiques | ✅ Chemin complet visible |

### Décision

**→ Migrer vers les imports absolus** dans tout `src/pyworkflow_engine/`.

**Exception tolérée** : les fichiers `__init__.py` d'un sous-package peuvent conserver des imports relatifs de niveau 1 pour leurs re-exports internes (ex. `from .context import WorkflowContext`), car le `__init__.py` *est* le package lui-même. Cette exception est commune dans l'écosystème Python.

### Règle de style appliquée

```toml
# pyproject.toml — section ruff
[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"   # interdit les imports relatifs depuis sous-modules
```

La règle `TID252` de ruff détectera et pourra corriger automatiquement les violations.

### Exemple de transformation

```python
# Avant
from .engine.context import WorkflowContext
from .engine.dag import DAGResolver
from .exceptions import WorkflowFailed, WorkflowError
from .models import Job, JobRun, RunStatus, StepType

# Après
from pyworkflow_engine.engine.context import WorkflowContext
from pyworkflow_engine.engine.dag import DAGResolver
from pyworkflow_engine.exceptions import WorkflowFailed, WorkflowError
from pyworkflow_engine.models import Job, JobRun, RunStatus, StepType
```

---

## Décision 2 — Introduire un module `config/`

### Constat actuel

La configuration est actuellement dispersée :

- `engine/runner.py` : paramètres d'exécution inline
- `engine/retry.py` : `RetryHandler()` sans config centralisée
- `executors/` : chaque executor définit ses propres paramètres
- `logging/config.py` : configuration du logging isolée
- `facade.py` : `parallel`, `max_workers` passés directement au constructeur

### Analyse

| Critère | Sans `config/` | Avec `config/` |
|---|---|---|
| Nombre de sources de paramétrage | 6+ dispersées | 1 point d'entrée |
| Testabilité | Patching de variables et constructeurs | Injection d'un objet `WorkflowConfig` |
| Extensibilité (nouveaux adapters) | Chaque adapter gère seul | Schéma validé et documenté |
| Cohérence avec l'architecture modulaire | ❌ Exception notable | ✅ Cohérent avec engine/, executors/, etc. |
| Risque d'over-engineering | Faible (archi déjà à 6+ modules) | Proportionné |

### Décision

**→ Introduire un module `config/`** avec une structure à 3 niveaux :

```
src/pyworkflow_engine/config/
├── __init__.py          # Re-export de WorkflowConfig
├── base.py              # WorkflowConfig (dataclass frozen, point d'entrée unique)
├── engine.py            # EngineConfig (max_retries, timeout, retry_delay)
├── executor.py          # ExecutorConfig (strategy, pool_size, max_workers)
└── logging.py           # LoggingConfig (absorbe logging/config.py à terme)
```

### Schéma de configuration cible

```python
# config/engine.py
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class EngineConfig:
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    default_timeout_seconds: Optional[float] = None
    parallel: bool = False

# config/executor.py
@dataclass(frozen=True)
class ExecutorConfig:
    strategy: str = "local"   # local | thread_pool | process_pool | async
    pool_size: int = 4
    max_workers: Optional[int] = None

# config/logging.py
@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    format: str = "text"      # text | json

# config/base.py
@dataclass(frozen=True)
class WorkflowConfig:
    engine: EngineConfig = field(default_factory=EngineConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
```

### Impact sur `WorkflowEngine`

```python
# facade.py — après migration
from pyworkflow_engine.config import WorkflowConfig

class WorkflowEngine:
    def __init__(self, config: WorkflowConfig | None = None, ...):
        self._config = config or WorkflowConfig()
        # parallel et max_workers lus depuis config.engine
```

L'API existante (`WorkflowEngine(parallel=True, max_workers=4)`) est maintenue par compatibilité via des paramètres dépréciés le temps d'une version de transition.

---

## Alternatives rejetées

### A1 — Conserver les imports relatifs

Rejeté. Le projet cible une publication PyPI et doit respecter les conventions de l'écosystème. Les imports relatifs à 3+ niveaux (`from ...models import …`) sont déjà un signal de dette technique.

### A2 — Config via variables d'environnement uniquement

Rejeté. Les variables d'environnement sont appropriées pour le déploiement (12-factor), pas pour la configuration programmatique d'une bibliothèque. Les dataclasses `frozen=True` permettent l'injection de configuration dans les tests sans patching.

### A3 — Config via fichier YAML/TOML externe

Rejeté pour l'instant. Hors périmètre v0.4. Peut être ajouté ultérieurement comme couche optionnelle au-dessus des dataclasses.

---

## Conséquences

### Positives

- **Lisibilité** : chaque import révèle son origine exacte (`pyworkflow_engine.engine.context`).
- **Testabilité** : `WorkflowEngine(config=WorkflowConfig(engine=EngineConfig(max_retries=1)))` pour les tests.
- **Cohérence** : la configuration rejoint les autres modules structurels du package.
- **Outillage** : `ruff` peut valider et corriger automatiquement le style d'imports.

### Négatives / Risques

- **Volume de changements** : la migration des imports touche ~20 fichiers. À faire en un seul commit atomique pour éviter un état intermédiaire cassé.
- **Rupture de compatibilité mineure** : le setter `WorkflowEngine.persistence` accède directement à `self._suspension._persistence` — à encapsuler lors de la migration `config/`.

### Fichiers impactés (imports)

| Module | Fichiers à migrer |
|--------|------------------|
| `engine/` | `context.py`, `dag.py`, `runner.py`, `parallel_runner.py`, `retry.py`, `suspension.py` |
| `executors/` | `base.py`, `local.py`, `thread_pool.py`, `process_pool.py`, `async_exec.py`, `retryable.py` |
| `triggers/` | `base.py`, `manual.py`, `schedule.py` |
| `persistence/` | `base.py` et adapters |
| Racine | `facade.py`, `exceptions.py`, `__init__.py` |

---

## Plan d'implémentation

```
Sprint 1 (config/) :
  1. Créer src/pyworkflow_engine/config/ avec base.py, engine.py, executor.py, logging.py
  2. Adapter WorkflowEngine.__init__ pour accepter WorkflowConfig
  3. Maintenir la rétrocompatibilité des paramètres existants (deprecated warning)
  4. Tests unitaires de WorkflowConfig

Sprint 2 (imports absolus) :
  1. Configurer ruff TID252 dans pyproject.toml
  2. Exécuter : ruff check src/ --select TID252 --fix
  3. Vérifier manuellement les __init__.py (exception tolérée)
  4. Lancer la suite de tests complète
  5. Commit atomique : "refactor: migrate to absolute imports (ADR-004)"
```
