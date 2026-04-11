# ADR-006 — Architecture hexagonale : introduction d'une couche `ports/` et réorganisation `adapters/`

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-006                             |
| **Date**    | 11 avril 2026                       |
| **Statut**  | 🔵 Proposition                      |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-002 (refactoring modulaire), ADR-004 (imports absolus + config), ADR-005 (API déclarative) |
| **Version cible** | v0.6.0                         |

---

## Contexte

### Retour d'expérience d'un projet précédent

Un projet antérieur (`flowledger`) avait adopté une **architecture hexagonale** (Ports & Adapters) avec la structure suivante :

```
├── ports/             ← INTERFACES (Protocol Python — sans implémentation)
│   ├── repository.py  ←   JournalRepository, BalanceRepository
│   ├── export.py      ←   ExportPort
│   └── notification.py←   NotificationPort
│
├── adapters/          ← IMPLÉMENTATIONS CONCRÈTES
│   ├── cli/           ←   Adapter CLI Typer
│   ├── api/           ←   Adapter HTTP FastAPI
│   ├── mcp/           ←   Adapter MCP agents IA
│   ├── persistence/   ←   JSON / SQLite / PostgreSQL
│   └── tui/           ←   Terminal UI Textual
│
├── data/              ← Jeux de données compatibles CLI
```

Cette architecture séparait clairement les **contrats** (ports) des **implémentations** (adapters), avec une règle fondamentale : _"le package est un package de domaine ; tout ce qui l'utilise de l'extérieur n'en fait pas partie"_.

### État actuel de `pyworkflow_engine` (v0.5.0)

Notre structure actuelle est **partiellement modulaire**, issue du refactoring ADR-002 :

```
src/pyworkflow_engine/
├── facade.py              # WorkflowEngine — point d'entrée
├── exceptions.py
├── engine/                # runner, retry, dag, suspension, context
├── models/                # step, job, run
├── decorators/            # @step, @job (ADR-005)
├── config/                # configuration (ADR-004)
├── executors/             # base.py + local, thread_pool, process_pool, async
│   └── base.py            # ← ABC BaseExecutor + ExecutorRegistry
├── persistence/           # base.py + memory, json_file, sqlite, sqlalchemy
│   └── base.py            # ← ABC BasePersistence + exceptions
├── triggers/              # base.py + manual, schedule
│   └── base.py            # ← ABC BaseTrigger + TriggerState
├── adapters/              # celery/, snowflake/, sqlalchemy/, structlog/
└── logging/               # structured logging
```

### Problèmes identifiés

1. **Interfaces et implémentations colocalisées** — `BasePersistence` (interface) vit dans `persistence/base.py` aux côtés de `memory.py`, `sqlite.py`, etc. (implémentations). Il n'y a pas de séparation architecturale visible entre le _contrat_ et les _implémentations concrètes_.

2. **Frontière `adapters/` incohérente** — Le dossier `adapters/` ne contient que les intégrations tierces (Celery, Snowflake, structlog), tandis que `persistence/`, `executors/` et `triggers/` (qui sont aussi des _adapters_ au sens hexagonal) vivent à la racine du package, au même niveau que le domaine (`engine/`, `models/`).

3. **Règle de dépendance implicite** — Le flux `adapters → ports ← engine` n'est pas matérialisé dans l'arborescence. Un contributeur ne peut pas savoir, en regardant la structure, quelles sont les abstractions stables et quelles sont les implémentations interchangeables.

4. **Question `clients/` vs `adapters/`** — L'expérience `flowledger` montre qu'il faut distinguer ce qui est _livré avec le package_ (adapters) de ce qui _consomme le package depuis l'extérieur_ (clients). Cette distinction n'est pas documentée pour `pyworkflow_engine`.

---

## Analyse : pertinence pour `pyworkflow_engine`

### Ce qui est pertinent

| Concept hexagonal | Pertinence | Justification |
|---|---|---|
| **Ports explicites** (interfaces Protocol/ABC) | ✅ Haute | Les ABC existent déjà (`BasePersistence`, `BaseExecutor`, `BaseTrigger`) — les regrouper dans `ports/` clarifie le contrat public |
| **Adapters regroupés** | ✅ Haute | `persistence/`, `executors/`, `triggers/` sont des adapters au sens hexagonal — les regrouper matérialise la frontière |
| **Séparation clients externes** | ✅ Très haute | Le package est une **bibliothèque de domaine** (workflow engine). Les consommateurs font `pip install pyworkflow-engine` |
| **Dossier `data/`** | ❌ Non pertinent | `pyworkflow_engine` est un **moteur**, pas une application avec des jeux de données. Les exemples dans `examples/` suffisent |

