# Audit Production-Readiness — pyworkflow-engine

> **Version auditée :** v0.7.0  
> **Date :** 2026-04-13  
> **Périmètre :** `src/pyworkflow_engine/` + couche `jobs/` / `pipelines/`  
> **Méthode :** lecture statique exhaustive, grep de patterns critiques, analyse architecturale

---

## Table des matières

1. [Verdict global](#1-verdict-global)
2. [Architecture](#2-architecture)
3. [Couche Engine](#3-couche-engine)
4. [Couche Storage (Persistence)](#4-couche-storage-persistence)
5. [Adaptateur API REST](#5-adaptateur-api-rest)
6. [Adaptateur Celery](#6-adaptateur-celery)
7. [Façade WorkflowEngine](#7-façade-workflowengine)
8. [Gestion des erreurs et exceptions](#8-gestion-des-erreurs-et-exceptions)
9. [Sécurité](#9-sécurité)
10. [Performance et scalabilité](#10-performance-et-scalabilité)
11. [Typage statique](#11-typage-statique)
12. [Tests et couverture](#12-tests-et-couverture)
13. [Roadmap Production — par priorité](#13-roadmap-production--par-priorité)

---

## 1. Verdict global

| Dimension | Note | Commentaire |
|-----------|------|-------------|
| Architecture | ★★★★☆ | Hexagonale bien appliquée, isolation claire |
| Core engine | ★★★★☆ | Solide, SRP respecté, bien testé |
| Persistence / Storage | ★★★☆☆ | SQLite bon ; gap de migration ; pas de cleanup connexion |
| API REST | ★★★☆☆ | Auth désactivée par défaut, CORS wildcard |
| Sécurité | ★★☆☆☆ | Plusieurs risques non bloquants mais à corriger |
| Performance | ★★★☆☆ | Acceptable à l'échelle actuelle ; points de friction identifiés |
| Typage | ★★★☆☆ | `Any` présent dans des chemins critiques |
| Tests | ★★★★☆ | 535 tests, 84 % — bonne base, gaps identifiés |

**Conclusion :** la base est saine. L'architecture est la bonne décision. Les points bloquants pour un déploiement production (auth désactivée, CORS trop permissif, migration incomplète) sont peu nombreux et simples à corriger. Le projet est **production-ready en environnement de confiance** ; il nécessite des ajustements ciblés avant une exposition publique.

---

## 2. Architecture

### Hexagonal (Ports & Adapters) — bien exécutée

La séparation `ports/` → `adapters/` est cohérente et tenue. Le `engine/` ne dépend jamais d'un adapter concret, ce qui est vérifiable par grep : aucun import direct de `sqlite3`, `celery`, `fastapi` dans `engine/` ou `models/`.

```
engine/ + models/          → zéro dépendance externe
ports/ (BaseStorage, BaseExecutor, BaseTrigger)  → contrats purs
adapters/ (SQLite, Celery, FastAPI, CLI…)        → implémentations opt-in
facade.py                  → point d'assemblage
```

**Critique positive :** les lazy imports (`TYPE_CHECKING`, `importlib`) évitent de charger les dépendances optionnelles (Celery, SQLAlchemy) si l'utilisateur n'en a pas besoin. C'est la bonne approche pour une bibliothèque SDK.

### Critique — `facade.py` : God Object en croissance

`WorkflowEngine` fait 800+ lignes et cumule :
- Exécution pure (`run`, `run_pipeline`)
- Persistance (`save_job`, `run_with_storage`, `list_jobs`)
- Administration IA (`create_agent`, `chat`, `upload_knowledge`)
- Bootstrap de configuration (`_bootstrap_from_config`)

Chaque responsabilité supplémentaire augmente la surface testable et cognitive. L'objectif v1.0 devrait être de déléguer vers des sous-facades :

```python
# Avant
engine.create_agent(...)
engine.run_with_storage(...)

# Après (suggestion)
engine.ai.create_agent(...)       # AIFacade
engine.storage.run(...)           # StorageFacade
engine.run(...)                   # API publique minimale
```

---

## 3. Couche Engine

### `engine/runner.py` — propre, SRP respecté

[runner.py:24](src/pyworkflow_engine/engine/runner.py#L24) — `WorkflowRunner` a une responsabilité unique : orchestrer les executors dans l'ordre topologique. La gestion du retry, de la suspension et de la persistence est délibérément laissée à l'appelant. C'est le bon choix.

**Point notable :** l'ordre de priorité des executors est documenté et implémenté proprement ([runner.py:133](src/pyworkflow_engine/engine/runner.py#L133)) :
1. `executor_name` (named/custom)
2. `executor_type` (THREAD, PROCESS, ASYNC)
3. fallback local

### `engine/dag.py` — algorithmes corrects, un risque de stack

[dag.py:86](src/pyworkflow_engine/engine/dag.py#L86) — `_detect_cycles` utilise une DFS récursive. Pour des workflows profonds (chaînes linéaires de 500+ steps), Python atteindra `RecursionError` (limite par défaut : 1000).

**Risque :** faible en pratique (les workflows réels sont larges, pas profonds), mais non protégé.

```python
# Correctif minimal
import sys
sys.setrecursionlimit(max(sys.getrecursionlimit(), len(self._steps_by_name) * 2))

# Correctif propre : remplacer la DFS récursive par une DFS itérative
```

### `engine/parallel_runner.py` — correct mais inefficace

[parallel_runner.py:134](src/pyworkflow_engine/engine/parallel_runner.py#L134) — un nouveau `ThreadPoolExecutor` est créé **pour chaque groupe parallèle**. Si un workflow a 10 groupes, 10 pools sont créés et détruits. Le coût de création d'un pool est non négligeable.

```python
# Actuel : pool créé/détruit par groupe
with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
    ...

# Suggestion : pool créé une seule fois dans __init__ ou execute()
with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
    for group in parallel_groups:
        self._execute_group(pool, ...)
```

**Autre point :** [parallel_runner.py:172](src/pyworkflow_engine/engine/parallel_runner.py#L172) — `with self._lock:` protège l'append sur `job_run.step_runs`, ce qui est correct. La lecture est documentée explicitement. Pas de lock tenu pendant l'exécution du step — pas de sérialisation involontaire.

### `engine/context.py` — thread-safe, mais `freeze()` non utilisé

[context.py:45](src/pyworkflow_engine/engine/context.py#L45) — `_frozen` est présent, `set()` le vérifie, mais aucun runner n'appelle `freeze()`. La protection est une lettre morte. Soit la retirer, soit l'activer systématiquement après l'exécution d'un step pour empêcher les mutations rétroactives.

### `engine/suspension.py` — silences trop larges

```python
# suspension.py:78-79
except Exception:
    pass  # Fallback silencieux

# suspension.py:107-108
except Exception:
    pass  # Fallback silencieux — le dict mémoire reste disponible
```

Trois blocs `except Exception: pass` dans ce fichier. Une suspension ratée est un état indéfini du workflow. Au minimum, ces exceptions devraient être loggées en `WARNING`.

---

## 4. Couche Storage (Persistence)

### `adapters/storage/sqlite.py` — bien conçu, deux lacunes

#### Points forts

- Connexions thread-local ([sqlite.py:213](src/pyworkflow_engine/adapters/storage/sqlite.py#L213)) — isolation correcte sans pooling explicite
- WAL mode + foreign keys + indexes ([sqlite.py:229](src/pyworkflow_engine/adapters/storage/sqlite.py#L229)) — configuration sensée
- SCHEMA_VERSION = 4 avec table `schema_version` — versioning présent

#### Lacune 1 : gap dans la migration

[sqlite.py:258](src/pyworkflow_engine/adapters/storage/sqlite.py#L258) — la logique de migration est :

```python
if current_version == 0:
    conn.executescript(SCHEMA_SQL)       # v0 → v4 (fresh install)
else:
    if current_version < 3:
        conn.executescript(MIGRATION_V2_TO_V3)  # v2 → v3 seulement
# ❌ v3 → v4 non géré
```

Une base existante en v3 ne recevra pas la migration vers v4. La version en DB sera mise à jour à 4 sans que le schéma v4 soit réellement appliqué. **Risque : runtime errors silencieuses sur des colonnes manquantes.**

**Correctif :**
```python
if current_version < 3:
    conn.executescript(MIGRATION_V2_TO_V3)
if current_version < 4:
    conn.executescript(MIGRATION_V3_TO_V4)
# etc. — migrations cumulatives et indépendantes
```

#### Lacune 2 : pas de cleanup des connexions thread-local

Les connexions sont créées dans `threading.local()` mais jamais fermées. Dans un serveur ASGI gérant des threads de worker, les connexions s'accumulent sans être libérées.

```python
# Ajouter une méthode de cleanup
def close(self) -> None:
    if hasattr(self._local, "connection"):
        self._local.connection.close()
        del self._local.connection
```

#### Handlers perdus à la désérialisation

[sqlite.py:288](src/pyworkflow_engine/adapters/storage/sqlite.py#L288) — `_deserialize_job` reconstruit les `Step` depuis JSON. `Step.handler` (un `Callable`) ne peut pas être sérialisé, donc les steps rechargés ont `handler=None`. Le moteur doit réinjecter les handlers depuis un registre en mémoire. Ce comportement est attendu mais **non documenté dans les erreurs** : si le registre est absent, l'erreur survient lors de l'exécution, pas au chargement.

---

## 5. Adaptateur API REST

### Auth désactivée par défaut — risque opérationnel

[config.py:33](src/pyworkflow_engine/adapters/api/config.py#L33) :
```python
require_auth: bool = False
api_key: str | None = None
```

[deps.py:47](src/pyworkflow_engine/adapters/api/deps.py#L47) :
```python
if not config.require_auth:
    return None   # Tout le monde passe
```

L'infrastructure d'auth est présente (`verify_api_key`, `APIKeyHeader`, `Depends`) et branchée sur toutes les routes. **C'est une bonne conception.** Le problème est que la valeur par défaut laisse l'API ouverte sans avertissement.

**Recommandation :** au démarrage du serveur, logger un `WARNING` explicite si `require_auth=False` :
```python
if not config.require_auth:
    logger.warning(
        "API running WITHOUT authentication. "
        "Set require_auth=True and api_key=<secret> for production."
    )
```

### CORS wildcard par défaut

[config.py:32](src/pyworkflow_engine/adapters/api/config.py#L32) :
```python
cors_origins: list[str] = field(default_factory=lambda: ["*"])
```

`allow_credentials=True` combiné à `allow_origins=["*"]` est invalide selon la spec CORS et rejeté par les navigateurs modernes. FastAPI lèvera une erreur ou ignorera `allow_credentials`. En tout état de cause, un wildcard CORS en production est une mauvaise pratique.

**Recommandation :** documenter clairement que `cors_origins=["*"]` est pour le développement local uniquement. Envisager de forcer une valeur explicite en production.

### Rate limiting absent

Aucune limite de débit sur les routes. Un client peut soumettre des milliers de runs. À ajouter via `slowapi` (wrapper `limits` pour FastAPI) ou un reverse proxy (nginx, Caddy).

### WebSocket présent mais non audité

[routes/websocket.py](src/pyworkflow_engine/adapters/api/routes/websocket.py) existe. Son comportement sous charge (reconnexion, backpressure, cleanup des connexions mortes) n'a pas été vérifié.

---

## 6. Adaptateur Celery

[adapters/celery/executor.py:321](src/pyworkflow_engine/adapters/celery/executor.py#L321) :
```python
except Exception:
    pass  # Ne pas propager les erreurs de shutdown
```

Acceptable pour un shutdown, mais sans log associé.

**Points à vérifier :**
- Le timeout des tasks Celery (`task_soft_time_limit`) est-il propagé depuis `Step.timeout` ?
- En cas d'échec Celery (broker indisponible), l'erreur remonte-t-elle clairement ou se perd-elle dans `AsyncResult.get()` ?
- Les tasks sont-elles idempotentes ? En cas de re-queue automatique par Celery, un step pourrait s'exécuter deux fois.

---

## 7. Façade WorkflowEngine

### Multiplication des `except Exception` non loggés

Grep sur `facade.py` : **13 occurrences** de `except Exception`. Plusieurs sont annotés `# noqa: BLE001` (blind exception catch autorisé explicitement), ce qui est cohérent avec une dégradation gracieuse. Mais certains swallowent des erreurs qui devraient être loggées :

```python
# facade.py:571
except Exception:  # noqa: BLE001
    # ❌ Aucun log — l'erreur disparaît silencieusement
```

**Pattern recommandé :**
```python
except Exception as e:  # noqa: BLE001
    logger.warning("Non-fatal error during X: %s", e, exc_info=True)
```

### Checkpoint non-atomique

Dans `run_with_storage`, chaque step est checkpointé individuellement :
```python
for step_name in execution_order:
    self._runner.execute(job_run, [step_name], ...)
    self._save_job_run_checkpoint(job_run)   # sauvegarde intermédiaire
```

Si le process crash entre deux steps, l'état partiel est sauvegardé, mais la reprise peut ré-exécuter un step dont le résultat a déjà été appliqué au contexte. **Les handlers de steps doivent être idempotents** — ce prérequis n'est pas documenté.

### Registre de handlers et round-trip storage

Quand un job est chargé depuis le storage (`get_job`), les `Step.handler` sont `None`. La façade réinjecte les handlers depuis `self._job_registry`. Si l'engine est redémarré sans re-enregistrer les jobs (scénario : worker restart), les jobs stockés sont inutilisables. Ce comportement est une **contrainte architecturale** qui doit être explicitement documentée et/ou protégée par une assertion.

---

## 8. Gestion des erreurs et exceptions

### Bilan des `except Exception: pass` dans le codebase

```
engine/suspension.py       : 3 blocs silencieux
engine/ai/agent_service.py : 2 blocs silencieux
facade.py                  : ~5 blocs partiellement silencieux
celery/executor.py         : 1 bloc silencieux (shutdown)
logging/utils.py           : 2 blocs silencieux
```

**Règle recommandée :** `except Exception: pass` est acceptable uniquement pour les opérations best-effort (envoi de métriques, shutdown). Pour toute opération d'état (suspension, checkpoint, agent memory), le minimum est un `logger.warning(..., exc_info=True)`.

### Hiérarchie d'exceptions — point fort

La hiérarchie dans `exceptions.py` est bien conçue :
- `WorkflowError` (base)
  - `DAGValidationError`
  - `StepExecutionError`
  - `WorkflowSuspended`
  - `ContextError`
  - `StorageError` / `TransactionError` / `JobNotFoundError`

Les exceptions contextualisées (avec `job_name`, `step_name`, `details`) facilitent le debugging. C'est un atout réel.

---

## 9. Sécurité

### Matrice des risques

| Risque | Localisation | Sévérité | Facilité de correction |
|--------|-------------|----------|----------------------|
| Auth désactivée par défaut | `adapters/api/config.py:33` | Moyenne | Triviale (warning au démarrage) |
| CORS wildcard par défaut | `adapters/api/config.py:32` | Faible-Moyenne | Triviale (documenter + env-specific config) |
| API key en clair dans la config | `adapters/api/config.py:34` | Faible | Utiliser une variable d'environnement |
| Silences sur erreurs de suspension | `engine/suspension.py:78` | Faible | Logger + raise |
| Pas de rate limiting | `adapters/api/` | Faible | Ajouter `slowapi` |
| Handlers non validés après chargement storage | `facade.py` | Faible | Assertion explicite |

**Aucun risque critique (injection SQL, RCE, SSRF)** n'a été identifié dans le code audité. L'absence de dépendances externes dans le core réduit la surface d'attaque.

### Recommandation concrète : secrets via variables d'environnement

```python
# Actuel (config.py)
api_key: str | None = None

# Recommandé
import os
api_key: str | None = field(default_factory=lambda: os.environ.get("PYWORKFLOW_API_KEY"))
```

---

## 10. Performance et scalabilité

### Création de ThreadPoolExecutor par groupe

[parallel_runner.py:134](src/pyworkflow_engine/engine/parallel_runner.py#L134) — chaque groupe parallèle instancie et détruit un `ThreadPoolExecutor`. Le coût de création (~5-10ms par pool) est négligeable pour quelques groupes mais devient perceptible sur des workflows à 20+ groupes avec steps rapides.

**Correctif :** partager le pool sur toute la durée d'exécution du workflow.

### `copy.deepcopy` dans le contexte

[context.py](src/pyworkflow_engine/engine/context.py) utilise `copy.deepcopy` pour isoler les outputs de steps. Sur des payloads volumineux (DataFrames, listes de milliers d'objets), ce deep copy est un goulot. Pour les workflows de traitement de données lourds, considérer une référence partagée avec validation d'immutabilité plutôt qu'une copie systématique.

### Pagination non activée par défaut sur `list_job_runs`

Si aucune limite n'est passée à `list_job_runs()`, toutes les lignes sont chargées en mémoire. Sur une base avec 100K+ runs, c'est une OOM guarantee.

**Correctif :** imposer une `limit` maximale par défaut dans `BaseStorage.list_job_runs()`.

### SQLite : limites opérationnelles

| Scénario | Limite approximative |
|----------|----------------------|
| Runs/jour | ~5-10K avec WAL mode |
| Taille max recommandée | < 10 GB |
| Lectures concurrentes | ✅ Bonnes (WAL) |
| Écritures concurrentes | ⚠️ Sérialisées (1 writer) |

Au-delà de ces seuils, migrer vers SQLAlchemy + PostgreSQL.

---

## 11. Typage statique

### `Any` dans les chemins critiques

```python
# runner.py:52
retry_handler: Any | None = None  # devrait être RetryHandler | None

# runner.py:114
def execute_single(self, step: Step, context: WorkflowContext) -> Any:
# devrait être -> dict[str, Any] | None

# facade.py
def create_agent(...) -> Any:  # devrait être Agent
```

Ces `Any` cassent l'inférence de type côté consommateur. Un IDE ne peut pas autocompléter les champs de retour d'`execute_single`. Utiliser `TypeVar`, `Generic[T]`, ou des types concrets là où c'est possible.

### `dict[str, Any]` comme type de contexte

Le contexte transporte des données arbitraires, ce qui rend `dict[str, Any]` difficile à éviter complètement. Une amélioration progressive serait d'utiliser `TypedDict` pour les structures connues (output de steps typés), laissant `Any` uniquement pour les données dynamiques.

---

## 12. Tests et couverture

### Bilan (v0.7.0)

| Métrique | Valeur |
|----------|--------|
| Tests totaux | 535 |
| Couverture lignes | 84 % |
| Linting | ruff |
| Type checking | mypy --strict |
| Tests async | pytest-asyncio |

### Gaps identifiés

**Haute priorité :**
- `engine/suspension.py` — les chemins `except Exception: pass` ne sont pas testés
- `adapters/storage/sqlite.py` — migration v3 → v4 non testée
- `engine/parallel_runner.py` — exécution concurrente sous charge (race conditions)
- `facade.py` — comportement quand les handlers sont absents après chargement storage

**Moyenne priorité :**
- API routes sans auth (`require_auth=False`) — tests de régression si on active l'auth
- Celery executor — comportement quand le broker est indisponible
- `DAGResolver._detect_cycles` — DAG de 500+ nœuds (RecursionError)

**Faible priorité :**
- GUI / TUI — tests manuels suffisants à ce stade (alpha)
- WebSocket — load test de connexions simultanées

---

## 13. Roadmap Production — par priorité

### P0 — Bloquants avant exposition publique

| # | Action | Fichier(s) | Effort |
|---|--------|-----------|--------|
| 1 | Logger un `WARNING` si `require_auth=False` au démarrage de l'API | [adapters/api/server.py](src/pyworkflow_engine/adapters/api/server.py) | XS |
| 2 | Documenter `cors_origins=["*"]` comme dev-only + proposer env-specific default | [adapters/api/config.py](src/pyworkflow_engine/adapters/api/config.py) | XS |
| 3 | Corriger le gap de migration SQLite v3 → v4 | [adapters/storage/sqlite.py:258](src/pyworkflow_engine/adapters/storage/sqlite.py#L258) | S |
| 4 | Ajouter `close()` / cleanup des connexions thread-local dans `SQLiteStorage` | [adapters/storage/sqlite.py:202](src/pyworkflow_engine/adapters/storage/sqlite.py#L202) | S |

### P1 — Qualité et robustesse (v0.8)

| # | Action | Fichier(s) | Effort |
|---|--------|-----------|--------|
| 5 | Remplacer les `except Exception: pass` par des logs `WARNING` dans `suspension.py` | [engine/suspension.py](src/pyworkflow_engine/engine/suspension.py) | XS |
| 6 | Partager le `ThreadPoolExecutor` sur toute l'exécution du workflow (pas par groupe) | [engine/parallel_runner.py](src/pyworkflow_engine/engine/parallel_runner.py) | S |
| 7 | Appeler `context.freeze()` après chaque step dans les runners | [engine/runner.py](src/pyworkflow_engine/engine/runner.py), [engine/parallel_runner.py](src/pyworkflow_engine/engine/parallel_runner.py) | XS |
| 8 | Imposer une `limit` par défaut sur `list_job_runs()` | [ports/storage.py](src/pyworkflow_engine/ports/storage.py), [adapters/storage/sqlite.py](src/pyworkflow_engine/adapters/storage/sqlite.py) | S |
| 9 | Documenter l'exigence d'idempotence des handlers (checkpoints non-atomiques) | [README.md](README.md), [facade.py](src/pyworkflow_engine/facade.py) | XS |
| 10 | Ajouter validation explicite des handlers après chargement storage | [facade.py](src/pyworkflow_engine/facade.py) | S |
| 11 | Remplacer `retry_handler: Any` par `retry_handler: RetryHandler | None` dans les runners | [engine/runner.py:52](src/pyworkflow_engine/engine/runner.py#L52) | XS |
| 12 | Protéger `_detect_cycles` contre `RecursionError` (DFS itérative ou `sys.setrecursionlimit`) | [engine/dag.py:86](src/pyworkflow_engine/engine/dag.py#L86) | M |

### P2 — Production à l'échelle (v1.0)

| # | Action | Effort |
|---|--------|--------|
| 13 | Rate limiting sur l'API (`slowapi` ou reverse proxy) | M |
| 14 | Scinder `WorkflowEngine` : sous-facade `engine.ai`, `engine.storage` | L |
| 15 | Typer `execute_single` → `dict[str, Any] \| None` au lieu de `Any` | S |
| 16 | API key via variable d'environnement (`PYWORKFLOW_API_KEY`) | XS |
| 17 | Stress tests parallélisme : 100 steps concurrents, 50 workflows simultanés | M |
| 18 | OpenTelemetry traces (spans par step, par workflow) | L |
| 19 | Mécanisme de graceful shutdown (annulation en vol) | L |
| 20 | Migration vers `msgpack` pour les checkpoints (si perf critiques) | M |

### P3 — Nice-to-have

| # | Action |
|---|--------|
| 21 | Support multi-tenancy (isolation par namespace dans le storage) |
| 22 | Intégration secrets manager (Vault, AWS SSM) pour l'API key |
| 23 | WebSocket : tests de charge et cleanup des connexions mortes |
| 24 | GUI / TUI : stabilisation pour beta publique |

---

## Annexe — Commandes de vérification rapide

```bash
# Vérifier l'absence d'imports de concrete adapters dans engine/
grep -r "import sqlite3\|import celery\|import fastapi" src/pyworkflow_engine/engine/

# Lister tous les except Exception silencieux
grep -n "except Exception" src/pyworkflow_engine/**/*.py | grep -v "as e\|as exc\|as err"

# Vérifier que la migration est complète pour toutes les versions
grep -A5 "current_version" src/pyworkflow_engine/adapters/storage/sqlite.py

# Vérifier que require_auth est activé dans la config de prod
python -c "from pyworkflow_engine.adapters.api.config import APIConfig; c = APIConfig(); print('Auth:', c.require_auth, '| CORS:', c.cors_origins)"
```

---

*Audit réalisé par analyse statique du code source. Les métriques de performance sont des estimations basées sur les patterns observés, non des benchmarks mesurés.*
