# État d'avancement — `pyworkflow-engine`

> **Dernière mise à jour :** 10 avril 2026  
> **Version actuelle :** 0.2.1  
> **Phase :** Alpha — développement actif  
> **Statut global :** 🟡 En cours

---

## Résumé exécutif

`pyworkflow-engine` est un moteur d'orchestration de workflows Python pur. Le cœur du projet est **fonctionnel et testé** à 88% de couverture. La migration de `ias_workflow_engine` vers `pyworkflow_engine` est terminée. Les travaux en cours portent sur la stabilisation des adapters, l'extension de la CLI, et la mise en place des triggers.

---

## 1. Tableau de bord global

| Domaine               | Statut        | Couverture | Priorité |
|-----------------------|:-------------:|:----------:|:--------:|
| Core Engine           | ✅ Stable      | ~90%       | —        |
| Modèles design-time   | ✅ Stable      | ~95%       | —        |
| Modèles runtime       | ✅ Stable      | ~90%       | —        |
| Enums & exceptions    | ✅ Stable      | ~95%       | —        |
| DAG Resolver          | ✅ Stable      | ~90%       | —        |
| WorkflowContext       | ✅ Stable      | ~85%       | —        |
| Executors avancés     | ✅ Stable      | ~85%       | —        |
| Logging               | ✅ Stable      | ~92%       | —        |
| Persistence (Memory)  | ✅ Stable      | ~90%       | —        |
| Persistence (JSON)    | ⚠️ À stabiliser | ~75%      | 🔴 Haute  |
| Persistence (SQLite)  | ⚠️ À stabiliser | ~75%      | 🔴 Haute  |
| Persistence (SQLAlchemy) | ⚠️ À stabiliser | ~70%   | 🔴 Haute  |
| Adapters (Django)     | 🔧 Squelette   | <10%       | 🟡 Moyenne |
| Adapters (FastAPI)    | 🔧 Squelette   | <10%       | 🟡 Moyenne |
| Adapters (Celery)     | 🔧 Squelette   | <10%       | 🟡 Moyenne |
| Adapters (Streamlit)  | 🔧 Squelette   | <10%       | 🟢 Basse  |
| Adapters (Structlog)  | 🔧 Squelette   | <10%       | 🟢 Basse  |
| Executors/            | ⏳ Prévu       | 0%         | 🟡 Moyenne |
| Triggers              | ⏳ Prévu       | 0%         | 🟡 Moyenne |
| CLI                   | ⏳ Prévu       | 0%         | 🟡 Moyenne |
| Serialization         | ⏳ Prévu       | 0%         | 🟢 Basse  |

---

## 2. Historique des versions

### v0.2.1 — 11 mars 2026 ✅
**Thème : Utilitaires de logging avancés**

- Ajout de `logged_operation` — context manager de traçage automatique (début, durée, succès/échec)
- Ajout de `StepLogBridge` — handler stdlib redirigé vers `StepRun.add_log()`
- Ajout de `LoggingConfigBuilder` — API fluente de construction de config
- Ajout de `SnowflakeLogHandler` — adapter Snowflake avec batching
- Support des couleurs ANSI dans `StructuredFormatter` (auto-détection TTY)
- Nouveaux exemples : `logging_basics.py`, `logging_advanced.py`
- **+32 tests** → **111 tests** passing sur le module logging
- 0 régression

### v0.2.0 — 10 mars 2026 ✅ *(breaking change)*
**Thème : Renommage et couche de persistance complète**

- **Breaking** : renommage `ias_workflow_engine` → `pyworkflow_engine`
- 4 backends de persistance : `InMemoryStorage`, `JSONFileStorage`, `SQLiteStorage`, `SQLAlchemyStorage`
- Timeout par step via thread daemon + `Queue`
- Executors avancés : `ThreadPool`, `ProcessPool`, `Async`, `RetryableExecutor`, `ExecutorRegistry`
- **185+ tests**, couverture 88%
- Guide de migration `MIGRATION.md`

