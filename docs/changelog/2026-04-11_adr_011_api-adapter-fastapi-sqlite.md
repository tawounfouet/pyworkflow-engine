# ADR-011 — API Adapter : FastAPI + SQLite dans `adapters/api/`

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-011                             |
| **Date**    | 11 avril 2026                       |
| **Statut**  | ✅ Décision prise                   |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (architecture hexagonale), ADR-007 (adapter complexe vs simple), ADR-008 (CLI adapter), ADR-010 (GUI adapter NiceGUI) |
| **Version cible** | v0.10.0                        |

---

## Contexte

### Situation actuelle

Le projet dispose de trois interfaces utilisateur couvrant des segments distincts :

| Adapter | ADR | Statut | Segment |
|---|---|---|---|
| CLI (`adapters/cli/`) | ADR-008 | ✅ Implémenté | Scriptabilité, CI/CD, pipes Unix |
| TUI (`adapters/tui/`) | ADR-009 | ✅ Spécifié | Supervision interactive terminal, SSH |
| GUI (`adapters/gui/`) | ADR-010 | ✅ Spécifié | Dashboard web, non-développeurs |

Ces trois interfaces sont des **interfaces humaines** — elles supposent un utilisateur physique devant un écran. Un pan entier de cas d'usage reste non couvert : les **intégrations machine-to-machine** (M2M).

Le `pyproject.toml` déclare déjà un extra `fastapi` :

```toml
fastapi = ["fastapi>=0.100", "uvicorn>=0.20"]
```

Le dossier `adapters/api/` existe avec un `__init__.py` vide (placeholder). La `SQLitePersistence` est implémentée et testée dans `adapters/persistence/sqlite.py`, avec WAL mode, indexation, FK constraints, et un schéma versionnné (v2).

### Le besoin

| Scénario | CLI | TUI | GUI | Besoin API |
|---|---|---|---|---|
| Intégration Terraform / Ansible / scripts d'infra | ⚠️ Possible (subprocess) | ❌ | ❌ | ✅ `curl POST /api/v1/runs` |
| Webhook entrant (GitHub, Slack, PagerDuty) | ❌ | ❌ | ❌ | ✅ Endpoint webhook |
| Frontend React/Vue/Svelte custom | ❌ | ❌ | ⚠️ NiceGUI uniquement | ✅ JSON API standard |
| Monitoring externe (Datadog, Grafana) | ❌ | ❌ | ❌ | ✅ `GET /api/v1/health` + métriques |
| Déclenchement programmatique depuis un autre service Python/Go/Rust | ⚠️ Import Python | ❌ | ❌ | ✅ HTTP universel |
| Multi-utilisateur simultané via réseau | ❌ (mono-process) | ❌ (mono-terminal) | ✅ (WebSocket) | ✅ HTTP stateless, N clients |
| Supervision depuis un outil d'orchestration (Airflow, Prefect) | ❌ | ❌ | ❌ | ✅ REST standard |
| SDK client auto-généré (OpenAPI → TypeScript/Go/Rust) | ❌ | ❌ | ❌ | ✅ OpenAPI spec native |
| CI/CD pipeline (GitHub Actions, GitLab CI) | ⚠️ Possible | ❌ | ❌ | ✅ `curl` natif |

### Les questions

1. Quel framework HTTP Python choisir pour l'API REST ?
2. SQLite est-il suffisant comme persistence par défaut de l'API, ou faut-il imposer PostgreSQL ?
3. Comment structurer l'adapter API dans l'architecture hexagonale ?
4. Comment gérer le temps réel (suivi de runs en cours) : SSE, WebSocket, ou polling ?
5. Quel modèle d'authentification pour la Phase 1 ?
6. Comment l'API s'articule-t-elle avec la GUI NiceGUI (ADR-010) ?
7. Quelle stratégie de versioning de l'API ?

---

## Analyse

### Comparaison des frameworks API Python

| Critère | Flask | Django REST | **FastAPI** | Litestar | Falcon |
|---|---|---|---|---|---|
| **Async natif (ASGI)** | ❌ WSGI | ❌ WSGI (+async views) | ✅ **ASGI natif** | ✅ ASGI | ⚠️ ASGI récent |
| **Validation Pydantic v2** | ❌ Manuel | ❌ Serializers DRF | ✅ **Natif** | ✅ Pydantic/attrs | ❌ Manuel |
| **OpenAPI auto-gen** | ❌ (flask-smorest) | ❌ (drf-spectacular) | ✅ **Natif** (`/docs`, `/redoc`) | ✅ Natif | ❌ |
| **Dependency injection** | ❌ | ❌ | ✅ **`Depends()`** | ✅ | ❌ |
| **SSE / WebSocket** | ⚠️ Extensions | ⚠️ Channels | ✅ **Natif** | ✅ | ⚠️ |
| **Performances (req/s)** | ~3k | ~2k | ✅ **~15k** (Starlette) | ✅✅ ~18k | ✅✅ ~20k |
| **Communauté 2026** | Large (déclin) | Large (stable) | ✅ **Dominante** (>80k ★) | Moyenne (croissance) | Petite (stable) |
| **Installation** | ~2 MB | ~30 MB (Django) | ✅ **~3 MB** | ~3 MB | ~1 MB |
| **Courbe d'apprentissage** | Faible | Élevée | ✅ **Faible** | Faible | Moyenne |
| **Écosystème middleware** | Large | Très large | ✅ **Starlette ASGI** | Starlette ASGI | Limité |

#### Litestar — le challenger sérieux

Litestar (anciennement Starlite) est le concurrent le plus crédible de FastAPI en 2026. Scores de performance légèrement supérieurs, API plus opinionated, dependency injection plus puissante. **Mais** :

- Communauté ~5× plus petite que FastAPI (16k vs 80k ★)
- Écosystème de middlewares et extensions moins fourni
- **Aucune synergie avec NiceGUI** (ADR-010) — NiceGUI est construit sur FastAPI/Starlette
- Moins de ressources d'apprentissage (tutoriels, StackOverflow, livres)

Pour un projet qui a **déjà choisi NiceGUI** (= FastAPI sous le capot), adopter un framework API différent créerait une incohérence de stack.

### L'argument décisif : cohérence de la stack

```
adapters/
├── cli/   → Typer + Rich            (terminal)
├── tui/   → Textual + Rich          (terminal interactif)
├── gui/   → NiceGUI (= FastAPI)     (web UI)
├── api/   → FastAPI                  (REST / WebSocket)
│              ↑              ↑
│              └─ MÊME STACK ─┘
```

NiceGUI (ADR-010) **est** une application FastAPI. Choisir FastAPI pour l'API REST signifie :

- Même pattern `async/await`, même système `Depends()` pour l'injection
- Même middleware ASGI (CORS, request ID, timing)
- **Possibilité de monter GUI + API sur le même serveur** (`gui_app.mount("/api/v1", api_app)`)
- Une seule stack à maîtriser pour l'équipe
- Les schemas Pydantic sont partagés entre API et GUI

### Verdict framework : FastAPI — choix unique et non négociable

Contrairement aux ADR précédents (CLI : Typer vs Click ; TUI : Textual vs curses ; GUI : 11 frameworks), il n'y a **pas de compétition réelle** ici. FastAPI est le choix convergent imposé par l'écosystème du projet.

---

### SQLite comme persistence par défaut de l'API

#### Pourquoi SQLite suffit

| Argument | Détail |
|---|---|
| **Déjà implémenté et testé** | `SQLitePersistence` est en production — 535 tests, 84% coverage, schéma v2 |
| **WAL mode activé** | Lectures concurrentes non bloquées par les écritures — géré nativement par `_get_connection()` |
| **Zéro infrastructure** | Pas de serveur DB à installer/maintenir — cohérent avec `pyworkflow gui` = "zéro infra" |
| **Performance suffisante** | ~5k lectures/s, ~200 écritures/s en WAL — couvre 80% des déploiements réels |
| **Fichier unique** | Backup = `cp workflow.db workflow.db.bak`, déploiement trivial |
| **Indexation existante** | `idx_job_runs_job_name`, `idx_job_runs_status`, `idx_job_runs_created_at` — optimisé pour les requêtes de l'API |
| **FK constraints** | `PRAGMA foreign_keys = ON` — intégrité référentielle job → job_runs → step_runs |
| **Thread-safety** | `threading.RLock` + connection-per-thread — compatible avec le modèle de concurrence de uvicorn/FastAPI |