### Ce qui diffère du projet précédent

| Aspect | `flowledger` (précédent) | `pyworkflow_engine` (actuel) |
|---|---|---|
| **Nature** | Application de domaine métier (journalisation comptable) | Bibliothèque/framework technique (orchestration de workflows) |
| **CLI intégrée** | Oui — entrypoint livré avec le package | Non — c'est une lib, pas un outil CLI |
| **Données** | Jeux de données métier (`data/`) | Aucun — l'utilisateur fournit ses propres jobs/steps |
| **Clients externes** | React, Streamlit = séparés | Celery, Snowflake = **adapters intégrés** (optionnels via extras) |
| **Nature des ports** | Abstractions métier (Repository, Export, Notification) | Abstractions techniques (Persistence, Executor, Trigger) |

### Conclusion de l'analyse

L'architecture hexagonale est **pertinente** pour `pyworkflow_engine`, mais la frontière ports/adapters doit refléter la nature **technique** du package (pas métier). Les adaptations nécessaires sont :

- **Pas de `data/`** — pas de jeux de données à livrer
- **Pas de `clients/`** — pas de frontends, les consommateurs font `pip install`
- **Pas de `adapters/cli/`** — pas de CLI ; si un jour ajoutée, elle irait dans `adapters/cli/`
- **Les ports sont techniques** — persistence, execution, triggers, logging

---

## Décision proposée

### 1. Créer un package `ports/` regroupant les interfaces pures

Extraire les ABC/Protocol existants dans un package dédié, sans implémentation :

```
ports/
├── __init__.py          # re-exports publics
├── persistence.py       # BasePersistence, PersistenceError, JobNotFoundError, TransactionError
├── executor.py          # BaseExecutor, ExecutorRegistry (protocol)
├── trigger.py           # BaseTrigger, TriggerState
└── logger.py            # LogHandler protocol (si pertinent à terme)
```

**Règle** : `ports/` ne contient **aucune implémentation**, uniquement des ABC, Protocol, Enum de contrat et exceptions de contrat.

### 2. Réorganiser les implémentations concrètes sous `adapters/`

Déplacer les implémentations vers `adapters/` pour matérialiser la frontière hexagonale :

```
adapters/
├── persistence/         # InMemory, JSON, SQLite, SQLAlchemy
│   ├── __init__.py
│   ├── memory.py
│   ├── json_file.py
│   ├── sqlite.py
│   └── sqlalchemy.py
├── executors/           # Local, ThreadPool, ProcessPool, Async, Retryable
│   ├── __init__.py
│   ├── local.py
│   ├── thread_pool.py
│   ├── process_pool.py
│   ├── async_exec.py
│   └── retryable.py
├── triggers/            # Manual, Schedule/Cron
│   ├── __init__.py
│   ├── manual.py
│   └── schedule.py
├── logging/             # Handlers spécialisés (SQLite, Snowflake)
├── celery/              # Intégration Celery (extra)
├── snowflake/           # Intégration Snowflake (extra)
├── sqlalchemy/          # Intégration SQLAlchemy (extra)
└── structlog/           # Intégration structlog (extra)
```

### 3. Structure cible complète

```
src/pyworkflow_engine/
├── __init__.py            # Exports publics du package
├── facade.py              # WorkflowEngine — point d'entrée orchestrateur
├── exceptions.py          # Exceptions de base du package
├── py.typed
│
├── ports/                 # ← NOUVEAU : interfaces pures (Protocol/ABC)
│   ├── __init__.py        #   re-exports : BasePersistence, BaseExecutor, BaseTrigger
│   ├── persistence.py     #   BasePersistence + exceptions de contrat
│   ├── executor.py        #   BaseExecutor, ExecutorRegistry protocol
│   ├── trigger.py         #   BaseTrigger, TriggerState
│   └── logger.py          #   LogHandler protocol (optionnel, phase ultérieure)
│
├── engine/                # ← DOMAINE : logique cœur (dépend uniquement de ports/)
│   ├── runner.py
│   ├── parallel_runner.py
│   ├── retry.py
│   ├── suspension.py
│   ├── dag.py
│   └── context.py
│
├── models/                # ← DOMAINE : structures de données immuables
│   ├── step.py / design_time.py
│   ├── job.py
│   └── run.py / runtime.py
│
├── decorators/            # ← DOMAINE : API déclarative @step/@job (ADR-005)
│   ├── step_decorator.py
│   └── job_decorator.py
│
├── config/                # ← DOMAINE : configuration centralisée (ADR-004)
│
├── adapters/              # ← IMPLÉMENTATIONS concrètes des ports
│   ├── persistence/       #   InMemory, JSON, SQLite, SQLAlchemy
│   ├── executors/         #   Local, ThreadPool, ProcessPool, Async, Retryable
│   ├── triggers/          #   Manual, Schedule/Cron
│   ├── logging/           #   Handlers spécialisés
│   ├── celery/            #   Intégration Celery (extra)
│   ├── snowflake/         #   Intégration Snowflake (extra)
│   ├── sqlalchemy/        #   Intégration SQLAlchemy (extra)
│   └── structlog/         #   Intégration structlog (extra)
│
├── logging/               # ← TRANSVERSAL : config logging, formatters, get_logger()
│
└── examples/              # Démonstrations (externes au package)
```

