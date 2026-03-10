# Plan d'Implémentation : Package Python Pur `ias-workflow-engine`

**Date**: 10 mars 2026  
**Status**: Plan d'exécution (Logging Module: ✅ **COMPLETED**)  
**Durée estimée**: 8-10 semaines  
**Équipe**: 2-3 développeurs  

---

## ✅ Modules Implémentés

### Logging Module (Completed - March 2026)

**Status**: Production-ready ✅  
**Coverage**: 94% test coverage, 52 tests passed  
**Dependencies**: Zero core dependencies (stdlib only)  

**Architecture**:
- **Layer 1 (Core)**: `stdlib.logging` - `get_logger()`, JSON formatter, structured formatter
- **Layer 2 (Advanced)**: `stdlib` handlers - SQLiteLogHandler, QueueHandler for async  
- **Layer 3 (Adapters)**: Optional structlog via `pip install ias-workflow-engine[structlog]`

**Files Created**:
- `src/ias_workflow_engine/logging/` - Complete logging module
- `src/ias_workflow_engine/adapters/structlog/` - Optional structlog integration
- `tests/unit/test_logging.py` - Comprehensive test suite (52 tests)
- `docs/guides/logging.md` - Full documentation

**Features Delivered**:
- ✅ Zero-dependency core logging
- ✅ Structured and JSON formatters  
- ✅ SQLite persistence with query API
- ✅ Async queue-based logging
- ✅ File logging with rotation support
- ✅ Thread-safe operations
- ✅ Optional structlog integration
- ✅ Comprehensive documentation

---

## 🎯 Vue d'Ensemble

Ce document détaille le plan d'implémentation pour migrer l'application Django `django-workflows` vers un package Python pur `ias-workflow-engine` suivant la stratégie "Library-first, Framework-second".

### Objectifs SMART

- **S**pécifique : Créer un package Python pur zero-dependency avec adapters pluggables
- **M**esurable : 100% de couverture fonctionnelle par rapport à l'existant Django
- **A**tteignable : Réutiliser l'architecture conceptuelle existante
- **R**éaliste : Migration progressive avec coexistence temporaire
- **T**emporel : Livraison en 4 phases sur 8-10 semaines

---

## 🏗️ Architecture de Développement

### Stratégie de Repository

```
📂 Développement Parallèle
├── django-workflows/          # App existante (maintenance uniquement)
└── ias-workflow-engine/       # Nouveau package (développement actif)
    ├── src/ias_workflow_engine/
    ├── tests/
    ├── examples/
    └── docs/
```

### Environnements

| Environnement | Usage | Configuration |
|---|---|---|
| **dev** | Développement local | `uv sync --group dev` |
| **test** | Tests automatisés | CI/CD avec matrix Python 3.11-3.13 |
| **staging** | Tests d'intégration | Déploiement des adapters en environnement similaire à prod |
| **production** | Migration progressive | Feature flags pour basculement graduel |

### Setup Instructions

Pour commencer le développement :

```bash
# Clone et setup
git clone <repository-url> ias-workflow-engine
cd ias-workflow-engine

# Install dependencies avec uv
uv sync --group dev

# Activate virtual environment
source .venv/bin/activate

# Run tests
python -m pytest
```

---

## 📅 Planning Détaillé

### Phase 1 : Core Framework-Free (Semaines 1-2)

**Livrable** : Core fonctionnel sans aucune dépendance externe

#### Semaine 1 : Structure & Modèles

**Jour 1-2 : Setup Projet**
- [ ] Initialiser le repository `ias-workflow-engine`
- [ ] Configurer `pyproject.toml` avec dependencies = []
- [ ] Setup CI/CD (GitHub Actions)
- [ ] Configuration développement (ruff, mypy, pre-commit)

**Jour 3-5 : Modèles Core**
- [ ] `core/models/enums.py` : TriggerType, StepType, ExecutorType, RunStatus
- [ ] `core/models/design_time.py` : Job, Step, SubJob (dataclasses)
- [ ] `core/models/runtime.py` : JobRun, StepRun, StepLog (dataclasses)
- [ ] `core/models/__init__.py` : API publique
- [ ] Tests unitaires pour tous les modèles