#### Benchmarks attendus (SQLite WAL, PRAGMA optimisés)

La `SQLitePersistence` existante configure déjà :

```python
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA synchronous = NORMAL")
conn.execute("PRAGMA cache_size = -64000")    # 64 MB cache
conn.execute("PRAGMA temp_store = MEMORY")
```

| Métrique | Valeur attendue | Source |
|---|---|---|
| Lectures concurrentes /s | ~5 000 – 10 000 | WAL + 64 MB cache + mmap |
| Écritures /s | ~150 – 300 | WAL + NORMAL sync (pas FULL) |
| Latence P50 lecture | ~0.5 ms | Index sur job_name, status, created_at |
| Latence P99 lecture | ~3 ms | Pire cas : full table scan sur step_runs |
| Latence P50 écriture | ~2 ms | WAL mode, busy_timeout implicite |
| Latence P99 écriture | ~15 ms | Contention d'écriture sous charge |
| Taille DB / 10k runs | ~50 MB | JSON blob compact, 3 tables |

**Suffisant pour** : 1-20 utilisateurs simultanés, ~100 runs/heure, ~50k runs historiques.

#### Limites et seuils de bascule

| Limite SQLite | Impact API | Seuil de bascule | Mitigation |
|---|---|---|---|
| **Un seul writer** | Écritures sérialisées | > 500 écritures/s | `busy_timeout=5000` + retry applicatif |
| **Pas de réseau** | Un seul process peut écrire | Multi-instance (HA) | Bascule vers PostgreSQL via `SQLAlchemyPersistence` |
| **Pas de pub/sub** | Pas de notification DB → WebSocket | Besoin de push < 100ms | EventBus interne (Phase 2) |
| **JSON blob** | Pas de requêtes dans les sous-champs | Filtrage complexe sur step metadata | Colonnes dédiées ou `json_extract()` SQLite |
| **Taille fichier** | Performance dégradée > 10 GB | > 100k runs avec step_runs | `cleanup_old_runs()` existant, ou PostgreSQL |

#### Le chemin de migration : architecture hexagonale

Le design hexagonal (ADR-006) rend le changement de backend **transparent pour l'API** :

```python
# Phase 1 — SQLite (défaut, zéro infra)
persistence = SQLitePersistence("workflow.db")

# Phase 2 — PostgreSQL (sans changer une ligne dans l'API)
persistence = SQLAlchemyPersistence("postgresql://user:pass@host/db")

# L'injection reste identique
engine = WorkflowEngine(persistence=persistence)
api = create_app(engine=engine)
```

L'API n'a **aucune connaissance** du backend de persistence — elle dialogue uniquement avec la facade `WorkflowEngine`, qui elle-même dialogue avec le port `BasePersistence`. C'est la raison d'être de l'architecture hexagonale.

---

### Adapter simple vs complexe (règle ADR-007)

| Critère ADR-007 | Évaluation pour l'API |
|---|---|
| 2+ fichiers coordonnés | ✅ app + routes + schemas + deps + errors + middleware |
| Dépendance tierce avec configuration propre | ✅ FastAPI (routing, DI, OpenAPI, CORS, lifespan) + uvicorn |
| Concepts spécifiques au-delà du port | ✅ Routes HTTP, schemas Pydantic, middleware ASGI, SSE, WebSocket, auth |

→ L'API est un **adapter complexe** → `adapters/api/` (package dédié), conformément à ADR-007.

### Architecture : App → Routers → Schemas

```
┌────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Application                              │
│    create_app() factory — lifespan, middleware, exception handlers      │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                       Middleware Stack                           │   │
│  │  RequestID → Timing → CORS → Auth (optional)                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌───────────────────┐  ┌────────────────────┐  ┌─────────────────┐   │
│  │  /api/v1/jobs     │  │  /api/v1/runs      │  │ /api/v1/exec.   │   │
│  │                   │  │                    │  │                 │   │
│  │ GET  /            │  │ POST /             │  │ GET /           │   │
│  │ GET  /{name}      │  │ GET  /             │  └─────────────────┘   │
│  │ GET  /{name}/plan │  │ GET  /{id}         │                        │
│  │ POST /{name}/val. │  │ GET  /{id}/steps   │  ┌─────────────────┐   │
│  └───────────────────┘  │ POST /{id}/cancel  │  │ /api/v1/health  │   │
│                         │ POST /{id}/resume  │  │                 │   │
│  ┌───────────────────┐  └────────────────────┘  │ GET /           │   │
│  │  /api/v1/events   │                          └─────────────────┘   │
│  │                   │  ┌────────────────────┐                        │
│  │ GET /stream (SSE) │  │  /api/v1/ws        │                        │
│  └───────────────────┘  │                    │                        │
│                         │ WebSocket          │                        │
│                         └────────────────────┘                        │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Depends() Layer                               │   │
│  │  get_engine() → WorkflowEngine(SQLitePersistence)               │   │
│  │  get_config() → APIConfig                                       │   │
│  │  verify_api_key() → Optional auth                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   WorkflowEngine     │  ← Facade (ADR-002)
                    │   (facade.py)        │
                    │         │             │
                    │   SQLitePersistence   │  ← Port persistence (ADR-006)
                    │   (WAL mode)         │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   workflow.db         │
                    └──────────────────────┘
```

### Endpoints — mapping complet facade → REST

#### Convention REST

- **Collection** : pluriel (`/jobs`, `/runs`, `/executors`)
- **Ressource** : singulier avec identifiant (`/jobs/{name}`, `/runs/{run_id}`)
- **Action** : verbe en POST sur la ressource (`/runs/{id}/cancel`, `/runs/{id}/resume`)
- **Versioning** : préfixe `/api/v1/` — permet l'évolution sans casser les clients

#### Table de mapping

| Méthode | Endpoint | Facade | Response Schema | Status |
|---|---|---|---|---|
| `GET` | `/api/v1/jobs` | `list_jobs(limit, offset)` | `list[JobSummary]` | 200 |
| `GET` | `/api/v1/jobs/{name}` | `get_job(name)` | `JobDetail` | 200 / 404 |
| `GET` | `/api/v1/jobs/{name}/plan` | `get_execution_plan(job)` | `ExecutionPlanResponse` | 200 / 404 |
| `POST` | `/api/v1/jobs/{name}/validate` | `validate_job(job)` | `ValidationResponse` | 200 / 404 |
| `POST` | `/api/v1/runs` | `run_with_persistence(name, ctx)` | `RunDetail` | 201 / 404 / 409 |
| `GET` | `/api/v1/runs` | `list_job_runs(filters)` | `RunListResponse` | 200 |
| `GET` | `/api/v1/runs/{run_id}` | `get_job_run(run_id)` | `RunDetail` | 200 / 404 |
| `GET` | `/api/v1/runs/{run_id}/steps` | `get_job_run(id).step_runs` | `list[StepRunSchema]` | 200 / 404 |
| `POST` | `/api/v1/runs/{run_id}/cancel` | `cancel(run_id)` | `RunSummary` | 200 / 404 / 409 |
| `POST` | `/api/v1/runs/{run_id}/resume` | `resume(run_id, outputs)` | `RunDetail` | 200 / 404 / 409 |
| `GET` | `/api/v1/executors` | `list_executors()` | `list[ExecutorInfo]` | 200 |
| `GET` | `/api/v1/events/stream` | (SSE polling) | SSE stream | 200 |
| `WS` | `/api/v1/ws` | (WebSocket) | JSON messages | 101 |
| `GET` | `/api/v1/health` | `persistence.health_check()` | `HealthResponse` | 200 |

### Pagination, filtrage, tri

```
GET /api/v1/runs?page=1&page_size=20&job_name=etl&status=failed&sort=-started_at
```