### v0.1.0-alpha — 10 mars 2026 ✅
**Thème : Bootstrap initial**

- Core zero-dépendance (engine, DAG, modèles, context)
- Executors de base (local, thread, async)
- Persistance en mémoire
- Système de logging stdlib (zéro dépendance)
- Adapter structlog opt-in
- Outillage dev : ruff, mypy, pytest, pre-commit

---

## 3. Composants terminés en détail

### ✅ Core Engine (`core/engine.py`)
- Exécution séquentielle selon l'ordre topologique DAG
- Suspension/reprise de workflows (`WorkflowSuspended`)
- Annulation (`cancel`)
- Retry automatique par step avec délai configurable
- Timeout par step (thread daemon + Queue stdlib)
- Exécution conditionnelle (`step.condition`)
- Intégration du backend de persistance via property
- Plan d'exécution (`get_execution_plan`) et validation (`validate_job`)

### ✅ DAG Resolver (`core/dag.py`)
- Tri topologique (algorithme de Kahn)
- Détection de cycles (DFS tri coloré)
- Groupes de parallelisme (`get_parallel_groups`)
- Chemin critique (`get_critical_path`)
- Statistiques de graphe (`get_graph_stats`)

### ✅ Logging (`logging/`)
- Conforme PEP 282 (NullHandler par défaut)
- Namespace hiérarchique `pyworkflow_engine.*`
- Formatters : `StructuredFormatter` (console + couleurs ANSI) et `JSONFormatter` (NDJSON)
- Handlers : console, fichier rotatif, `QueueHandler` asynchrone non-bloquant
- `LoggingConfig` (dataclass `frozen`) avec `with_overrides()`
- Utilitaires : `logged_operation`, `StepLogBridge`, `LoggingConfigBuilder`

### ✅ Persistance — InMemoryStorage
- Thread-safe (verrous internes)
- Support transactionnel (context manager)
- Estimation de la mémoire consommée
- Filtres : par job, statut, plage de dates, pagination

---

## 4. Problèmes connus

### ⚠️ Incohérences d'API dans les backends de persistance (JSONFile, SQLite, SQLAlchemy)
- **Impact :** Les backends autres qu'`InMemoryStorage` peuvent présenter des comportements inattendus sur des cas limites.
- **Exemple :** `StepType.PYTHON_FUNCTION` au lieu de `StepType.FUNCTION` dans certains anciens exemples.
- **Fichier concerné :** `examples/storage_backends.py`
- **Workaround :** Utiliser `examples/storage_simple.py` comme référence.
- **Priorité :** 🔴 Haute

### ⚠️ Adapters vides
- Les dossiers `adapters/django`, `adapters/fastapi`, `adapters/celery`, etc. contiennent des squelettes vides.
- Aucune fonctionnalité d'intégration framework n'est encore disponible.
- **Priorité :** 🟡 Moyenne

### ⚠️ Tests d'intégration absents
- Le répertoire `tests/integration/` est vide.
- Seuls des tests unitaires et quelques scénarios de bout-en-bout via `tests/unit/` existent.
- **Priorité :** 🟡 Moyenne

### ⚠️ CLI non implémentée
- Le point d'entrée `workflow` est déclaré dans `pyproject.toml` mais le module cible (`pyworkflow_engine.cli.main:cli`) est absent.
- **Priorité :** 🟡 Moyenne

---

## 5. Roadmap

### 🔜 Court terme (prochaines itérations)

| Tâche | Priorité | Effort estimé |
|-------|:--------:|:-------------:|
| Corriger les incohérences API des backends JSON/SQLite/SQLAlchemy | 🔴 | Moyen |
| Implémenter `LocalExecutor` dans `executors/` | 🔴 | Faible |
| Écrire les tests d'intégration (`tests/integration/`) | 🟡 | Élevé |
| Implémenter les commandes CLI de base (`run`, `list`, `status`) | 🟡 | Moyen |
| Premier adapter fonctionnel : FastAPI | 🟡 | Élevé |