#### Semaine 2 : Moteur d'Exécution

**Jour 1-3 : WorkflowEngine**
- [ ] `core/engine.py` : WorkflowEngine principal
- [ ] `core/dag.py` : DAGResolver (résolution graphe de dépendances)
- [ ] `core/context.py` : WorkflowContext (passage I/O)
- [ ] `core/exceptions.py` : WorkflowSuspended, WorkflowFailed, etc.

**Jour 4-5 : Sérialisation & Validation**
- [ ] `serialization/serializer.py` : to_dict/from_dict pour tous les modèles
- [ ] `serialization/snapshot.py` : Snapshots immuables pour JobRun
- [ ] `contrib/validators.py` : Validation DAG (cycles, orphelins)
- [ ] Tests d'intégration pour workflows simples

**Critères d'Acceptance Phase 1** :
```python
# Ce code doit fonctionner sans aucune dépendance externe
from ias_workflow_engine.core import Job, Step, WorkflowEngine

def hello_world():
    return {"message": "Hello World!"}

job = Job(name="Test", steps=[
    Step(name="Say Hello", callable=hello_world)
])

engine = WorkflowEngine()
result = engine.run(job)
assert result.status == "success"
assert result.result["step_0"]["message"] == "Hello World!"
```

### Phase 2 : Executors & Persistence (Semaines 3-4)

**Livrable** : Système d'exécution pluggable et persistence modulaire

#### Semaine 3 : Executors

**Jour 1-2 : Interfaces & Registry**
- [ ] `executors/base.py` : BaseExecutor (ABC)
- [ ] `executors/registry.py` : ExecutorRegistry avec découverte automatique
- [ ] Tests pour le système de registry

**Jour 3-5 : Executors Built-in**
- [ ] `executors/local.py` : LocalExecutor (sync, même process)
- [ ] `executors/thread.py` : ThreadExecutor (ThreadPoolExecutor)
- [ ] `executors/async_executor.py` : AsyncExecutor (asyncio natif)
- [ ] `executors/process.py` : ProcessExecutor (multiprocessing)
- [ ] `executors/human.py` : HumanExecutor (suspension WAITING_HUMAN)
- [ ] `executors/external.py` : ExternalExecutor (suspension WAITING_EXTERNAL)
- [ ] Tests pour chaque executor

#### Semaine 4 : Persistence & Triggers

**Jour 1-3 : Persistence**
- [ ] `persistence/base.py` : BasePersistence (ABC)
- [ ] `persistence/memory.py` : InMemoryPersistence
- [ ] `persistence/json_file.py` : JSONFilePersistence
- [ ] `persistence/sqlite.py` : SQLitePersistence (sqlite3 stdlib)
- [ ] Tests pour chaque backend de persistence

**Jour 4-5 : Triggers**
- [ ] `triggers/base.py` : BaseTrigger (ABC)
- [ ] `triggers/registry.py` : TriggerRegistry
- [ ] `triggers/manual.py` : ManualTrigger
- [ ] `triggers/schedule.py` : ScheduleTrigger (cron sans Celery)
- [ ] `triggers/signal.py` : SignalTrigger (pub/sub interne)
- [ ] Tests pour tous les triggers

**Critères d'Acceptance Phase 2** :
```python
# Persistence pluggable
from ias_workflow_engine import Job, WorkflowEngine
from ias_workflow_engine.persistence import SQLitePersistence

persistence = SQLitePersistence("workflows.db")
engine = WorkflowEngine(persistence=persistence)

# Executors pluggables
from ias_workflow_engine.executors import ThreadExecutor
job = Job(name="Parallel Job", steps=[...])
result = engine.run(job, executor_type="thread")

# Suspension/reprise
result = engine.run(human_workflow)
assert result.status == "waiting_human"
resumed = engine.resume(result, step_outputs={"approved": True})
assert resumed.status == "success"
```

### Phase 3 : Adapters & Intégrations (Semaines 5-6)