| Paramètre | Type | Défaut | Contraintes | Description |
|---|---|---|---|---|
| `page` | `int` | `1` | `≥ 1` | Page courante |
| `page_size` | `int` | `20` | `1 – 100` | Éléments par page |
| `job_name` | `str \| None` | `None` | — | Filtre exact par nom de job |
| `status` | `str \| None` | `None` | Valeurs de `RunStatus` | Filtre par statut |
| `since` | `datetime \| None` | `None` | ISO 8601 | Runs créés après cette date |
| `sort` | `str` | `-created_at` | `created_at`, `-created_at`, `status`, `job_name` | Tri (préfixe `-` = descendant) |

Ces paramètres correspondent exactement aux arguments de `BasePersistence.list_job_runs()` et `BasePersistence.list_jobs()` :

```python
# Port persistence — déjà compatible pagination
def list_job_runs(
    self,
    job_name: str | None = None,
    status: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    since: datetime | None = None,
) -> list[JobRun]: ...
```

La conversion `page/page_size → limit/offset` est triviale : `offset = (page - 1) * page_size`.

### Schemas Pydantic — DTOs dédiés

Le domain model (`Job`, `Step`, `JobRun`, `StepRun`) utilise des `dataclass` stdlib avec des `handler: Callable` non sérialisables. L'API **ne doit pas** exposer directement ces modèles. Des **DTOs Pydantic** dédiés assurent :

- Validation automatique des entrées
- Sérialisation JSON propre (pas de `Callable`, pas de `datetime` brut)
- Documentation OpenAPI auto-générée avec types, exemples, descriptions
- Découplage entre l'API publique et le modèle interne

```python
# schemas/jobs.py
from pydantic import BaseModel, Field
from typing import Any

class StepSchema(BaseModel):
    """Représentation API d'un step."""
    name: str
    step_type: str
    depends_on: list[str] = Field(default_factory=list)
    retries: int = 0
    timeout: float | None = None
    executor_type: str = "local"
    executor_name: str | None = None

    model_config = {"json_schema_extra": {
        "example": {
            "name": "extract",
            "step_type": "function",
            "depends_on": [],
            "retries": 3,
            "timeout": 60.0,
            "executor_type": "local",
        }
    }}

class JobSummary(BaseModel):
    """Résumé d'un job pour les listes (léger, sans steps)."""
    name: str
    description: str = ""
    version: str | None = None
    step_count: int
    executor_type: str = "local"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)

class JobDetail(JobSummary):
    """Détail complet d'un job (avec steps et metadata)."""
    steps: list[StepSchema]
    timeout: float | None = None
    max_concurrent_steps: int = 10
    metadata: dict[str, Any] = Field(default_factory=dict)

class ExecutionPlanResponse(BaseModel):
    """Plan d'exécution d'un job (résultat de DAGResolver)."""
    job_name: str
    execution_order: list[str]
    parallel_groups: list[list[str]]
    critical_path: list[str]
    entry_points: list[str]
    exit_points: list[str]
    stats: dict[str, Any]
    validation_warnings: list[str]

class ValidationResponse(BaseModel):
    """Résultat de la validation d'un job."""
    job_name: str
    valid: bool
    warnings: list[str]
```

```python
# schemas/runs.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any

class RunCreate(BaseModel):
    """Corps de la requête POST /runs."""
    job_name: str
    context: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None

    model_config = {"json_schema_extra": {
        "example": {
            "job_name": "etl_pipeline",
            "context": {"env": "staging", "batch_size": 1000},
        }
    }}

class StepRunSchema(BaseModel):
    """Représentation API d'un step run."""
    step_name: str
    status: str
    executor_type: str = "local"
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    output: Any | None = None
    error: str | None = None

class RunSummary(BaseModel):
    """Résumé d'un run pour les listes (sans step_runs)."""
    job_run_id: str
    job_name: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    triggered_by: str = "api"

class RunDetail(RunSummary):
    """Détail complet d'un run (avec step_runs)."""
    job_version: str | None = None
    step_runs: list[StepRunSchema] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

class RunListResponse(BaseModel):
    """Réponse paginée pour GET /runs."""
    items: list[RunSummary]
    total: int
    page: int = 1
    page_size: int = 20
    has_next: bool = False

class ResumeRequest(BaseModel):
    """Corps de la requête POST /runs/{id}/resume."""
    outputs: dict[str, Any] = Field(default_factory=dict)
```

```python
# schemas/common.py
from pydantic import BaseModel
from datetime import datetime

class ErrorResponse(BaseModel):
    """Format d'erreur standardisé."""
    error: str          # Code machine (JOB_NOT_FOUND, VALIDATION_ERROR, etc.)
    message: str        # Message humain
    detail: dict | None = None

    model_config = {"json_schema_extra": {
        "example": {
            "error": "JOB_NOT_FOUND",
            "message": "Job 'etl_v2' not found",
            "detail": {"job_name": "etl_v2"},
        }
    }}

class HealthResponse(BaseModel):
    """Réponse du health check."""
    status: str = "healthy"
    version: str
    persistence_backend: str
    persistence_status: str
    timestamp: datetime
    stats: dict | None = None

class ExecutorInfo(BaseModel):
    """Information sur un executor enregistré."""
    name: str
    executor_type: str
```

### Gestion des erreurs — mapping exceptions domain → HTTP

La hiérarchie d'exceptions du projet (`exceptions.py`) se mappe naturellement sur les codes HTTP :

| Exception domain | Code HTTP | Code erreur | Quand |
|---|---|---|---|
| `JobNotFoundError` | **404** | `JOB_NOT_FOUND` | `get_job()` retourne `None` |
| `WorkflowValidationError` | **422** | `VALIDATION_ERROR` | `validate_job()`, `get_execution_plan()` |
| `DAGValidationError` | **422** | `DAG_VALIDATION_ERROR` | Cycle, step manquant dans le graphe |
| `WorkflowSuspended` | **409** | `WORKFLOW_SUSPENDED` | Step demande une suspension |
| `WorkflowCancelled` | **409** | `WORKFLOW_CANCELLED` | Run déjà annulé |
| `WorkflowTimeoutError` | **504** | `TIMEOUT` | Timeout global dépassé |
| `StepExecutionError` | **500** | `STEP_EXECUTION_ERROR` | Échec d'un step |
| `WorkflowFailed` | **500** | `WORKFLOW_FAILED` | Échec général du workflow |
| `PersistenceError` | **503** | `PERSISTENCE_ERROR` | SQLite verrouillé, fichier inaccessible |
| `WorkflowError` (base) | **500** | `INTERNAL_ERROR` | Toute exception non mappée |
| `ValueError` | **400** | `BAD_REQUEST` | Paramètres invalides |

```python
# errors.py
from fastapi import Request
from fastapi.responses import JSONResponse

from pyworkflow_engine.exceptions import (
    WorkflowError,
    WorkflowValidationError,
    DAGValidationError,
    WorkflowSuspended,
    WorkflowCancelled,
    WorkflowTimeoutError,
    StepExecutionError,
    WorkflowFailed,
)
from pyworkflow_engine.ports.persistence import (
    JobNotFoundError,
    PersistenceError,
)

EXCEPTION_MAP: dict[type[Exception], tuple[int, str]] = {
    JobNotFoundError:        (404, "JOB_NOT_FOUND"),
    WorkflowValidationError: (422, "VALIDATION_ERROR"),
    DAGValidationError:      (422, "DAG_VALIDATION_ERROR"),
    WorkflowSuspended:       (409, "WORKFLOW_SUSPENDED"),
    WorkflowCancelled:       (409, "WORKFLOW_CANCELLED"),
    WorkflowTimeoutError:    (504, "TIMEOUT"),
    StepExecutionError:      (500, "STEP_EXECUTION_ERROR"),
    WorkflowFailed:          (500, "WORKFLOW_FAILED"),
    PersistenceError:        (503, "PERSISTENCE_ERROR"),
    WorkflowError:           (500, "INTERNAL_ERROR"),
    ValueError:              (400, "BAD_REQUEST"),
}


async def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Traduit les exceptions domain en réponses JSON standardisées."""
    for exc_type, (status, code) in EXCEPTION_MAP.items():
        if isinstance(exc, exc_type):
            return JSONResponse(
                status_code=status,
                content={
                    "error": code,
                    "message": str(exc),
                    "detail": getattr(exc, "details", None),
                },
            )
    # Fallback — exception non mappée
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "detail": None,
        },
    )
```