### 4. Règle de dépendance (flux hexagonal)

```
┌─────────────────────────────────────────────────────┐
│                    facade.py                         │
│         (assemble engine + ports + adapters)         │
└────────────┬──────────────┬─────────────────────────┘
             │              │
             ▼              ▼
      ┌─────────────┐  ┌──────────────┐
      │   engine/    │  │  adapters/   │
      │   models/    │  │  (implémente │
      │   decorators/│  │   les ports) │
      │   (domaine)  │  │              │
      └──────┬───────┘  └──────┬───────┘
             │                 │
             ▼                 ▼
         ┌─────────────────────────┐
         │        ports/           │
         │  (interfaces pures —    │
         │   ABC / Protocol)       │
         └─────────────────────────┘
```

**Règle fondamentale** :
- `engine/` → importe → `ports/` (dépend des abstractions, **jamais** des adapters)
- `adapters/` → importe → `ports/` (implémente les interfaces)
- `facade.py` → importe → `engine/` + `ports/` + `adapters/` (assemble le tout)

---

## Ce qu'il ne faut PAS faire

| Anti-pattern | Pourquoi |
|---|---|
| Dossier `data/` | Nous ne sommes pas une application CLI — pas de jeux de données à livrer |
| Dossier `clients/` | Personne ne fait un "client React" pour un workflow engine Python — les consommateurs font `pip install pyworkflow-engine` |
| Séparer Celery/Snowflake hors du package | Ce sont des **adapters optionnels** livrés via extras (`pip install pyworkflow-engine[celery]`), ils appartiennent au package |
| Forcer `adapters/cli/` maintenant | Nous n'avons pas de CLI — si un jour ajoutée, elle y trouvera sa place |
| `ports/` avec de la logique | Les ports ne doivent contenir que des ABC, Protocol, Enum de contrat et exceptions de contrat — zéro implémentation |

---

## Plan de migration

La migration doit être **incrémentale et non-breaking** pour protéger les **540 tests passing** (v0.5.0).

### Phase 1 — Créer `ports/` avec re-exports (v0.5.x, non-breaking)

1. Créer `ports/__init__.py`, `ports/persistence.py`, `ports/executor.py`, `ports/trigger.py`
2. **Copier** (pas déplacer) les ABC et exceptions de contrat depuis leurs emplacements actuels
3. Faire pointer les fichiers originaux (`persistence/base.py`, `executors/base.py`, `triggers/base.py`) vers `ports/` via re-imports :
   ```python
   # persistence/base.py — après Phase 1
   # Re-export depuis ports/ pour compatibilité ascendante
   from pyworkflow_engine.ports.persistence import (
       BasePersistence,
       JobNotFoundError,
       PersistenceError,
       TransactionError,
   )
   ```
4. **Les 540 tests continuent de passer sans modification.**

### Phase 2 — Déplacer les implémentations sous `adapters/` (v0.5.x, non-breaking)

1. Déplacer `persistence/memory.py`, `persistence/json_file.py`, etc. → `adapters/persistence/`
2. Déplacer `executors/local.py`, `executors/thread_pool.py`, etc. → `adapters/executors/`
3. Déplacer `triggers/manual.py`, `triggers/schedule.py` → `adapters/triggers/`
4. Maintenir des re-exports dans les anciens emplacements (`persistence/__init__.py`, etc.)
5. Marquer les anciens chemins d'import comme `deprecated` via des warnings :
   ```python
   import warnings
   warnings.warn(
       "Importing from pyworkflow_engine.persistence is deprecated. "
       "Use pyworkflow_engine.adapters.persistence instead.",
       DeprecationWarning,
       stacklevel=2,
   )
   ```