**Livrable** : Adapters pour Django, FastAPI, Celery prêts pour production

#### Semaine 5 : Adapter Django

**Jour 1-2 : Persistence Django**
- [ ] `adapters/django/models.py` : Modèles Django wrapper des dataclasses
- [ ] `adapters/django/persistence.py` : DjangoORMPersistence
- [ ] `adapters/django/signals.py` : DjangoSignalTrigger
- [ ] Migration Django pour les nouvelles tables

**Jour 3-5 : Interface Django**
- [ ] `adapters/django/admin.py` : Interface admin Django
- [ ] `adapters/django/views.py` : API DRF
- [ ] `adapters/django/urls.py` : Routes
- [ ] `adapters/django/apps.py` : AppConfig
- [ ] Tests d'intégration Django

#### Semaine 6 : Autres Adapters

**Jour 1-2 : Adapter Celery**
- [ ] `adapters/celery/executor.py` : CeleryExecutor
- [ ] `adapters/celery/tasks.py` : Tâches Celery génériques
- [ ] `adapters/celery/schedule.py` : Celery Beat bridge
- [ ] Tests avec Celery

**Jour 3-4 : Adapter FastAPI**
- [ ] `adapters/fastapi/routes.py` : APIRouter FastAPI
- [ ] `adapters/fastapi/dependencies.py` : Injection de dépendances
- [ ] `adapters/fastapi/websocket.py` : WebSocket temps réel
- [ ] Tests FastAPI

**Jour 5 : Adapter SQLAlchemy**
- [ ] `adapters/sqlalchemy/models.py` : Tables SQLAlchemy
- [ ] `adapters/sqlalchemy/persistence.py` : SQLAlchemyPersistence
- [ ] Tests SQLAlchemy

**Critères d'Acceptance Phase 3** :
```python
# Adapter Django fonctionne
pip install ias-workflow-engine[django]
# Les modèles Django wrappent les dataclasses core
# L'admin Django affiche les workflows
# L'API DRF expose les endpoints

# Adapter Celery fonctionne
pip install ias-workflow-engine[celery]
# Les tâches sont dispatchées à Celery
# Celery Beat déclenche les workflows schedulés

# Adapter FastAPI fonctionne
pip install ias-workflow-engine[fastapi]
# Routes FastAPI exposent l'API
# WebSocket diffuse les changements d'état
```

### Phase 4 : Migration & Production (Semaines 7-8)

**Livrable** : Migration complète avec coexistence et bascule progressive

#### Semaine 7 : Migration Bridge

**Jour 1-3 : Bridge Django → Core**
- [ ] Adapter bidirectionnel : Django models ↔ Core dataclasses
- [ ] Script de migration des données existantes
- [ ] Validation : les deux systèmes produisent les mêmes résultats
- [ ] Feature flags pour bascule progressive

**Jour 4-5 : Tests de Régression**
- [ ] Suite de tests comparant Django vs Core sur workflows existants
- [ ] Tests de performance (latence, throughput)
- [ ] Tests de charge (stress testing)
- [ ] Documentation migration

#### Semaine 8 : Déploiement Production

**Jour 1-2 : Déploiement Staging**
- [ ] Déploiement environnement staging avec les deux systèmes
- [ ] Tests d'acceptance utilisateur
- [ ] Validation des adaptors en condition réelle

**Jour 3-5 : Bascule Production**
- [ ] Déploiement production avec feature flag OFF
- [ ] Bascule progressive par pourcentage de workflows
- [ ] Monitoring et rollback si nécessaire
- [ ] Décommissioning de l'ancien système (optionnel)

**Critères d'Acceptance Phase 4** :
```python
# Migration sans interruption de service
# Performance égale ou supérieure à l'existant
# 100% des workflows existants fonctionnent avec le nouveau système
# Adapters Django maintiennent l'interface utilisateur existante
# Possibilité de rollback instantané
```

---

## 🧪 Stratégie de Tests

### Pyramide de Tests