**Note** : la recherche par `isinstance()` respecte l'héritage des exceptions. `DAGValidationError` (sous-classe de `WorkflowValidationError`) est testée avant `WorkflowValidationError` grâce à l'ordre du dict.

### Dependency Injection — `Depends()` layer

```python
# deps.py
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.api.config import APIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def get_engine(request: Request) -> WorkflowEngine:
    """Récupère l'instance WorkflowEngine depuis le state de l'app.

    L'engine est créée une seule fois au démarrage (lifespan)
    et partagée entre toutes les requêtes.
    """
    return request.app.state.engine


def get_config(request: Request) -> APIConfig:
    """Récupère la configuration API depuis le state."""
    return request.app.state.config


# ── Auth optionnel — API Key ────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> str | None:
    """Vérifie l'API Key si l'auth est activée.

    Si ``config.require_auth`` est ``False``, toute requête passe.
    Sinon, la clé ``X-API-Key`` doit correspondre à ``config.api_key``.
    """
    config: APIConfig = request.app.state.config
    if not config.require_auth:
        return None
    if api_key is None or api_key != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
```

### Middleware stack

```python
# middleware.py
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Injecte un X-Request-ID unique dans chaque requête et réponse."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Mesure le temps de traitement et l'ajoute en header X-Process-Time."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"
        return response
```

### Server-Sent Events (SSE) — suivi temps réel mono-directionnel

Le SSE est idéal pour le cas d'usage principal : **suivre un run en cours depuis un client léger** (`curl`, navigateur, script).

```python
# routes/events.py
import asyncio
from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse

from pyworkflow_engine.adapters.api.deps import get_engine
from pyworkflow_engine.facade import WorkflowEngine
from pyworkflow_engine.models.enums import TERMINAL_STATUSES

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/stream")
async def event_stream(
    run_id: str | None = Query(None, description="Filtre par run ID"),
    interval: float = Query(2.0, ge=0.5, le=30.0, description="Intervalle polling (s)"),
    engine: WorkflowEngine = Depends(get_engine),
) -> EventSourceResponse:
    """Stream SSE d'événements — suivi de run en temps réel.

    Si ``run_id`` est fourni, le stream se ferme automatiquement
    quand le run atteint un état terminal.
    """
    async def generate():
        while True:
            if run_id:
                job_run = engine.get_job_run(run_id)
                if job_run is None:
                    yield {"event": "error", "data": '{"error": "RUN_NOT_FOUND"}'}
                    return
                yield {
                    "event": "run_update",
                    "data": _run_to_json(job_run),
                }
                if job_run.status in TERMINAL_STATUSES:
                    yield {"event": "run_completed", "data": _run_to_json(job_run)}
                    return
            else:
                # Stream global — derniers runs modifiés
                runs = engine.list_job_runs(limit=10)
                yield {
                    "event": "runs_snapshot",
                    "data": _runs_to_json(runs),
                }
            await asyncio.sleep(interval)

    return EventSourceResponse(generate())
```

**Usage client** :

```bash
# Suivre un run spécifique
curl -N http://localhost:8000/api/v1/events/stream?run_id=abc123

# Stream global (dashboard léger)
curl -N http://localhost:8000/api/v1/events/stream?interval=5
```

### WebSocket — communication bidirectionnelle

Le WebSocket couvre les cas avancés : abonnement multi-run, commandes interactives.

```python
# routes/websocket.py
import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from pyworkflow_engine.adapters.api.deps import get_engine
from pyworkflow_engine.facade import WorkflowEngine
from pyworkflow_engine.models.enums import TERMINAL_STATUSES

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    engine: WorkflowEngine = Depends(get_engine),
) -> None:
    """WebSocket bidirectionnel — abonnements et commandes.

    Protocole JSON :
      Client → Server : {"command": "subscribe_run", "run_id": "..."}
      Client → Server : {"command": "run_job", "job_name": "...", "context": {...}}
      Server → Client : {"type": "run_update", "data": {...}}
      Server → Client : {"type": "run_started", "data": {"run_id": "..."}}
      Server → Client : {"type": "error", "message": "..."}
    """
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            command = msg.get("command")

            if command == "subscribe_run":
                run_id = msg["run_id"]
                while True:
                    job_run = engine.get_job_run(run_id)
                    if job_run is None:
                        await websocket.send_json(
                            {"type": "error", "message": f"Run {run_id} not found"}
                        )
                        break
                    await websocket.send_json({
                        "type": "run_update",
                        "data": _run_to_dict(job_run),
                    })
                    if job_run.status in TERMINAL_STATUSES:
                        break
                    await asyncio.sleep(1.0)

            elif command == "run_job":
                try:
                    job_run = engine.run_with_persistence(
                        msg["job_name"],
                        initial_context=msg.get("context"),
                    )
                    await websocket.send_json({
                        "type": "run_started",
                        "data": {"run_id": job_run.job_run_id, "status": job_run.status.value},
                    })
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown command: {command}"}
                )
    except WebSocketDisconnect:
        pass
```

### Authentification — API Key (Phase 1)

| Modèle | Complexité | Phase | Justification |
|---|---|---|---|
| **Aucune auth** | Nulle | Phase 0 (dev local) | Friction zéro pour le développement |
| **API Key** (`X-API-Key`) | Faible | ✅ **Phase 1** | Suffisant pour single-tenant, intégrations M2M |
| **JWT / OAuth2** | Élevée | ⏳ Phase 3+ | Multi-tenant, RBAC, SSO — via adapter dédié |

L'auth est **optionnelle par défaut** (`require_auth: bool = False`). Activée par configuration :

```bash
pyworkflow api serve --api-key "my-secret-key-42"
```

```bash
curl -H "X-API-Key: my-secret-key-42" http://localhost:8000/api/v1/jobs
```

### Intégration CLI (ADR-008)

La sous-commande `api` est ajoutée à la CLI :

```bash
# Lancer l'API avec SQLite par défaut
pyworkflow api serve --app myproject.workflows:engine

# Toutes les options
pyworkflow api serve \
    --app myproject.workflows:engine \
    --host 0.0.0.0 \
    --port 8000 \
    --db workflow.db \
    --reload \
    --cors-origins "http://localhost:3000" \
    --api-key "secret"
```

```python
# adapters/cli/commands/api.py
"""Sous-commande API — lance le serveur REST FastAPI."""

from __future__ import annotations

from typing import Optional

import typer

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.adapters.cli.loader import load_engine

app = typer.Typer(
    name="api",
    help="Lancer le serveur REST API (FastAPI + uvicorn).",
    no_args_is_help=False,
)


@app.command("serve")
@error_handler
def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Adresse d'écoute."),
    port: int = typer.Option(8000, "--port", "-p", help="Port du serveur."),
    db: str = typer.Option("workflow.db", "--db", help="Chemin du fichier SQLite."),
    reload: bool = typer.Option(False, "--reload", help="Hot-reload (développement)."),
    cors_origins: Optional[list[str]] = typer.Option(
        None, "--cors-origins", help="Origines CORS autorisées."
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="Clé API (active l'authentification)."
    ),
    workers: int = typer.Option(1, "--workers", "-w", help="Nombre de workers uvicorn."),
) -> None:
    """Lance le serveur REST API PyWorkflow."""
    try:
        from pyworkflow_engine.adapters.api.app import create_app
        from pyworkflow_engine.adapters.api.config import APIConfig
    except ImportError:
        from rich.console import Console
        Console(stderr=True).print(
            "[bold red]✗[/bold red] L'API nécessite 'fastapi' et 'uvicorn'. "
            "Installez avec : [cyan]pip install pyworkflow-engine[api][/cyan]"
        )
        raise typer.Exit(4)

    import uvicorn

    engine = load_engine(ctx.obj["app_path"])

    config = APIConfig(
        host=host,
        port=port,
        db_path=db,
        cors_origins=cors_origins or ["*"],
        api_key=api_key,
        require_auth=api_key is not None,
    )
    api_app = create_app(engine=engine, config=config)
    uvicorn.run(
        api_app,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )
```

