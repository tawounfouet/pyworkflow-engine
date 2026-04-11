# ADR-012 — Renommage `persistence` → `storage` dans tout le codebase

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-012                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (architecture hexagonale, `adapters/`), ADR-011 (API adapter + SQLite) |
| **Version cible** | v0.7.0                         |

---

## Contexte

Le codebase utilise le terme `persistence` à plusieurs niveaux :

| Emplacement | Symbole actuel |
|---|---|
| `src/pyworkflow_engine/config/persistence.py` | `PersistenceConfig` |
| `src/pyworkflow_engine/adapters/persistence/` | `SQLitePersistence`, `MemoryPersistence`, `JsonPersistence` |
| `src/pyworkflow_engine/ports/` | `PersistencePort` / `BasePersistence` |
| `examples/persistence_backends.py` | — |
| `examples/persistence_simple.py` | — |
| Documentation et docstrings | "backend de persistence", "sans persistence" |

La question a été soulevée lors d'une revue : **`persistence` est-il le meilleur terme, ou serait-il plus idiomatique d'utiliser `storage` ou `db` ?**

---

## Analyse

### Les trois candidats

| Terme | Longueur | Sémantique exacte | Précédents |
|---|---|---|---|
| `persistence` | Long (11 car.) | ✅ Précis (DDD, JPA, Hibernate) | JPA, Spring, Doctrine |
| `db` | Court (2 car.) | ⚠️ Implique une base relationnelle | Django (`DATABASES`), Rails, Flask-SQLAlchemy |
| `storage` | Court (7 car.) | ✅ Couvre tous les backends | Azure Storage, Laravel Storage, Android, Celery |

### Problème sémantique de `persistence`

Le terme `persistence` est exact dans le contexte **DDD / architecture hexagonale** — il désigne le fait de *persister l'état* au-delà du cycle de vie d'un processus. Cependant, il introduit une contradiction interne dans ce projet :

```python
# Contradiction sémantique
cfg = PersistenceConfig(backend="memory")  # ← "memory" ne persiste rien !
```

Le backend `"memory"` ne persiste rien entre deux exécutions. Le nommer `PersistenceConfig(backend="memory")` est sémantiquement incohérent. `StorageConfig(backend="memory")` est neutre et juste : la mémoire vive *est* un espace de stockage, même éphémère.

### Pourquoi pas `db` ?

`db` est tentant (Django, Rails, Flask-SQLAlchemy) mais reste trop restrictif :

```python
# Sonne faux
cfg = DatabaseConfig(backend="json")    # un fichier JSON n'est pas une "database"
cfg = DatabaseConfig(backend="memory")  # la RAM n'est pas une "database"
```

`db` / `database` convient quand tous les backends sont des systèmes de gestion de bases de données. Ce n'est pas le cas ici.

### Pourquoi `storage` est le bon choix

`storage` est le terme générique pour tout mécanisme de *stockage de données*, quelle que soit sa nature :

| Backend | `persistence` | `db` | `storage` |
|---|---|---|---|
| `"sqlite"` | ✅ | ✅ | ✅ |
| `"memory"` | ❌ contradiction | ❌ incorrect | ✅ (stockage éphémère) |
| `"json"` | ✅ | ❌ incorrect | ✅ (stockage fichier) |

**Précédents industrie** :

- **Azure** : `Azure Storage` (blob, table, queue, file)
- **Laravel** : facade `Storage` (local, S3, SFTP…)
- **Android** : `SharedPreferences`, `Room` = storage layers
- **Celery** : `result_backend` — même concept (stocker les résultats de tâches)
- **Python stdlib** : `shelve`, `pickle` — stockage, pas "persistence"

---

## Décision

**→ Renommer `persistence` en `storage` dans l'intégralité du codebase.**

### Périmètre du renommage

| Catégorie | Avant | Après |
|---|---|---|
| Dossier adapters | `adapters/persistence/` | `adapters/storage/` |
| Module config | `config/persistence.py` | `config/storage.py` |
| Classe config | `PersistenceConfig` | `StorageConfig` |
| Classe base | `BasePersistence` / `PersistencePort` | `BaseStorage` / `StoragePort` |
| Classe SQLite | `SQLitePersistence` | `SQLiteStorage` |
| Classe mémoire | `MemoryPersistence` | `MemoryStorage` |
| Classe JSON | `JsonPersistence` | `JsonStorage` |
| Exemples | `persistence_backends.py` | `storage_backends.py` |
| Exemples | `persistence_simple.py` | `storage_simple.py` |
| Champ `db_path` | `db_path` | **conservé** (`db_path` reste idiomatique pour un chemin SQLite) |

> **Note** : le champ `db_path` dans `StorageConfig` est **conservé tel quel**. Il désigne explicitement le chemin d'un fichier SQLite — `db_path` est idiomatique et précis pour cet usage.

### Exemple avant / après

```python
# Avant
from pyworkflow_engine.config.persistence import PersistenceConfig

cfg = PersistenceConfig(db_path="workflow.db", backend="sqlite")
cfg = PersistenceConfig(backend="memory")  # ← contradiction sémantique

# Après
from pyworkflow_engine.config.storage import StorageConfig

cfg = StorageConfig(db_path="workflow.db", backend="sqlite")
cfg = StorageConfig(backend="memory")  # ← cohérent
```

---

## Alternatives rejetées

### Garder `persistence`

- ✅ Aucun changement, aucune migration
- ❌ Contradiction sémantique avec `backend="memory"`
- ❌ Moins idiomatique dans l'écosystème Python grand public

### Adopter `db`

- ✅ Court, universel (Django, Rails, Flask-SQLAlchemy)
- ❌ Incorrect pour `backend="json"` et `backend="memory"`
- ❌ Induirait en erreur : l'utilisateur s'attendrait à ne pouvoir brancher que des BDD relationnelles

---

## Conséquences

### Positives

- **Cohérence sémantique** : `StorageConfig(backend="memory")` est désormais sans contradiction.
- **API plus intuitive** : les utilisateurs familiers de Laravel, Azure ou Android reconnaissent immédiatement le concept.
- **Extensibilité** : un futur backend `"s3"`, `"redis"`, ou `"filesystem"` s'intègre naturellement sous `storage` sans frictions de nommage.

### Négatives / risques

- **Breaking change** : tous les imports utilisant `PersistenceConfig`, `SQLitePersistence`, etc. doivent être mis à jour.
- **Migration nécessaire** : les utilisateurs existants devront adapter leur code (à documenter dans `CHANGELOG.md`).

### Plan de migration

Le renommage est effectué en une seule passe automatisée via script `sed` + `git mv`, dans l'ordre :

1. Remplacement du contenu des fichiers (classes, imports, docstrings)
2. Renommage des fichiers (`*.py`)
3. Renommage des dossiers (`adapters/persistence/` → `adapters/storage/`)
4. Mise à jour des `__init__.py` et re-exports
5. Validation : `grep -rni "persistence"` → zéro occurrence
6. Tests : `pytest` + `mypy`
7. Commit sur branche dédiée `refactor/rename-persistence-to-storage`

---

## Statut

✅ Décision prise — implémentation planifiée en v0.7.0.