```
       /\
      /  \     E2E Tests (10%)
     /____\    - Tests d'intégration complets
    /      \   - Workflows Django vs Core
   /________\  Integration Tests (20%)
  /          \ - Adapters avec frameworks réels
 /____________\ Unit Tests (70%)
                - Core models, engine, executors
                - Zero dépendance externe
```

### Couverture par Composant

| Composant | Target Coverage | Stratégie |
|---|---|---|
| **core/** | 95% | Tests unitaires purs, mocking minimal |
| **executors/** | 90% | Tests avec ThreadPoolExecutor, multiprocessing |
| **persistence/** | 85% | Tests avec SQLite temporaire, mocks |
| **adapters/** | 70% | Tests d'intégration avec frameworks réels |
| **CLI** | 60% | Tests fonctionnels avec subprocess |

### Environnements de Test

```yaml
# .github/workflows/ci.yml
matrix:
  python-version: ['3.11', '3.12', '3.13']
  os: [ubuntu-latest, macos-latest, windows-latest]
  extras: 
    - '' # Core seulement
    - 'django'
    - 'fastapi'
    - 'celery'
    - 'all'
```

---

## 📦 Stratégie de Packaging & Distribution

### Versions & Release

| Version | Contenu | Timeline |
|---|---|---|
| **0.1.0-alpha** | Core + LocalExecutor | Fin semaine 2 |
| **0.2.0-alpha** | + Executors + Persistence | Fin semaine 4 |
| **0.3.0-beta** | + Adapters Django/FastAPI | Fin semaine 6 |
| **1.0.0-rc1** | + Migration tools | Fin semaine 7 |
| **1.0.0** | Production ready | Fin semaine 8 |

### Distribution

```toml
# Packages séparés pour éviter la confusion
[project]
name = "ias-workflow-engine"        # Package principal
# vs
name = "django-workflows"           # App Django existante (deprecated)

[project.optional-dependencies]
# Installation granulaire
minimal = []                        # Core seulement
django = ["django>=4.2", "djangorestframework>=3.14"]
web = ["ias-workflow-engine[django,fastapi]"]
async = ["ias-workflow-engine[celery,fastapi]"] 
full = ["ias-workflow-engine[django,fastapi,celery,sqlalchemy,streamlit,cli]"]
```

### Rétrocompatibilité

```python
# Migration bridge temporaire
# django_workflows/core.py (deprecated)
import warnings
from ias_workflow_engine import Job, WorkflowEngine

warnings.warn(
    "django_workflows is deprecated. Use 'ias-workflow-engine[django]' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Proxy classes pour rétrocompatibilité
class LegacyJob(Job):
    """Deprecated: Use ias_workflow_engine.Job directly"""
    pass
```

---

## 🚀 Stratégie de Déploiement

### Migration Progressive

#### Option A : Feature Flag (Recommandée)

```python
# settings.py
USE_NEW_WORKFLOW_ENGINE = os.getenv('USE_NEW_WORKFLOW_ENGINE', 'false').lower() == 'true'

# views.py
if settings.USE_NEW_WORKFLOW_ENGINE:
    from ias_workflow_engine.adapters.django import DjangoWorkflowEngine
    engine = DjangoWorkflowEngine()
else:
    from django_workflows.engine import WorkflowEngine
    engine = WorkflowEngine()
```

#### Option B : Migration par Tenant

```python
# Pour les apps multi-tenant
WORKFLOW_ENGINE_BY_TENANT = {
    'tenant_beta': 'new',     # Tenant beta sur nouveau système
    'tenant_prod': 'old',     # Tenant prod sur ancien système
}
```

#### Option C : Migration par Type de Workflow

```python
# Migration par type de job
NEW_ENGINE_JOB_TYPES = ['etl', 'ai_processing']  # Types migrés
OLD_ENGINE_JOB_TYPES = ['reporting', 'alerts']   # Types en ancien système
```

### Monitoring & Observabilité

#### Métriques Clés

```python
# Métriques à surveiller pendant migration
METRICS = {
    'workflow_latency': 'Latence execution workflow',
    'workflow_success_rate': 'Taux de succès',
    'engine_errors': 'Erreurs par moteur (old vs new)',
    'migration_coverage': 'Pourcentage workflows migrés',
    'rollback_triggers': 'Déclencheurs de rollback'
}
```

#### Alertes

| Métrique | Seuil | Action |
|---|---|---|
| **Latence** | +20% vs baseline | Investigation |
| **Erreur Rate** | >1% pour nouveau moteur | Rollback automatique |
| **Différence Résultats** | >0% (old vs new) | Stop migration |

### Rollback Plan

```python
# Plan de rollback en cas de problème
class RollbackPlan:
    """
    1. Feature flag OFF → 100% ancien système
    2. Vider queues nouveau système
    3. Reprendre workflows suspendus sur ancien système
    4. Alerter équipe + post-mortem
    """
    
    def execute_rollback(self):
        settings.USE_NEW_WORKFLOW_ENGINE = False
        # Transfert des workflows en cours...
```

---

## 👥 Organisation Équipe

### Rôles & Responsabilités

| Rôle | Responsable | Responsabilités |
|---|---|---|
| **Lead Dev** | Senior Dev A | Architecture, reviews, décisions techniques |
| **Core Dev** | Dev B | Core models, engine, executors |
| **Adapters Dev** | Dev C | Django, FastAPI, Celery adapters |
| **QA** | QA Lead | Tests, validation, performance |
| **DevOps** | Platform Team | CI/CD, déploiement, monitoring |

### Workflow de Développement

```
📋 Kanban Board
├── 📝 Backlog          # User stories prioritisées
├── 🏗️ In Progress      # Développement actif (max 3 items)
├── 👀 Code Review      # Pull requests en review
├── 🧪 Testing          # Tests manuels + automatisés
└── ✅ Done             # Delivered to staging/prod
```

### Definition of Done

- [ ] Code écrit et testé (coverage > seuil)
- [ ] Code review approuvé par Lead Dev
- [ ] Tests CI/CD passent sur tous les environnements
- [ ] Documentation mise à jour
- [ ] Pas de régression sur performance
- [ ] Migration path documenté (si applicable)

---

## 📊 Métriques de Succès

### KPIs Techniques

| KPI | Baseline (Django) | Target (Core) | Mesure |
|---|---|---|---|
| **Temps de test** | ~30s (avec DB) | <2s (core seulement) | CI/CD |
| **Latence workflow** | 100ms | ≤100ms | APM |
| **Memory usage** | ~50MB (Django stack) | <10MB (core) | Profiling |
| **Lines of code** | ~2000 LOC | <1500 LOC (core) | SonarQube |
| **Dependencies** | ~50 packages | 0 (core) | `pip list` |

### KPIs Business

| KPI | Baseline | Target | Mesure |
|---|---|---|---|
| **Developer velocity** | 1 workflow/jour | 3 workflows/jour | Jira |
| **Time to market** | 2 semaines | 1 semaine | Business metrics |
| **Bug rate** | 5% workflows | <1% workflows | Sentry |
| **Maintenance cost** | 20h/mois | 5h/mois | Time tracking |

### Critères de Réussite

#### Must Have ✅
- [ ] 100% feature parity avec Django app
- [ ] Performance égale ou supérieure
- [ ] Zero dépendance pour le core
- [ ] Migration sans interruption de service
- [ ] Tests core < 2s

#### Should Have 📈  
- [ ] Amélioration 3x de la vitesse de développement
- [ ] Réduction 75% des dépendances
- [ ] Documentation complète + exemples
- [ ] Package publié sur PyPI

#### Could Have 🎯
- [ ] CLI fonctionnel
- [ ] Adapter Streamlit
- [ ] Notebook examples
- [ ] Performance monitoring dashboard

---

## 🎯 Risques & Mitigation

### Risques Techniques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| **Incompatibilité sérialization** | Moyenne | Élevé | Tests croisés Django ↔ Core dès semaine 3 |
| **Performance dégradée** | Faible | Élevé | Benchmarks continus, profiling |
| **Bugs dans DAG resolver** | Moyenne | Moyen | Tests exhaustifs, edge cases |
| **Migration data complexe** | Élevée | Moyen | Scripts testés, rollback plan |

### Risques Projet

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| **Retard planning** | Moyenne | Moyen | Buffer 20% dans planning |
| **Scope creep** | Élevée | Élevé | Définition strict MVP, phase approach |
| **Résistance équipe** | Faible | Moyen | Démos régulières, formation |
| **Prod incident** | Faible | Élevé | Feature flags, rollback automatique |

### Plan de Contingence

```python
# Critères de stop/rollback
STOP_CRITERIA = {
    'performance_degradation': '>20%',
    'error_rate_increase': '>1%', 
    'test_coverage_drop': '<80%',
    'timeline_delay': '>2 weeks'
}

# Actions correctives
CORRECTIVE_ACTIONS = {
    'performance': 'Profiling + optimisation',
    'errors': 'Bug fixes + tests supplémentaires',  
    'coverage': 'Tests complémentaires',
    'timeline': 'Réduction scope ou équipe renforcée'
}
```

---

## 📚 Documentation & Formation

### Documentation Technique

- [ ] **Architecture Decision Records (ADRs)** : Décisions architecturales
- [ ] **API Reference** : Auto-générée via mkdocstrings
- [ ] **Migration Guide** : Django → Core step-by-step
- [ ] **Troubleshooting** : Common issues + solutions
- [ ] **Performance Tuning** : Optimisation guidelines

### Documentation Utilisateur

- [ ] **Quick Start** : Workflow en 5 minutes
- [ ] **Tutorial** : Human-in-the-loop, AI agents, subworkflows
- [ ] **How-To Guides** : Cas d'usage spécifiques
- [ ] **Integration Examples** : FastAPI, Django, Streamlit, notebook

### Formation Équipe

| Session | Durée | Audience | Contenu |
|---|---|---|---|
| **Architecture Overview** | 2h | Tous devs | Vision, principes, demo |
| **Core Development** | 4h | Core devs | Models, engine, patterns |
| **Adapter Development** | 3h | Adapter devs | Interfaces, Django/FastAPI |
| **Migration Workshop** | 2h | Ops + devs | Feature flags, monitoring |

---

## 🎉 Critères de Livraison

### Phase Gates

Chaque phase a des critères de passage stricts :

#### ✅ Phase 1 Complete
```bash
# Core fonctionne sans dépendances
pip install ./ias-workflow-engine  # 0 dependencies
python -c "from ias_workflow_engine import Job, WorkflowEngine; print('✅ Core OK')"
pytest tests/unit/ --cov=ias_workflow_engine.core --cov-report=term --cov-fail-under=90
```

#### ✅ Phase 2 Complete  
```bash
# Executors & Persistence pluggables
pytest tests/executors/ tests/persistence/ --cov-fail-under=85
python examples/async_workflow.py  # Async executor fonctionne
python examples/sqlite_persistence.py  # Persistence fonctionne
```

#### ✅ Phase 3 Complete
```bash
# Adapters fonctionnels
pip install ./ias-workflow-engine[django,fastapi,celery]
python examples/django_integration.py
python examples/fastapi_integration.py
python examples/celery_integration.py
```

#### ✅ Phase 4 Complete
```bash
# Production ready
# Migration scripts executés
# Performance >= baseline
# Feature flags opérationnels
# Monitoring actif
```

### Checklist de Release

- [ ] **Code Quality** : Tous les tests passent, coverage >85%
- [ ] **Performance** : Benchmarks ≥ baseline
- [ ] **Security** : Scan dependencies, SAST passed
- [ ] **Documentation** : Complète et à jour
- [ ] **Migration** : Scripts testés, rollback validé
- [ ] **Monitoring** : Dashboards configurés
- [ ] **Formation** : Équipe formée

---

**Status** : 📋 **Plan d'Implémentation Approuvé**  
**Next Action** : Kick-off Phase 1 - Setup projet + Modèles Core  
**Owner** : Lead Dev + Core Team  
**Review Date** : Fin de chaque semaine (points d'étape)