Import conditionnel dans `adapters/cli/main.py` (même pattern ADR-008/009/010) :

```python
# API sub-command — optionnel, n'apparaît que si fastapi est installé
try:
    from pyworkflow_engine.adapters.cli.commands import api as api_commands
    app.add_typer(api_commands.app, name="api")
except ImportError:
    pass
```

### Convergence avec le GUI (ADR-010) — même processus FastAPI

L'avantage architectural majeur de FastAPI pour l'API est la **convergence avec NiceGUI** :

#### Phase 1 — Séparés

```bash
pyworkflow api serve --port 8000    # REST API
pyworkflow gui --port 8080          # Web UI
```

#### Phase 2 — Montés ensemble

```python
# convergence.py — API + GUI sur le même serveur
from pyworkflow_engine.adapters.api.app import create_app as create_api
from pyworkflow_engine.adapters.gui.app import WorkflowGUI

engine = WorkflowEngine(persistence=SQLitePersistence("workflow.db"))

# L'API est un sous-app FastAPI
api = create_api(engine=engine)

# NiceGUI est un FastAPI app — on peut monter l'API dessus
gui = WorkflowGUI(engine)
# gui._fastapi_app.mount("/api/v1", api)

# Résultat unifié :
# http://localhost:8080/           → GUI (NiceGUI)
# http://localhost:8080/api/v1/    → REST API (FastAPI)
# http://localhost:8080/api/v1/docs → Swagger UI
```

Cette convergence est **impossible** avec PyQt6, DearPyGui, ou Flet. C'est l'argument qui justifie le choix de NiceGUI (ADR-010) ET de FastAPI (ADR-011) comme un **duo cohérent**.

#### Phase 3 — CLI unified

```bash
# Tout-en-un (API + GUI)
pyworkflow serve --app myproject:engine --port 8080 --api --gui
```

### Flux de dépendances

```
pyworkflow api serve --app myproject:engine --db workflow.db
       │
       ▼
  main.py (Typer)
       │  ctx.obj["app_path"]
       ▼
  commands/api.py
       │  load_engine(app_path)
       │  SQLitePersistence(db_path)
       ▼
  api/app.py (create_app)
       │  lifespan: engine + config → app.state
       ▼
  routes/  ──→  deps.py ──→  WorkflowEngine
     │                              │
     ▼                              ▼
  schemas/              SQLitePersistence (WAL)
     │                              │
     ▼                              ▼
  Pydantic DTOs              workflow.db
```

L'API est un **adapter pur** : elle dépend uniquement de la facade `WorkflowEngine` (via `Depends(get_engine)`) et n'a aucune connaissance des ports internes, de l'engine, du runner, ou des autres adapters.

### Comparaison avec l'écosystème workflow

| Aspect | Airflow | Prefect | Dagster | Luigi | **PyWorkflow** |
|---|---|---|---|---|---|
| **Framework API** | Flask (legacy) | FastAPI | GraphQL (custom) | — | ✅ **FastAPI** |
| **Persistence** | PostgreSQL requis | PostgreSQL/Cloud | PostgreSQL requis | — | ✅ **SQLite (zero infra)** + pluggable |
| **OpenAPI / Swagger** | ❌ Partiel | ✅ | ❌ (GraphQL) | ❌ | ✅ **Natif** (`/docs`, `/redoc`) |
| **SSE** | ❌ | ⚠️ Cloud only | ❌ | ❌ | ✅ **Natif** |
| **WebSocket** | ❌ | ✅ Cloud | ✅ (subscriptions) | ❌ | ✅ **Natif** |
| **Auth** | RBAC complexe | Cloud-based | Custom | — | ✅ **API Key (simple)** → JWT (futur) |
| **Infra requise** | PostgreSQL + Redis + Webserver | Cloud / Server + DB | PostgreSQL + Dagit | Scheduler | **Aucune** — `pyworkflow api serve` |
| **Temps de setup** | ~30 min | ~10 min (cloud) | ~20 min | ~15 min | ✅ **~30 secondes** |
| **SDK auto-gen** | ⚠️ Partiel | ✅ (Python) | ❌ | ❌ | ✅ **OpenAPI → tout langage** |

**Avantage clé** : PyWorkflow est le seul orchestrateur offrant une **API REST + SSE + WebSocket sans infrastructure** (SQLite fichier local).

---

## Décision

### L'API vit dans `adapters/api/` — adapter complexe, FastAPI + SQLite par défaut

### Extra `pyproject.toml`

L'extra `fastapi` existe déjà :

```toml
[project.optional-dependencies]
fastapi = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]
```

Ajouter `sse-starlette` pour le support SSE :

```toml
api = ["fastapi>=0.100", "uvicorn[standard]>=0.20", "sse-starlette>=2.0"]
```

> **Note** : l'extra s'appelle `api` (et non `fastapi`) pour refléter son rôle d'adapter.
> L'ancien extra `fastapi` reste pour la rétrocompatibilité mais est marqué comme alias.

L'extra `all` doit inclure `api` :

```toml
all = [
    "pyworkflow-engine[django,fastapi,celery,sqlalchemy,postgresql,mysql,snowflake,streamlit,structlog,cli,tui,gui,api]",
]
```

### Structure cible

```
adapters/api/
├── __init__.py           ← re-export create_app(), lazy import guard (pattern ADR-008)
├── app.py                ← create_app() factory — lifespan, middleware, routers
├── config.py             ← APIConfig dataclass — host, port, db_path, cors, auth
├── deps.py               ← Depends() — get_engine, get_config, verify_api_key
├── errors.py             ← Exception handlers (domain exceptions → HTTP responses)
├── middleware.py          ← RequestID, Timing middleware ASGI
├── converters.py          ← Domain models (Job, JobRun) → Pydantic schemas
├── schemas/
│   ├── __init__.py       ← re-export all schemas
│   ├── jobs.py           ← JobSummary, JobDetail, StepSchema, ExecutionPlanResponse
│   ├── runs.py           ← RunCreate, RunSummary, RunDetail, RunListResponse, ResumeRequest
│   ├── executors.py      ← ExecutorInfo
│   └── common.py         ← ErrorResponse, HealthResponse, PaginationParams
├── routes/
│   ├── __init__.py       ← re-export all routers
│   ├── jobs.py           ← /api/v1/jobs — list, get, plan, validate
│   ├── runs.py           ← /api/v1/runs — create, list, get, steps, cancel, resume
│   ├── executors.py      ← /api/v1/executors — list
│   ├── events.py         ← /api/v1/events/stream — SSE
│   ├── websocket.py      ← /api/v1/ws — WebSocket
│   └── health.py         ← /api/v1/health — health check
└── server.py             ← run_server() helper (uvicorn launch, optionnel)
```

**18 fichiers** — cohérent avec la taille des adapters cli (13 fichiers) et gui (20 fichiers).

### Contrat de chaque fichier clé

#### `app.py` — Factory pattern

```python
"""Application factory — crée et configure l'app FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine

from pyworkflow_engine.adapters.api.config import APIConfig
from pyworkflow_engine.adapters.api.errors import register_exception_handlers
from pyworkflow_engine.adapters.api.middleware import RequestIDMiddleware, TimingMiddleware


def create_app(
    engine: WorkflowEngine,
    config: APIConfig | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Crée une application FastAPI configurée.

    Args:
        engine: Instance WorkflowEngine (avec persistence configurée).
        config: Configuration API. Valeurs par défaut si absent.

    Returns:
        Application FastAPI prête à être servie par uvicorn.

    Usage::

        from pyworkflow_engine.adapters.api import create_app
        app = create_app(engine)
        # uvicorn.run(app, host="0.0.0.0", port=8000)
    """
    config = config or APIConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup — stocke engine + config dans app.state
        app.state.engine = engine
        app.state.config = config
        yield
        # Shutdown — cleanup si nécessaire
        if hasattr(engine, "shutdown_executors"):
            engine.shutdown_executors()

    app = FastAPI(
        title="PyWorkflow Engine API",
        description="REST API for workflow orchestration — zero infrastructure",
        version="0.10.0",
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        **kwargs,
    )

    # Middleware (ordre = du plus externe au plus interne)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    from pyworkflow_engine.adapters.api.routes import (
        events,
        executors,
        health,
        jobs,
        runs,
        websocket,
    )

    app.include_router(jobs.router)
    app.include_router(runs.router)
    app.include_router(executors.router)
    app.include_router(events.router)
    app.include_router(websocket.router)
    app.include_router(health.router)

    return app
```