### ⏳ Moyen terme

| Tâche | Priorité | Effort estimé |
|-------|:--------:|:-------------:|
| Triggers : `SCHEDULE` (cron/intervalle) | 🟡 | Élevé |
| Triggers : `WEBHOOK` (HTTP endpoint) | 🟡 | Élevé |
| Adapter Django (ORM + DRF endpoints) | 🟡 | Élevé |
| Adapter Celery (distributiond des steps) | 🟡 | Élevé |
| Serialisation YAML/JSON des définitions de jobs | 🟢 | Moyen |
| Exécution parallèle native (`get_parallel_groups`) | 🟢 | Élevé |

### 🌱 Long terme / Vision

| Tâche | Priorité |
|-------|:--------:|
| Interface de monitoring Streamlit | 🟢 |
| Execution distribuée via Kubernetes executor | 🟢 |
| Publication sur PyPI | 🟡 |
| Documentation MkDocs complète (API reference) | 🟡 |
| Support Python 3.13 (tests dédiés) | 🟢 |

---

## 6. Métriques qualité

| Métrique                  | Valeur actuelle    | Cible        |
|---------------------------|--------------------|--------------|
| Lignes de code source     | ~7 069             | —            |
| Modules Python (src)      | 24                 | —            |
| Tests totaux              | 185+               | 250+         |
| Couverture globale        | **88%**            | **≥ 90%**    |
| Tests unitaires           | ✅ 8 fichiers       | + intégration |
| Tests d'intégration       | ❌ 0               | ≥ 10 scénarios |
| Exemples fonctionnels     | 6/7 (1 API issues) | 7/7           |
| Linting (ruff)            | ✅ Configuré        | 0 warning     |
| Typage (mypy strict)      | ✅ Configuré        | 0 error       |

---

## 7. Dépendances

### Core (zéro dépendance obligatoire)
```
dependencies = []
```
Le cœur fonctionne exclusivement avec la stdlib Python (≥ 3.11).

### Optionnelles (par groupe)

| Extra          | Package(s)                                    | Statut impl. |
|----------------|-----------------------------------------------|:------------:|
| `django`       | `django>=4.2`, `djangorestframework>=3.14`    | ⏳ Prévu     |
| `fastapi`      | `fastapi>=0.100`, `uvicorn>=0.20`             | ⏳ Prévu     |
| `celery`       | `celery>=5.3`                                 | ⏳ Prévu     |
| `streamlit`    | `streamlit>=1.30`                             | ⏳ Prévu     |
| `structlog`    | `structlog>=24.0`                             | 🔧 Squelette |
| `sqlalchemy`   | `sqlalchemy>=2.0`                             | ⚠️ Partiel   |
| `postgresql`   | `sqlalchemy>=2.0`, `psycopg2-binary>=2.9`    | ⚠️ Partiel   |
| `mysql`        | `sqlalchemy>=2.0`, `PyMySQL>=1.0`            | ⚠️ Partiel   |
| `cli`          | `click>=8.0`, `rich>=13.0`                   | ⏳ Prévu     |

---

## 8. Environnement de développement

```bash
# Installation de l'environnement complet
uv sync --all-extras

# Lancer les tests
pytest

# Vérifier le type-checking
mypy src/

# Linter
ruff check src/ tests/

# Formater
ruff format src/ tests/

# Pré-commit (hooks git)
pre-commit install
```

---

## Légende

| Icône | Signification             |
|-------|---------------------------|
| ✅    | Terminé et stable         |
| ⚠️    | Partiel – à stabiliser    |
| 🔧    | Squelette – non fonctionnel |
| ⏳    | Planifié – non démarré    |
| 🔴    | Priorité haute            |
| 🟡    | Priorité moyenne          |
| 🟢    | Priorité basse / future   |