### Phase 3 — Supprimer les re-exports de compatibilité (v0.6.0, breaking)

1. Supprimer `persistence/`, `executors/`, `triggers/` à la racine du package
2. Mettre à jour tous les imports internes et la documentation
3. Mettre à jour le CHANGELOG avec la mention **Breaking Changes**
4. Bump version → `0.6.0`

### Calendrier estimé

| Phase | Version | Breaking ? | Effort estimé | Prérequis |
|---|---|---|---|---|
| Phase 1 — `ports/` | v0.5.1 | ❌ Non | ~2h | Aucun |
| Phase 2 — Réorganisation `adapters/` | v0.5.2 | ❌ Non | ~4h | Phase 1 |
| Phase 3 — Nettoyage | v0.6.0 | ✅ Oui | ~2h | Phase 2 validée + migration docs |

---

## Alternatives considérées

### Alternative A — Statu quo (ne rien faire)

Les ABC restent dans `persistence/base.py`, `executors/base.py`, etc.

**Pour** : zéro effort, pas de risque de régression.
**Contre** : la frontière interface/implémentation reste invisible, la compréhension du code repose sur la connaissance implicite du développeur.

**Verdict** : ❌ Rejetée — la clarté architecturale est un investissement qui se rentabilise à mesure que le projet grandit.

### Alternative B — Ports comme fichiers dans chaque sous-package (pas de dossier `ports/`)

Garder `persistence/base.py`, `executors/base.py`, `triggers/base.py` comme "ports implicites".

**Pour** : moins de déplacement de fichiers.
**Contre** : ne résout pas le problème de visibilité. Un `base.py` dans chaque dossier n'est pas auto-documenté comme un package `ports/`.

**Verdict** : ❌ Rejetée — c'est l'état actuel, et il a été identifié comme problématique.

### Alternative C — Architecture hexagonale complète avec `data/` et `clients/`

Répliquer exactement la structure `flowledger`.

**Pour** : cohérence avec le projet précédent.
**Contre** : `pyworkflow_engine` est une bibliothèque technique, pas une application métier. `data/` et `clients/` n'ont pas de sens ici.

**Verdict** : ❌ Rejetée — il faut adapter le pattern au contexte, pas le copier aveuglément.

---

## Conséquences

### Positives

- **Lisibilité architecturale** — quiconque regarde la structure comprend immédiatement ce qui est _contrat_ (`ports/`) vs _interchangeable_ (`adapters/`)
- **Cohérence avec le système d'extras** — `pip install pyworkflow-engine[celery]` active un adapter, ce qui est désormais visible dans l'arborescence
- **Testabilité** — les tests unitaires du domaine (`engine/`) peuvent mocker uniquement les `ports/`, sans jamais importer les `adapters/`
- **Onboarding** — un nouveau contributeur comprend la frontière en 30 secondes
- **Préparation future** — ajout d'un `adapters/cli/`, `adapters/api/`, `adapters/mcp/` possible sans toucher au domaine

### Négatives

- **Effort de migration** — ~8h réparties sur 3 phases
- **Période de double-import** — pendant les phases 1-2, les modules existent à deux endroits (mitigé par les re-exports)
- **Breaking change en v0.6.0** — les utilisateurs qui importent depuis `pyworkflow_engine.persistence` devront mettre à jour

### Risques

| Risque | Probabilité | Mitigation |
|---|---|---|
| Régression de tests pendant la migration | Faible | Migration par re-exports, pas de suppression tant que les tests passent |
| Confusion pendant la période de double-import | Moyenne | Deprecation warnings explicites, documentation mise à jour |
| Sur-ingénierie pour un projet de cette taille | Faible | Le pattern est léger (un seul dossier `ports/` avec 3-4 fichiers) |

---

## Références

- [Hexagonal Architecture (Alistair Cockburn)](https://alistair.cockburn.us/hexagonal-architecture/)
- [Ports & Adapters in Python — Cosmic Python (Harry Percival & Bob Gregory)](https://www.cosmicpython.com/)
- ADR-002 — Refactoring architectural : `core/` monolithique → couches modulaires
- ADR-004 — Style d'imports absolus et introduction du module `config/`
- ADR-005 — API déclarative par décorateurs (`@step`, `@job`)
- Retour d'expérience projet `flowledger` — architecture hexagonale appliquée à un domaine métier comptable