**Contrats** :
- **Factory pattern** (`create_app()`) — jamais de singleton global, testable avec `httpx.AsyncClient`
- L'engine est injectée — l'API ne crée **jamais** de `WorkflowEngine` ni de `SQLitePersistence`
- Le `lifespan` context manager (FastAPI moderne) remplace les deprecated `on_startup`/`on_shutdown`
- `docs_url="/api/v1/docs"` — Swagger UI accessible sous le préfixe versionnné

#### `config.py` — Configuration

```python
"""Configuration de l'API REST."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class APIConfig:
    """Configuration du serveur API.

    Tous les champs ont des valeurs par défaut sensées.
    Surchargeable via les flags CLI ``pyworkflow api serve``.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "workflow.db"
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    require_auth: bool = False
    api_key: str | None = None
    page_size_default: int = 20
    page_size_max: int = 100
    sse_interval: float = 2.0
    ws_interval: float = 1.0
```

#### `converters.py` — Domain → DTO

```python
"""Convertisseurs domain models → schemas Pydantic."""

from __future__ import annotations

from pyworkflow_engine.models import Job, JobRun
from pyworkflow_engine.models.run import StepRun
from pyworkflow_engine.adapters.api.schemas.jobs import JobSummary, JobDetail, StepSchema
from pyworkflow_engine.adapters.api.schemas.runs import RunSummary, RunDetail, StepRunSchema


def job_to_summary(job: Job) -> JobSummary:
    return JobSummary(
        name=job.name,
        description=job.description,
        version=job.version,
        step_count=len(job.steps),
        executor_type=job.default_executor.value,
        enabled=job.enabled,
        tags=list(job.tags) if job.tags else [],
    )


def job_to_detail(job: Job) -> JobDetail:
    return JobDetail(
        name=job.name,
        description=job.description,
        version=job.version,
        step_count=len(job.steps),
        executor_type=job.default_executor.value,
        enabled=job.enabled,
        tags=list(job.tags) if job.tags else [],
        steps=[
            StepSchema(
                name=s.name,
                step_type=s.step_type.value if s.step_type else "function",
                depends_on=list(s.depends_on) if s.depends_on else [],
                retries=s.retries,
                timeout=s.timeout.total_seconds() if s.timeout else None,
                executor_type=s.executor_type.value if s.executor_type else "local",
                executor_name=s.executor_name,
            )
            for s in job.steps
        ],
        timeout=job.timeout.total_seconds() if job.timeout else None,
        max_concurrent_steps=job.max_concurrent_steps,
        metadata=dict(job.metadata) if job.metadata else {},
    )


def run_to_summary(run: JobRun) -> RunSummary:
    duration_ms = None
    if run.start_time and run.end_time:
        duration_ms = int((run.end_time - run.start_time).total_seconds() * 1000)
    return RunSummary(
        job_run_id=run.job_run_id,
        job_name=run.job_name,
        status=run.status.value,
        started_at=run.start_time,
        completed_at=run.end_time,
        duration_ms=duration_ms,
    )


def run_to_detail(run: JobRun) -> RunDetail:
    duration_ms = None
    if run.start_time and run.end_time:
        duration_ms = int((run.end_time - run.start_time).total_seconds() * 1000)
    return RunDetail(
        job_run_id=run.job_run_id,
        job_name=run.job_name,
        job_version=run.job_version,
        status=run.status.value,
        started_at=run.start_time,
        completed_at=run.end_time,
        duration_ms=duration_ms,
        step_runs=[_step_run_to_schema(sr) for sr in run.step_runs],
        context=dict(run.input_data) if run.input_data else {},
        error=run.error if hasattr(run, "error") else None,
    )


def _step_run_to_schema(sr: StepRun) -> StepRunSchema:
    return StepRunSchema(
        step_name=sr.step_name,
        status=sr.status.value,
        executor_type=sr.executor_type.value if hasattr(sr, "executor_type") and sr.executor_type else "local",
        start_time=sr.start_time,
        end_time=sr.end_time,
        duration_ms=sr.duration_ms,
        retry_count=sr.retry_count if hasattr(sr, "retry_count") else 0,
        error=sr.error if hasattr(sr, "error") else None,
    )
```

**Contrat** : les convertisseurs sont des **fonctions pures** (pas de side effects, pas d'accès DB). Testables unitairement sans mock.

#### `__init__.py` — Re-export avec lazy import guard

```python
"""API adapter — serveur REST pour PyWorkflow Engine.

Installation : ``pip install pyworkflow-engine[api]``

Usage::

    from pyworkflow_engine.adapters.api import create_app
    from pyworkflow_engine import WorkflowEngine
    from pyworkflow_engine.adapters.persistence.sqlite import SQLitePersistence

    engine = WorkflowEngine(persistence=SQLitePersistence("workflow.db"))
    app = create_app(engine)

    # Lancer avec uvicorn
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""

from __future__ import annotations

__all__ = ["create_app"]


def __getattr__(name: str) -> object:
    if name == "create_app":
        try:
            from pyworkflow_engine.adapters.api.app import create_app
            return create_app
        except ImportError as exc:
            raise ImportError(
                "L'API adapter nécessite 'fastapi' et 'uvicorn'. "
                "Installez-le avec : pip install pyworkflow-engine[api]"
            ) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### Tests — stratégie complète

#### Pattern `httpx.AsyncClient` + `ASGITransport`

```python
# tests/unit/adapters/api/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient

from pyworkflow_engine import WorkflowEngine
from pyworkflow_engine.adapters.api.app import create_app
from pyworkflow_engine.adapters.persistence.memory import InMemoryPersistence
from pyworkflow_engine.models import Job
from pyworkflow_engine.models.step import Step
from pyworkflow_engine.models.enums import StepType


@pytest.fixture
def engine() -> WorkflowEngine:
    """Engine avec InMemoryPersistence (rapide, isolé)."""
    persistence = InMemoryPersistence()
    eng = WorkflowEngine(persistence=persistence)

    # Job de test
    def extract(ctx):
        return {"data": [1, 2, 3]}

    job = Job(
        name="test-etl",
        description="ETL pipeline de test",
        steps=[Step(name="extract", step_type=StepType.FUNCTION, handler=extract)],
        version="1.0.0",
    )
    eng.save_job(job)
    return eng


@pytest.fixture
async def client(engine: WorkflowEngine) -> AsyncClient:
    """Client HTTP async pour tester l'API."""
    app = create_app(engine=engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

#### Exemples de tests

```python
# tests/unit/adapters/api/test_jobs_routes.py
import pytest

@pytest.mark.anyio
async def test_list_jobs(client):
    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "test-etl"
    assert data[0]["step_count"] == 1

@pytest.mark.anyio
async def test_get_job_detail(client):
    response = await client.get("/api/v1/jobs/test-etl")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-etl"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["name"] == "extract"

@pytest.mark.anyio
async def test_get_job_not_found(client):
    response = await client.get("/api/v1/jobs/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "JOB_NOT_FOUND"

@pytest.mark.anyio
async def test_get_execution_plan(client):
    response = await client.get("/api/v1/jobs/test-etl/plan")
    assert response.status_code == 200
    data = response.json()
    assert data["job_name"] == "test-etl"
    assert "execution_order" in data
    assert "parallel_groups" in data
```

```python
# tests/unit/adapters/api/test_runs_routes.py
import pytest

@pytest.mark.anyio
async def test_create_run(client):
    response = await client.post("/api/v1/runs", json={
        "job_name": "test-etl",
        "context": {"env": "test"},
    })
    assert response.status_code == 201
    data = response.json()
    assert data["job_name"] == "test-etl"
    assert data["status"] in ("success", "running", "pending")
    assert "job_run_id" in data
    assert len(data["step_runs"]) == 1

@pytest.mark.anyio
async def test_create_run_job_not_found(client):
    response = await client.post("/api/v1/runs", json={
        "job_name": "nonexistent",
    })
    assert response.status_code == 404

@pytest.mark.anyio
async def test_list_runs_pagination(client):
    # Créer 25 runs
    for _ in range(25):
        await client.post("/api/v1/runs", json={"job_name": "test-etl"})

    response = await client.get("/api/v1/runs?page=1&page_size=10")
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["has_next"] is True

    # Page 3 (5 éléments restants)
    response = await client.get("/api/v1/runs?page=3&page_size=10")
    data = response.json()
    assert len(data["items"]) == 5
    assert data["has_next"] is False

@pytest.mark.anyio
async def test_filter_runs_by_status(client):
    await client.post("/api/v1/runs", json={"job_name": "test-etl"})
    response = await client.get("/api/v1/runs?status=success")
    data = response.json()
    assert all(r["status"] == "success" for r in data["items"])
```

```python
# tests/unit/adapters/api/test_health.py
import pytest

@pytest.mark.anyio
async def test_health_check(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "persistence_backend" in data

# tests/unit/adapters/api/test_auth.py
import pytest
from httpx import ASGITransport, AsyncClient
from pyworkflow_engine.adapters.api.app import create_app
from pyworkflow_engine.adapters.api.config import APIConfig

@pytest.mark.anyio
async def test_auth_required_rejects_no_key(engine):
    config = APIConfig(require_auth=True, api_key="secret-42")
    app = create_app(engine=engine, config=config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/jobs")
        assert response.status_code == 401

@pytest.mark.anyio
async def test_auth_passes_with_valid_key(engine):
    config = APIConfig(require_auth=True, api_key="secret-42")
    app = create_app(engine=engine, config=config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/jobs",
            headers={"X-API-Key": "secret-42"},
        )
        assert response.status_code == 200
```

---

## Plan d'implémentation

### Phase 1 — Scaffold, CRUD, Health (v0.10.0-alpha)

| Tâche | Fichier | Effort |
|---|---|---|
| `app.py` — factory `create_app()`, lifespan, middleware | `adapters/api/app.py` | 2h |
| `config.py` — `APIConfig` dataclass | `adapters/api/config.py` | 30min |
| `deps.py` — `get_engine`, `get_config` | `adapters/api/deps.py` | 30min |
| `errors.py` — exception handlers domain → HTTP | `adapters/api/errors.py` | 1h30 |
| `middleware.py` — RequestID, Timing | `adapters/api/middleware.py` | 1h |
| `converters.py` — domain → Pydantic | `adapters/api/converters.py` | 1h30 |
| `schemas/jobs.py` — DTOs jobs | `adapters/api/schemas/jobs.py` | 1h |
| `schemas/runs.py` — DTOs runs | `adapters/api/schemas/runs.py` | 1h |
| `schemas/common.py` — Error, Health, Pagination | `adapters/api/schemas/common.py` | 30min |
| `routes/jobs.py` — GET /jobs, GET /jobs/{name}, GET /plan | `adapters/api/routes/jobs.py` | 2h |
| `routes/runs.py` — POST /runs, GET /runs, GET /runs/{id} | `adapters/api/routes/runs.py` | 2h30 |
| `routes/health.py` — GET /health | `adapters/api/routes/health.py` | 30min |
| `__init__.py` — lazy import guard | `adapters/api/__init__.py` | 15min |
| `commands/api.py` — intégration CLI | `adapters/cli/commands/api.py` | 45min |
| Tests unitaires (jobs, runs, health, errors) | `tests/unit/adapters/api/` | 3h |
| `pyproject.toml` — extra `api`, update `all` | `pyproject.toml` | 10min |

**Total Phase 1 : ~18h30**

### Phase 2 — Actions, Executors, Pagination avancée, Auth (v0.10.0-beta)

| Tâche | Fichier | Effort |
|---|---|---|
| `routes/runs.py` — cancel, resume, steps | `adapters/api/routes/runs.py` | 2h |
| Pagination complète + filtres + tri | `routes/runs.py`, `schemas/common.py` | 2h |
| `routes/executors.py` — list executors | `adapters/api/routes/executors.py` | 1h |
| `schemas/executors.py` — DTOs | `adapters/api/schemas/executors.py` | 30min |
| Auth API Key (`deps.py`, config) | `adapters/api/deps.py` | 1h |
| CORS configurble | `adapters/api/app.py` | 30min |
| Tests (cancel, resume, auth, pagination, filtres) | `tests/unit/adapters/api/` | 3h |

**Total Phase 2 : ~10h**

### Phase 3 — SSE, WebSocket, OpenAPI polish, convergence (v0.10.0)

| Tâche | Fichier | Effort |
|---|---|---|
| `routes/events.py` — SSE stream | `adapters/api/routes/events.py` | 2h |
| `routes/websocket.py` — WebSocket bidirectionnel | `adapters/api/routes/websocket.py` | 2h30 |
| OpenAPI enrichi (descriptions, exemples, tags) | `schemas/*.py`, `routes/*.py` | 1h30 |
| Convergence GUI mount (proof of concept) | `adapters/api/app.py` | 2h |
| `server.py` — helper uvicorn standalone | `adapters/api/server.py` | 30min |
| Tests SSE, WebSocket | `tests/unit/adapters/api/` | 2h30 |
| Documentation | `docs/integrations/api.md` | 1h30 |

**Total Phase 3 : ~12h30**

### Effort total estimé : ~41h

---

## Alternatives considérées

### Alternative A — Flask / Flask-RESTX

Utiliser Flask, le framework historique de l'écosystème Python.

**Pour** :
- Communauté massive, stabilité éprouvée (15+ ans)
- Extrêmement simple pour les endpoints basiques

**Contre** :
- **WSGI** — pas d'async natif, blocking I/O
- Pas de validation Pydantic native — nécessite flask-smorest ou marshmallow
- Pas d'OpenAPI auto-gen native — extensions requises
- Pas de `Depends()` — injection de dépendance manuelle
- **Incompatible avec NiceGUI** (ASGI vs WSGI)
- Performances ~3× inférieures à FastAPI
- Pas de SSE/WebSocket natif

**Verdict** : ❌ Rejetée — WSGI incompatible avec la stack ASGI du projet (NiceGUI, async), et inférieur sur tous les critères sauf la maturité.

### Alternative B — Django REST Framework

Utiliser Django + DRF, le framework full-stack.

**Pour** :
- ORM intégré, admin auto, auth/permissions robustes
- Écosystème middleware le plus riche de Python

**Contre** :
- **~30 MB** d'installation (Django complet) — surdimensionné pour une API de ~14 endpoints
- ORM Django incompatible avec notre persistence hexagonale (on a `BasePersistence`, pas `models.Model`)
- WSGI par défaut (async views récent mais pas ASGI-first)
- Pas de Pydantic natif — serializers DRF sont un système parallèle
- **Incompatible avec NiceGUI** et la philosophie "zéro framework imposé" du projet

**Verdict** : ❌ Rejetée — trop lourd, ORM incompatible avec l'architecture hexagonale, et casse la philosophie du projet.

### Alternative C — Litestar

Utiliser Litestar (ex-Starlite), le concurrent moderne de FastAPI.

**Pour** :
- Performances légèrement supérieures à FastAPI (~18k vs ~15k req/s)
- Dependency injection plus puissante (injection scope-aware)
- API plus opinionated (moins de boilerplate sur certains patterns)
- Pydantic v2 natif

**Contre** :
- Communauté ~5× plus petite (16k vs 80k ★ GitHub)
- **Aucune synergie NiceGUI** — NiceGUI est FastAPI, pas Litestar
- Moins de middleware ASGI compatibles
- Moins de ressources d'apprentissage
- Le delta de performance (~20%) est marginal pour notre use case (SQLite est le bottleneck, pas le framework)

**Verdict** : ❌ Rejetée — excellent framework mais l'incompatibilité NiceGUI et la communauté plus petite sont rédhibitoires.

### Alternative D — GraphQL (Strawberry / Ariadne)

Remplacer REST par GraphQL pour une flexibilité de requêtes.

**Pour** :
- Requêtes flexibles (le client demande exactement ce qu'il veut)
- Subscriptions pour le temps réel (alternative au SSE/WebSocket)
- Dagster utilise GraphQL avec succès

**Contre** :
- Complexité accrue (schema, resolvers, dataloader)
- Pas d'OpenAPI (GraphQL a son propre système d'introspection)
- Overkill pour ~14 endpoints avec un modèle simple (Job → Steps → Runs → StepRuns)
- Courbe d'apprentissage pour les consommateurs (curl + GraphQL = verbeux)
- Les intégrations M2M (Terraform, curl, scripts) préfèrent REST

**Verdict** : ❌ Rejetée — GraphQL est puissant mais surdimensionné pour notre périmètre. REST + SSE/WebSocket couvre 100% des besoins.

### Alternative E — PostgreSQL par défaut (pas SQLite)

Imposer PostgreSQL comme persistence par défaut de l'API.

**Pour** :
- Écritures concurrentes illimitées
- Pub/sub natif (`LISTEN/NOTIFY`) pour le push temps réel
- Requêtes JSON avancées (`jsonb`)
- Multi-instance (HA, réplication)

**Contre** :
- **Infrastructure requise** — briserait la promesse "zéro infra" du projet
- `pip install pyworkflow-engine[api]` ne suffit plus — il faut un serveur PostgreSQL
- L'installation prend 15-30 minutes au lieu de 30 secondes
- 80% des utilisateurs n'ont pas besoin de PostgreSQL pour un workflow engine mono-instance
- Le chemin de migration SQLite → PostgreSQL est déjà prévu (architecture hexagonale)

**Verdict** : ❌ Rejetée comme défaut — PostgreSQL reste disponible via `SQLAlchemyPersistence` pour les déploiements multi-instance. SQLite est le défaut "zéro infra".

### Alternative F — gRPC au lieu de REST

Utiliser gRPC pour les communications M2M.

**Pour** :
- Performances supérieures (Protocol Buffers, HTTP/2)
- Typage fort (fichiers .proto)
- Streaming bidirectionnel natif
- Temporal utilise gRPC

**Contre** :
- Pas de Swagger UI / exploration interactive
- Pas compatible curl (binaire, pas JSON)
- Complexité tooling (protoc, codegen)
- Pas de synergie NiceGUI
- Overkill pour le volume de trafic attendu (~100 req/s max)

**Verdict** : ❌ Rejetée — gRPC est excellent pour le M2M haute performance mais inadapté à un projet qui valorise la simplicité et l'accessibilité.

### Alternative G — Ne rien faire (CLI + GUI suffisent)

Ne pas implémenter d'API REST.

**Pour** : Zéro effort.

**Contre** :
- Aucune intégration M2M possible
- Pas de webhook, pas de SDK client, pas de monitoring externe
- La GUI NiceGUI (ADR-010) a déjà FastAPI sous le capot — ne pas l'exposer serait un gaspillage
- Tous les concurrents (Airflow, Prefect, Dagster, Temporal) offrent une API REST
- L'extra `fastapi` est déjà déclaré dans `pyproject.toml` — dette de promesse

**Verdict** : ❌ Rejetée — l'API REST est une attente standard, et FastAPI est déjà dans les dépendances du projet.

---

## Conséquences

### Positives

- **Intégrations M2M universelles** — `curl`, Terraform, Ansible, GitHub Actions, scripts Python/Go/Rust
- **OpenAPI native** — Swagger UI (`/api/v1/docs`) et ReDoc (`/api/v1/redoc`) auto-générés, SDK client auto-gen possible
- **Zéro infrastructure** — `pyworkflow api serve` avec SQLite = 30 secondes de setup
- **SSE + WebSocket** — suivi temps réel sans polling HTTP agressif
- **Cohérence stack** — même FastAPI que NiceGUI (ADR-010), même `Depends()`, même middleware
- **Convergence GUI + API** — possibilité de monter les deux sur le même serveur
- **Architecture hexagonale respectée** — l'API est un adapter pur, dépend uniquement de la facade
- **Tests simples** — `httpx.AsyncClient` + `ASGITransport` = tests rapides sans serveur
- **Migration persistence transparente** — SQLite → PostgreSQL sans toucher l'API

### Négatives

- **SQLite mono-writer** — limite les déploiements haute charge (>500 écritures/s)
- **SSE/WebSocket par polling** — pas de push natif en Phase 1 (nécessite EventBus en Phase 2)
- **Auth basique** — API Key seul n'offre pas de RBAC ni de multi-tenant
- **Dépendance FastAPI** — le framework est jeune vs Flask/Django (5 ans vs 15-20 ans)
- **Pas de background tasks** — `run_with_persistence()` est bloquant ; les runs longs bloquent la requête HTTP

### Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| SQLite lock contention sous charge | Moyenne | Moyen | `busy_timeout=5000`, retry applicatif, bascule PostgreSQL documéntée |
| Run long bloque la requête POST | Élevée | Moyen | Phase 2 : background task (asyncio, Celery), réponse 202 Accepted |
| FastAPI breaking change | Faible | Moyen | Pin `fastapi>=0.100,<1.0`, Starlette stable |
| SSE non supporté par certains proxies | Faible | Faible | WebSocket en alternative, polling fallback |
| Conflit de port API / GUI | Faible | Faible | Ports configurables, convergence en Phase 2 |
| Scaling multi-instance impossible avec SQLite | Moyenne | Élevé | Documenté comme limitation connue ; migration PostgreSQL = changer 1 ligne |

### Risque spécifique — runs longs et requêtes bloquantes

`POST /api/v1/runs` appelle `engine.run_with_persistence()` qui est **synchrone et bloquant**. Un run de 30 minutes bloque un worker uvicorn pendant 30 minutes.

| Phase | Solution | Complexité |
|---|---|---|
| Phase 1 | Limiter aux runs courts (<60s), documenter la limitation | Nulle |
| Phase 2 | `asyncio.to_thread()` pour libérer l'event loop | Faible |
| Phase 3 | Background worker + réponse `202 Accepted` + SSE/WebSocket pour le suivi | Moyenne |
| Phase 4 | Celery adapter (ADR-007) pour les runs distribués | Élevée |

La réponse Phase 2 est simple :

```python
@router.post("/api/v1/runs", status_code=201)
async def create_run(body: RunCreate, engine = Depends(get_engine)):
    import asyncio
    job_run = await asyncio.to_thread(
        engine.run_with_persistence,
        body.job_name,
        initial_context=body.context,
        run_id=body.run_id,
    )
    return run_to_detail(job_run)
```

---

## Références

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [FastAPI GitHub — 80k+ stars](https://github.com/tiangolo/fastapi)
- [Starlette ASGI framework](https://www.starlette.io/)
- [Pydantic v2 documentation](https://docs.pydantic.dev/latest/)
- [uvicorn ASGI server](https://www.uvicorn.org/)
- [sse-starlette — SSE for Starlette/FastAPI](https://github.com/sysid/sse-starlette)
- [httpx — async HTTP client for testing](https://www.python-httpx.org/)
- [SQLite WAL mode documentation](https://www.sqlite.org/wal.html)
- [SQLite PRAGMA optimization](https://www.sqlite.org/pragma.html)
- [Litestar framework](https://litestar.dev/) — alternative considérée
- [NiceGUI + FastAPI integration](https://nicegui.io/documentation/section_server_sge)
- ADR-006 — Architecture hexagonale
- ADR-007 — Adapter complexe vs simple (règle de placement)
- ADR-008 — CLI Adapter Typer + Rich
- ADR-010 — GUI Adapter NiceGUI (convergence FastAPI)
