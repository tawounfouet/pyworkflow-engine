# ADR-016 — Plan maître d'intégration : AI Engine + Pipeline + PyConnectors Bridge

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-016                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | 🔵 Proposition                      |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-013 (ai_engine fusion), ADR-014 (Pipeline + @pipeline/@stage), ADR-015 (plan unifié AI+Pipeline) |
| **Supersède** | ADR-015 (plan d'implémentation unifié) |
| **Version cible** | v0.8.0                         |
| **Fusionne** | ADR-013 + ADR-014 + ADR-015 + intégration pyconnectors |

---

## Motivation

ADR-015 fusionne ADR-013 (intégration `ai_engine`) et ADR-014 (modèle `Pipeline` + `@pipeline`/`@stage`) en un plan d'implémentation unique. Cependant, elle **omet l'intégration de `pyconnectors`**, le troisième package frère du monorepo.

`pyconnectors` (v0.2.0) est un **framework universel de connecteurs** vers des services externes (databases, APIs, storage, email, social, payment, auth…). Là où `ai_engine` partage ~10 doublons structurels avec `pyworkflow_engine` et nécessite une **fusion**, `pyconnectors` est **entièrement orthogonal** — zéro doublon, zéro chevauchement de modèles. Il ne doit donc **pas être fusionné**, mais rendu **accessible** depuis les workflows via un **pont adapter** (bridge pattern).

Cette ADR-016 **supersède ADR-015** en reprenant intégralement son plan (6 phases) et en ajoutant :

1. **L'analyse de `pyconnectors`** : pourquoi autonome, pourquoi un bridge
2. **Le `ConnectorStep` bridge** : `adapters/steps/connector_step.py`
3. **Le `StepType.CONNECTOR`** : nouveau type de step
4. **La phase 4 enrichie** : intégration du bridge dans la phase adapters
5. **Les scénarios combinés** Pipeline + AI + Connector

---

## Analyse de `pyconnectors` — pourquoi un bridge et pas une fusion

### Comparaison structurelle

| Concept | `pyworkflow_engine` | `pyconnectors` | Doublon ? |
|---|---|---|---|
| Modèle d'exécution | `StepRun` (tracé, statuts, retry) | `ConnectorResult` (success/error/duration) | ❌ Non — granularités différentes |
| Registre | — | `ConnectorRegistry` (class-based, auto-discovery) | ❌ Non — concept absent côté workflow |
| Factory | — | `ConnectorFactory` (create, execute, test) | ❌ Non — concept absent côté workflow |
| Configuration | `config/settings.py` (stdlib) | `ConnectorConfig` (dataclass, auth, params) | ❌ Non — domaines différents |
| Logging | `logging/` (workflow-centric) | `ConnectorLogger` (ring-buffer, JSONL) | ❌ Non — spécialisé connecteurs |
| Exceptions | `exceptions.py` (workflow) | `exceptions.py` (connecteurs) | ❌ Non — hiérarchies distinctes |
| Hooks | — | `BaseConnector._hooks` (pre/post/error) | ❌ Non — concept absent côté workflow |
| Décorateur | `@step`, `@job` | `@connector` | ❌ Non — registre vs builder |

**Verdict : zéro doublon structurel.** `pyconnectors` est un package **orthogonal** qui gère l'accès aux services externes. `pyworkflow_engine` orchestre des étapes.

### Pourquoi NE PAS fusionner

| Critère | Fusion | Bridge (retenu) |
|---|---|---|
| Doublons à éliminer | 0 | 0 |
| Cohérence modèles | Aucun bénéfice — modèles incompatibles | Le bridge adapte `ConnectorResult` → `StepRun` |
| Versioning | Couplage forcé | Indépendant — `pyconnectors` publiable seul |
| Réutilisabilité | `pyconnectors` enfermé dans `pyworkflow_engine` | `pyconnectors` réutilisable dans tout projet Python |
| Complexité | Import de 50+ connecteurs dans le core | 1 seul adapter bridge |
| Dépendances | Explosion (boto3, psycopg, pymysql, stripe…) | `pyconnectors` reste optionnel |

### Le bridge pattern : `ConnectorStep`

Le pont est un **adapter** unique dans `adapters/steps/connector_step.py` qui :

1. Accepte un nom de connecteur + sa configuration + les arguments d'exécution
2. Délègue à `ConnectorFactory.create()` → `connector.safe_execute()`
3. Traduit `ConnectorResult` en données compatibles avec le contexte `StepRun`
4. Gère les erreurs `pyconnectors` → exceptions `pyworkflow_engine`

```python
# adapters/steps/connector_step.py
"""Bridge adapter : exécute un connecteur pyconnectors comme step de workflow."""

from __future__ import annotations

import time
from typing import Any

from pyworkflow_engine.exceptions import StepExecutionError


def execute_connector(
    connector_name: str,
    connector_config: dict[str, Any] | None = None,
    **execute_kwargs: Any,
) -> dict[str, Any]:
    """
    Exécute un connecteur pyconnectors et retourne un dict compatible
    avec le contexte de workflow.

    Lazy import de pyconnectors — le core ne dépend jamais de pyconnectors
    au niveau import statique.

    Args:
        connector_name: Nom du connecteur dans le registre (ex: "database.postgresql").
        connector_config: Configuration du connecteur (dict passé à ConnectorConfig).
        **execute_kwargs: Arguments passés à connector.execute().

    Returns:
        Dict avec les clés :
        - ``_connector_name``: nom du connecteur utilisé
        - ``_connector_success``: bool
        - ``_connector_duration``: float (secondes)
        - ``_connector_error``: str | None
        - ``data``: résultat de l'exécution (ou None si erreur)

    Raises:
        StepExecutionError: Si pyconnectors n'est pas installé ou si l'exécution échoue.
    """
    try:
        from pyconnectors import ConnectorFactory, ConnectorConfig
    except ImportError as e:
        raise StepExecutionError(
            f"pyconnectors is not installed. "
            f"Install with: pip install pyconnectors\n"
            f"Original error: {e}"
        )

    config = ConnectorConfig.from_dict(connector_config or {})
    connector = ConnectorFactory.create(connector_name, config=config)
    result = connector.safe_execute(**execute_kwargs)

    output = {
        "_connector_name": connector_name,
        "_connector_success": result.success,
        "_connector_duration": result.duration,
        "_connector_error": result.error,
        "data": result.data,
    }

    if not result.success:
        raise StepExecutionError(
            f"Connector '{connector_name}' failed: {result.error}",
            details=output,
        )

    return output
```

Usage dans un workflow :

```python
from pyworkflow_engine.decorators import step, job, pipeline, stage
from pyworkflow_engine.models.enums import StepType

@step(name="fetch_countries", step_type=StepType.CONNECTOR)
def fetch_countries(source_url: str = "") -> dict:
    """Récupère les données via un connecteur REST."""
    from pyworkflow_engine.adapters.steps.connector_step import execute_connector

    return execute_connector(
        connector_name="http.rest",
        connector_config={"params": {"base_url": source_url}},
        url="/v3.1/all",
        method="GET",
    )

@step(name="write_to_db", step_type=StepType.CONNECTOR)
def write_staging(records: list = None) -> dict:
    """Écrit les données via un connecteur PostgreSQL."""
    from pyworkflow_engine.adapters.steps.connector_step import execute_connector

    return execute_connector(
        connector_name="database.postgresql",
        connector_config={"params": {"dsn": "postgresql://localhost/dwh"}},
        query="INSERT INTO staging.countries VALUES (%s)",
        params=records,
    )
```

---

## Rappel : analyse de cohérence ADR-013 ↔ ADR-014

> Reprise intégrale d'ADR-015 — les 7 frictions et leurs résolutions.

### Ce qui s'intègre bien naturellement

| Aspect | Cohérence | Détails |
|---|---|---|
| **Hiérarchie Step → Job → Pipeline** | ✅ Parfait | ADR-014 ajoute le 3ᵉ niveau. ADR-013 ajoute l'IA transversalement. |
| **Modèle runtime** | ✅ Parfait | `PipelineRun` → `StageRun` → `JobRun` → `StepRun`. Champs IA optionnels sur `StepRun`/`JobRun`. |
| **Decorators** | ✅ Parfait | `@step` → `@job` → `@pipeline` hiérarchie symétrique. Steps IA = `@step` avec `step_type=StepType.LLM_CALL`. |
| **Storage** | ✅ Compatible | ADR-014 : tables pipeline. ADR-013 : tables IA. Pas de collision. |
| **Facade** | ✅ Compatible | `run_pipeline()` (014) + méthodes IA (013) indépendantes. |
| **`pyproject.toml`** | ✅ Compatible | ADR-014 zéro dep. ADR-013 extras `[ai]`. |

### Les 7 frictions et résolutions

#### Friction 1 : `StepType` fusionné en une seule passe

ADR-013 fusionne `StepType` workflow + ai_engine. ADR-014 y fait référence. **ADR-016 ajoute** `StepType.CONNECTOR` pour le bridge pyconnectors.

```python
class StepType(Enum):
    """Types de steps — classiques, IA, et connecteurs."""

    # ── Workflow classique (existant) ──
    FUNCTION = "function"
    SUBPROCESS = "subprocess"
    HTTP_REQUEST = "http_request"
    SQL_QUERY = "sql_query"
    HUMAN_TASK = "human_task"
    EXTERNAL_TASK = "external_task"
    SUB_WORKFLOW = "sub_workflow"

    # ── IA (depuis ai_engine) — ADR-013 ──
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AI_DECISION = "ai_decision"
    SKILL_EXECUTION = "skill_execution"

    # ── Connecteurs (bridge pyconnectors) — ADR-016 ──
    CONNECTOR = "connector"
```

#### Friction 2 : `RunStatus` — superset, aucune modification

`RunStatus` de `pyworkflow_engine` contient déjà `CANCELLED`, `WAITING_HUMAN`, `WAITING_EXTERNAL`, `SUSPENDED`, `TIMEOUT`. Il est un **superset** de `ExecutionStatus` d'`ai_engine`. Aucune modification nécessaire.

```python
# Dans models/ai/types.py
ExecutionStatus = RunStatus  # Alias rétrocompatibilité
```

#### Friction 3 : Contexte — propagation et préfixes

Données IA préfixées `_ai_`. **ADR-016** : les données connecteur ne sont plus propagées comme clés `_connector_*` brutes dans le contexte mais structurées dans un `ConnectorOutcome` typé sur `StepRun.connector_outcome`. Les données métier (résultat de l'exécution) restent dans le contexte classique.

```python
# Contexte workflow — données métier libres
context = {
    "raw_data": [...],
    "kpi_results": {...},
    "_ai_classification": {"content": "...", "token_usage": {...}},
    "_ai_agent_id": "agent-uuid",
}

# Métadonnées connecteur — structurées dans StepRun
step_run.connector_outcome = ConnectorOutcome(
    connector_name="database.postgresql",
    connector_type="database",
    success=True,
    duration_seconds=0.234,
    records_affected=1500,
)
```

#### Friction 4 : `dataclass` vs Pydantic — cohabitation

| Couche | Technologie | Raison |
|---|---|---|
| `models/*.py` + `models/pipeline*.py` | `dataclass` (stdlib) | Zéro dépendance pour le core |
| `models/ai/*.py` | Pydantic `BaseModel` | Validation riche, compat LLM providers |

**Contrainte** : `models/` (dataclass) **ne doit jamais** importer depuis `models/ai/`. L'inverse est autorisé.

`pyconnectors` n'impacte pas cette règle — ses modèles (`ConnectorConfig`, `ConnectorResult`) restent **dans son propre package**. Le bridge fait un lazy import.

#### Friction 5 : `TriggerType.AI`

Ajouté dans l'enum. Pas de conflit avec `Pipeline.schedule` (cron string consommée par `ScheduleTrigger`).

```python
class TriggerType(Enum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    SIGNAL = "signal"
    WEBHOOK = "webhook"
    FILE_WATCHER = "file_watcher"
    AI = "ai"  # 🆕 ADR-013
```

#### Friction 6 : EventBus promu

`ai_engine/events/` promu dans `events/` top-level. Peut émettre des événements `pipeline.*`, `connector.*`.

#### Friction 7 : `BaseStorage` — trois extensions

ADR-014 : `save_pipeline()`, `save_pipeline_run()`, etc.
ADR-013 : `save_agent()`, `save_provider()`, etc.
**ADR-016** : aucune extension storage — les connecteurs sont stateless, pas de persistance supplémentaire. Le `StepRun` enregistré par le workflow trace le résultat du connecteur via son champ structuré `connector_outcome: ConnectorOutcome`.

---

## Analyse pyconnectors ↔ workflow : zéro friction

| Point de contact | Analyse | Résolution |
|---|---|---|
| Import | `pyconnectors` est un package externe optionnel | Lazy import dans `connector_step.py` |
| Exceptions | `PyConnectorsError` ≠ `WorkflowError` | Le bridge attrape et re-lève en `StepExecutionError` |
| Résultat | `ConnectorResult` (dataclass) ≠ `StepRun` | Le bridge traduit `ConnectorResult` → `ConnectorOutcome` (dataclass workflow) |
| Configuration | `ConnectorConfig` ≠ `Step.config` | Le bridge passe `Step.config` à `ConnectorConfig.from_dict()` |
| Logging | `ConnectorLogger` (ring-buffer) ≠ `logging/` | Indépendant — `pyconnectors` log en interne, workflow log le `StepRun` |
| Hooks | `BaseConnector._hooks` | Transparents — le bridge appelle `safe_execute()` qui gère les hooks |
| Auth | `build_auth_headers()` | Géré par `pyconnectors` en interne, transparent pour le workflow |
| Registry | `ConnectorRegistry` auto-discovery | Le bridge appelle `ConnectorFactory.create()` qui auto-load |

---

## Modèles de données connector (vue workflow)

### Constat : le bridge actuel est opaque

Le bridge `connector_step.py` tel que décrit plus haut retourne un `dict[str, Any]` brut avec des clés `_connector_*`. Ce choix initial est fonctionnel mais pose 3 problèmes :

| Problème | Impact |
|---|---|
| **Pas de typage** | `mypy` / IDE ne peuvent pas vérifier les clés du dict |
| **Pas de documentation structurelle** | Les développeurs doivent deviner les clés disponibles |
| **Pas de lien design-time → runtime** | Le `Step` ne décrit pas *quel* connecteur il utilise ; le `StepRun` ne structure pas le résultat |

### Solution : deux dataclasses légères dans `models/connector.py`

On ajoute **deux modèles** dans le core workflow — en `dataclass` stdlib (zéro dépendance), cohérents avec `models/step.py` et `models/run.py` :

| Modèle | Rôle | Phase | Stocké dans |
|---|---|---|---|
| `ConnectorRef` | **Design-time** — *quel* connecteur utiliser | Phase 1 | `Step.connector_ref` |
| `ConnectorOutcome` | **Runtime** — *qu'a retourné* le connecteur | Phase 4 | `StepRun.connector_outcome` |

#### Principes de conception

- **Pas de duplication** : ces modèles ne copient PAS `ConnectorConfig` / `ConnectorResult` de `pyconnectors`. Ils décrivent le connecteur **du point de vue du workflow**.
- **Pas d'import** : `models/connector.py` n'importe **jamais** depuis `pyconnectors`. La traduction `ConnectorResult → ConnectorOutcome` se fait dans le bridge (lazy import).
- **`dataclass` stdlib** : cohérent avec toute la couche `models/` (règle Friction 4).
- **`frozen=True`** pour `ConnectorRef` (design-time immuable), mutable pour `ConnectorOutcome` (runtime).
- **Sérialisation** : `to_dict()` / `from_dict()` comme tous les modèles existants.

#### `ConnectorRef` — design-time

```python
# models/connector.py
"""Modèles connector — vue workflow (design-time + runtime)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pyworkflow_engine.models.run import generate_id, utc_now


@dataclass(frozen=True)
class ConnectorRef:
    """Référence à un connecteur pyconnectors dans un Step.

    Décrit *quel* connecteur utiliser et *avec quelle configuration*,
    sans importer ni dépendre de pyconnectors.

    Attributes:
        connector_name: Nom du connecteur dans le registre pyconnectors
            (ex: ``"database.postgresql"``, ``"http.rest"``, ``"social.slack"``).
        connector_type: Catégorie du connecteur (ex: ``"database"``, ``"http"``,
            ``"storage"``, ``"social"``, ``"email"``). Optionnel — déduit du nom
            si non fourni.
        config: Configuration à passer à ``ConnectorConfig.from_dict()``.
            Ne contient jamais de secrets en clair — utiliser des références
            ``${ENV_VAR}`` ou un secret manager.
        action: Méthode à appeler sur le connecteur (défaut: ``"execute"``).
        description: Description lisible pour la documentation / GUI.
    """

    connector_name: str
    connector_type: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    action: str = "execute"
    description: str = ""

    def __post_init__(self) -> None:
        if not self.connector_type and "." in self.connector_name:
            object.__setattr__(
                self, "connector_type", self.connector_name.split(".")[0]
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_name": self.connector_name,
            "connector_type": self.connector_type,
            "config": self.config,
            "action": self.action,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectorRef:
        return cls(
            connector_name=data["connector_name"],
            connector_type=data.get("connector_type", ""),
            config=data.get("config", {}),
            action=data.get("action", "execute"),
            description=data.get("description", ""),
        )
```

Usage design-time :

```python
pg_ref = ConnectorRef(
    connector_name="database.postgresql",
    config={"params": {"dsn": "${POSTGRES_DSN}"}},
    description="Extraction des utilisateurs actifs",
)
# → connector_type auto-déduit à "database"

@step(name="extract_users", step_type=StepType.CONNECTOR)
def extract_users() -> dict:
    ...

# Step.connector_ref = pg_ref  (champ optionnel ajouté sur Step)
```

#### `ConnectorOutcome` — runtime

```python
@dataclass
class ConnectorOutcome:
    """Résultat de l'exécution d'un connecteur dans un StepRun.

    Capture les métadonnées standardisées retournées par le bridge
    ``connector_step.py``. Stocké dans ``StepRun.connector_outcome``.

    Attributes:
        id: Identifiant unique de cette exécution connecteur.
        connector_name: Nom du connecteur utilisé.
        connector_type: Catégorie (``"database"``, ``"http"``, etc.).
        success: ``True`` si le connecteur a retourné sans erreur.
        duration_seconds: Durée d'exécution en secondes.
        error: Message d'erreur si ``success=False``.
        records_affected: Nombre de lignes/objets affectés (optionnel).
        data_summary: Résumé des données retournées (pas les données brutes
            — celles-ci restent dans le contexte du workflow).
        metadata: Métadonnées libres retournées par le connecteur.
        executed_at: Timestamp d'exécution.
    """

    connector_name: str = ""
    connector_type: str = ""
    success: bool = False
    duration_seconds: float = 0.0
    error: str = ""
    records_affected: int | None = None
    data_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=generate_id)
    executed_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "connector_name": self.connector_name,
            "connector_type": self.connector_type,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "records_affected": self.records_affected,
            "data_summary": self.data_summary,
            "metadata": self.metadata,
            "executed_at": self.executed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectorOutcome:
        executed_at = data.get("executed_at")
        if isinstance(executed_at, str):
            executed_at = datetime.fromisoformat(executed_at)
        return cls(
            id=data.get("id", generate_id()),
            connector_name=data.get("connector_name", ""),
            connector_type=data.get("connector_type", ""),
            success=data.get("success", False),
            duration_seconds=data.get("duration_seconds", 0.0),
            error=data.get("error", ""),
            records_affected=data.get("records_affected"),
            data_summary=data.get("data_summary", {}),
            metadata=data.get("metadata", {}),
            executed_at=executed_at or utc_now(),
        )
```

### Impact sur les modèles existants

#### `Step` (design-time) — ajout de `connector_ref: ConnectorRef | None`

```python
@dataclass(frozen=True)
class Step:
    # ...champs existants...
    step_type: StepType = StepType.FUNCTION

    # 🆕 ADR-016 — référence connecteur (uniquement si step_type == CONNECTOR)
    connector_ref: ConnectorRef | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {  # ...sérialisation existante... }
        if self.connector_ref is not None:
            d["connector_ref"] = self.connector_ref.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        connector_ref_data = data.get("connector_ref")
        connector_ref = (
            ConnectorRef.from_dict(connector_ref_data)
            if connector_ref_data
            else None
        )
        return cls(..., connector_ref=connector_ref)
```

#### `StepRun` (runtime) — ajout de `connector_outcome: ConnectorOutcome | None`

```python
@dataclass
class StepRun:
    # ...champs existants...

    # 🆕 ADR-016 — résultat connecteur (uniquement si step_type == CONNECTOR)
    connector_outcome: ConnectorOutcome | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {  # ...sérialisation existante... }
        if self.connector_outcome is not None:
            d["connector_outcome"] = self.connector_outcome.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepRun:
        outcome_data = data.get("connector_outcome")
        connector_outcome = (
            ConnectorOutcome.from_dict(outcome_data)
            if outcome_data
            else None
        )
        return cls(..., connector_outcome=connector_outcome)
```

### Bridge mis à jour : retourne un `ConnectorOutcome` typé

Le bridge `connector_step.py` est mis à jour pour accepter un `ConnectorRef` et retourner un `ConnectorOutcome` au lieu d'un dict brut :

```python
# adapters/steps/connector_step.py — version mise à jour

from pyworkflow_engine.models.connector import ConnectorOutcome, ConnectorRef


def execute_connector(
    ref: ConnectorRef,
    **execute_kwargs: Any,
) -> ConnectorOutcome:
    """
    Exécute un connecteur pyconnectors et retourne un ConnectorOutcome typé.

    Le bridge :
    1. Lazy-importe pyconnectors
    2. Crée le connecteur via ConnectorFactory
    3. Appelle l'action demandée (ref.action)
    4. Traduit ConnectorResult → ConnectorOutcome
    5. Lève StepExecutionError si échec
    """
    try:
        from pyconnectors import ConnectorFactory, ConnectorConfig
    except ImportError as e:
        raise StepExecutionError(...) from e

    config = ConnectorConfig.from_dict(ref.config)
    connector = ConnectorFactory.create(ref.connector_name, config=config)

    start = time.perf_counter()
    result = getattr(connector, ref.action)(**execute_kwargs)
    duration = time.perf_counter() - start

    return ConnectorOutcome(
        connector_name=ref.connector_name,
        connector_type=ref.connector_type,
        success=result.success,
        duration_seconds=round(duration, 4),
        error=str(result.error) if result.error else "",
        records_affected=result.metadata.get("records_affected"),
        data_summary=_build_summary(result.data),
        metadata=result.metadata or {},
    )
```

### Diagramme design-time → runtime

```
              Design-time                          Runtime
         ┌────────────────────┐            ┌───────────────────────┐
         │       Step         │            │       StepRun         │
         │                    │            │                       │
         │ step_type=CONNECTOR│  execute   │ status=SUCCESS        │
         │ connector_ref ─────┼──────────→ │ connector_outcome ────┤
         │   ├ name: "db.pg"  │            │   ├ success: true     │
         │   ├ type: "database"│           │   ├ duration: 1.23s   │
         │   ├ config: {...}  │            │   ├ records: 1500     │
         │   └ action: "exec" │            │   └ data_summary: {}  │
         └────────────────────┘            └───────────────────────┘
                    │                                 ▲
                    │ pyconnectors                    │
                    │ (lazy import)                   │
                    ▼                                 │
         ┌────────────────────┐                      │
         │ ConnectorFactory   │                      │
         │  .create()         │──→ ConnectorResult ──┘
         │  .execute()        │    (traduit par bridge)
         └────────────────────┘
```

### Exports `models/__init__.py`

```python
from .connector import ConnectorOutcome, ConnectorRef

__all__ = [
    # ...exports existants...
    # Connector (bridge pyconnectors) — ADR-016
    "ConnectorRef",
    "ConnectorOutcome",
]
```

---

## Architecture cible unifiée

### Structure des dossiers (delta vs ADR-015)

Les ajouts ADR-016 sont marqués `🔶`.

```
src/pyworkflow_engine/
│
├── models/                              # Modèles de domaine
│   ├── __init__.py                      # Re-exports publics
│   ├── enums.py                         # ✅ Existant — enrichi (StepType IA + CONNECTOR + TriggerType.AI)
│   ├── job.py                           # ✅ Existant
│   ├── step.py                          # ✅ Existant — étendu (connector_ref: ConnectorRef | None)
│   ├── run.py                           # ✅ Existant — étendu (champs IA + connector_outcome)
│   ├── connector.py                     # 🔶 ADR-016 — ConnectorRef (design-time), ConnectorOutcome (runtime)
│   ├── pipeline.py                      # 🆕 ADR-014 — Pipeline, PipelineStage
│   ├── pipeline_run.py                  # 🆕 ADR-014 — PipelineRun, StageRun
│   │
│   └── ai/                              # 🆕 ADR-013 — Modèles IA (Pydantic)
│       ├── __init__.py
│       ├── types.py                     # Enums exclusifs IA (ProviderType, AgentRole, ...)
│       ├── agent.py                     # Agent, AgentConfig
│       ├── provider.py                  # LLMProviderConfig, ProviderSettings
│       ├── conversation.py              # Conversation
│       ├── message.py                   # Message, ToolCall, ToolResult, TokenUsage
│       ├── tool.py                      # ToolDefinition
│       ├── skill.py                     # Skill, AgentSkillAssignment
│       ├── memory.py                    # AgentMemory
│       ├── knowledge.py                 # KnowledgeSource, Document, Chunk
│       └── graph.py                     # Graph, GraphNode, GraphEdge
│
├── ports/                               # Interfaces (contrats abstraits)
│   ├── __init__.py
│   ├── executor.py                      # ✅ Existant
│   ├── storage.py                       # ✅ Existant → étendu (Pipeline + IA)
│   ├── trigger.py                       # ✅ Existant
│   │
│   └── ai/                              # 🆕 ADR-013 — Ports IA
│       ├── __init__.py
│       ├── llm.py                       # BaseLLMClient
│       ├── tool.py                      # BaseTool
│       ├── skill.py                     # BaseSkill
│       └── storage.py                   # BaseAIStorage
│
├── adapters/                            # Implémentations concrètes
│   ├── api/                             # ✅ Existant
│   ├── celery/                          # ✅ Existant
│   ├── cli/                             # ✅ Existant → enrichi (commandes pipeline + IA)
│   ├── executors/                       # ✅ Existant
│   ├── gui/                             # ✅ Existant → enrichi (page Pipelines)
│   ├── mcp/                             # ✅ Existant
│   ├── snowflake/                       # ✅ Existant
│   ├── sqlalchemy/                      # ✅ Existant
│   ├── storage/                         # ✅ Existant → enrichi (tables pipeline + IA)
│   ├── structlog/                       # ✅ Existant
│   ├── triggers/                        # ✅ Existant
│   ├── tui/                             # ✅ Existant
│   │
│   ├── steps/                           # 🔶 ADR-016 — Bridge adapters
│   │   ├── __init__.py
│   │   └── connector_step.py            # 🔶 Bridge pyconnectors → workflow step
│   │
│   └── ai/                              # 🆕 ADR-013 — Adapters IA
│       ├── __init__.py
│       ├── llm/                         # Factory LLM (openai, anthropic, ollama, ...)
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── factory.py
│       │   ├── openai.py
│       │   ├── anthropic.py
│       │   ├── ollama.py
│       │   ├── gemini.py
│       │   └── groq.py
│       ├── tools/                       # Tools concrets
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── registry.py
│       │   ├── executor.py
│       │   ├── calculator.py
│       │   ├── web_search.py
│       │   └── http_client.py
│       ├── skills/                      # Skills
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── registry.py
│       ├── storage/                     # Storage entités IA
│       │   ├── __init__.py
│       │   ├── memory.py
│       │   └── sqlite.py
│       ├── triggers/                    # Triggers IA
│       │   ├── __init__.py
│       │   └── ai_trigger.py
│       ├── steps/                       # Steps IA
│       │   ├── __init__.py
│       │   └── ai_step.py
│       ├── executors/                   # Executors IA
│       │   ├── __init__.py
│       │   └── agent_executor.py
│       ├── bridges/                     # Ponts workflow ↔ IA
│       │   ├── __init__.py
│       │   └── job_as_tool.py
│       ├── django/                      # Adapter Django IA
│       │   ├── __init__.py
│       │   ├── orm_models.py
│       │   ├── admin.py
│       │   ├── serializers.py
│       │   └── views.py
│       └── fastapi/                     # Adapter FastAPI IA
│           ├── __init__.py
│           ├── routers/
│           ├── schemas.py
│           └── dependencies.py
│
├── engine/                              # Orchestration / logique métier
│   ├── __init__.py
│   ├── context.py                       # ✅ Existant
│   ├── dag.py                           # ✅ Existant
│   ├── parallel_runner.py               # ✅ Existant
│   ├── retry.py                         # ✅ Existant
│   ├── runner.py                        # ✅ Existant
│   ├── suspension.py                    # ✅ Existant
│   ├── pipeline_runner.py               # 🆕 ADR-014 — PipelineRunner
│   │
│   └── ai/                              # 🆕 ADR-013 — Services IA
│       ├── __init__.py
│       ├── agent_service.py
│       ├── conversation_service.py
│       └── skill_registry.py
│
├── events/                              # 🆕 ADR-013 — EventBus unifié
│   ├── __init__.py
│   ├── bus.py                           # EventBus (thread-safe, sync/async)
│   └── events.py                        # Événements workflow + pipeline + IA + connector
│
├── config/                              # ✅ Existant
│   ├── __init__.py
│   ├── base.py
│   ├── engine.py
│   ├── executor.py
│   ├── logging.py
│   ├── settings.py
│   ├── storage.py
│   └── ai.py                           # 🆕 ADR-013 — AISettings
│
├── decorators/                          # ✅ Existant
│   ├── __init__.py
│   ├── step_decorator.py               # ✅ @step
│   ├── job_decorator.py                # ✅ @job
│   └── pipeline_decorator.py           # 🆕 ADR-014 — @pipeline, @stage
│
├── logging/                             # ✅ Existant
├── exceptions.py                        # ✅ Existant → enrichi (exceptions IA)
├── facade.py                            # ✅ Existant → enrichi (run_pipeline + API IA)
└── py.typed
```

### Packages autonomes du monorepo

```
pyworkflow-engine/
├── src/pyworkflow_engine/         ← Package principal (publié PyPI)
├── ai_engine/                     ← 🗄️ Archivé après fusion (Phase 6)
├── pyconnectors/                  ← ✅ RESTE AUTONOME (publié indépendamment)
│   ├── __init__.py                   v0.2.0
│   ├── base.py                       BaseConnector (ABC)
│   ├── config.py                     ConnectorConfig
│   ├── factory.py                    ConnectorFactory
│   ├── registry.py                   ConnectorRegistry, @connector
│   ├── result.py                     ConnectorResult
│   ├── connectors/                   50+ connecteurs (database, http, storage, social, ...)
│   ├── contrib/                      django.py, fastapi.py
│   └── cli/                          Typer CLI
├── pipelines/                     ← Pipelines applicatives (réécriture @pipeline)
└── jobs/                          ← Jobs applicatifs
```

### Diagramme de composition complet

```
Pipeline("weekly-countries-to-dwh")                    ← ADR-014
│   triggered_by: TriggerType.SCHEDULE
│   schedule: "0 1 * * 0"
│
├─ PipelineStage("ingestion")                          ← ADR-014
│  └─ Job("ingestion-restcountries")
│     ├─ Step("fetch_raw", CONNECTOR)                  ← 🔶 ADR-016 (ConnectorStep bridge)
│     ├─ Step("validate_raw", FUNCTION)                ← classique
│     └─ Step("ai_classify_sources", LLM_CALL)         ← 🧠 ADR-013
│
├─ PipelineStage("transformation")                     ← ADR-014
│  └─ Job("transform-stg-restcountries")
│     ├─ Step("clean_types", FUNCTION)                  ← classique
│     └─ Step("write_staging", CONNECTOR)               ← 🔶 ADR-016 (ConnectorStep bridge)
│
├─ PipelineStage("enrichment")                         ← ADR-014
│  └─ Job("ai-enrich-countries")
│     └─ Step("ai_enrich", LLM_CALL)                   ← 🧠 ADR-013
│
└─ PipelineStage("quality", continue_on_failure=True)  ← ADR-014
   └─ Job("quality-check")
      └─ Step("check_completeness", FUNCTION)           ← classique
```

Runtime :

```
PipelineRun
├─ StageRun("ingestion")
│  └─ JobRun("ingestion-restcountries")
│     ├─ StepRun("fetch_raw")
│     │  └─ connector_outcome: ConnectorOutcome(
│     │       connector_name="http.rest", connector_type="http",
│     │       success=true, duration_seconds=1.234,
│     │       records_affected=250, data_summary={type: "list", count: 250})
│     ├─ StepRun("validate_raw")
│     └─ StepRun("ai_classify_sources")
│        ├─ agent_id: "analyst-uuid"
│        └─ token_usage: {prompt: 450, completion: 120}
├─ StageRun("transformation")
│  └─ JobRun → StepRun(s) dont write_staging avec connector_outcome
├─ StageRun("enrichment")
│  └─ JobRun → StepRun(s) avec token_usage
└─ StageRun("quality")
   └─ JobRun → StepRun(s)
```

---

## Scénarios d'usage combinés

### Scénario 1 : Pipeline classique avec étape IA (ADR-013 + ADR-014)

```python
from pyworkflow_engine.decorators import step, job, stage, pipeline
from pyworkflow_engine.models.enums import StepType

@step(name="extract", timeout=30)
def extract_data(source: str = "api") -> dict:
    return {"records": fetch_from_api(source)}

@step(name="ai_classify", step_type=StepType.LLM_CALL)
def ai_classify_anomalies(records: list = None) -> dict:
    """Step IA — classifie les anomalies via un agent LLM."""
    return {"prompt": f"Classify anomalies: {records}"}

@step(name="load")
def load_to_warehouse(records: list = None, ai_result: dict = None) -> dict:
    return {"loaded": len(records or [])}

@job(name="etl-with-ai")
def etl_job():
    data = extract_data()
    classified = ai_classify_anomalies(records=data["records"])
    load_to_warehouse(records=data["records"], ai_result=classified)

@stage(job=etl_job)
def etl_stage():
    """ETL avec classification IA."""

@pipeline(
    name="daily-etl-with-ai",
    schedule="0 2 * * *",
    owner="data-team@company.com",
)
def daily_pipeline():
    etl_stage()

# Exécution
p = daily_pipeline.build()
engine = WorkflowEngine()
pipeline_run = engine.run_pipeline(p, initial_context={"date": "2026-04-12"})
```

### Scénario 2 : Pipeline avec bridge connecteur (ADR-016)

```python
from pyworkflow_engine.decorators import step, job, stage, pipeline
from pyworkflow_engine.models.enums import StepType
from pyworkflow_engine.adapters.steps.connector_step import execute_connector

@step(name="fetch_countries", step_type=StepType.CONNECTOR)
def fetch_countries() -> dict:
    """Récupère les pays via le connecteur REST de pyconnectors."""
    return execute_connector(
        connector_name="http.rest",
        connector_config={
            "params": {"base_url": "https://restcountries.com"}
        },
        url="/v3.1/all",
        method="GET",
    )

@step(name="write_staging", step_type=StepType.CONNECTOR)
def write_to_postgres(data: list = None) -> dict:
    """Écrit en base via le connecteur PostgreSQL de pyconnectors."""
    return execute_connector(
        connector_name="database.postgresql",
        connector_config={
            "params": {"dsn": "postgresql://localhost/dwh"}
        },
        query="INSERT INTO staging.countries SELECT * FROM jsonb_array_elements(%s)",
        params=(data,),
    )

@step(name="notify_slack", step_type=StepType.CONNECTOR)
def notify_slack(loaded_count: int = 0) -> dict:
    """Notifie Slack via le connecteur social de pyconnectors."""
    return execute_connector(
        connector_name="social.slack",
        connector_config={
            "params": {"webhook_url": "https://hooks.slack.com/..."}
        },
        text=f"✅ Pipeline terminée : {loaded_count} pays chargés.",
    )

@job(name="countries-etl")
def countries_etl():
    raw = fetch_countries()
    result = write_to_postgres(data=raw["data"])
    notify_slack(loaded_count=len(raw.get("data", [])))

@stage(job=countries_etl)
def etl_stage():
    pass

@pipeline(name="weekly-countries-to-dwh", schedule="0 1 * * 0")
def weekly_pipeline():
    etl_stage()
```

### Scénario 3 : Pipeline hybride — connecteur + IA + classique (les trois ADR)

```python
@step(name="fetch_data", step_type=StepType.CONNECTOR)
def fetch_data() -> dict:
    """ADR-016 : connecteur REST."""
    return execute_connector("http.rest", {"params": {"base_url": "..."}}, url="/data")

@step(name="ai_analyze", step_type=StepType.LLM_CALL)
def ai_analyze(data: dict = None) -> dict:
    """ADR-013 : analyse IA."""
    return {"prompt": f"Analyze quality: {data}"}

@step(name="transform")
def transform(data: dict = None, analysis: dict = None) -> dict:
    """Classique : transformation Python."""
    return {"cleaned": apply_rules(data, analysis)}

@step(name="write_results", step_type=StepType.CONNECTOR)
def write_results(cleaned: dict = None) -> dict:
    """ADR-016 : connecteur PostgreSQL."""
    return execute_connector("database.postgresql", {"params": {"dsn": "..."}},
                            query="INSERT INTO results ...", params=cleaned)

@step(name="ai_summary", step_type=StepType.LLM_CALL)
def ai_summary(results: dict = None) -> dict:
    """ADR-013 : résumé IA exécutif."""
    return {"prompt": f"Summarize: {results}"}

@step(name="notify", step_type=StepType.CONNECTOR)
def notify(summary: str = "") -> dict:
    """ADR-016 : notification Slack."""
    return execute_connector("social.slack", {"params": {"webhook_url": "..."}},
                            text=summary)

@job(name="full-hybrid-etl")
def hybrid_etl():
    raw = fetch_data()
    analysis = ai_analyze(data=raw["data"])
    cleaned = transform(data=raw["data"], analysis=analysis)
    stored = write_results(cleaned=cleaned["cleaned"])
    summary = ai_summary(results=stored)
    notify(summary=summary.get("_ai_result", "Done"))

@stage(job=hybrid_etl)
def main_stage():
    pass

@pipeline(name="hybrid-pipeline", schedule="0 3 * * *", tags=["hybrid", "ai", "etl"])
def hybrid_pipeline():
    main_stage()
```

### Scénario 4 : Agent IA orchestre des connecteurs (ADR-013 + ADR-016)

```python
from pyworkflow_engine.adapters.ai.bridges import JobAsTool
from pyworkflow_engine.adapters.steps.connector_step import execute_connector

# L'agent peut utiliser des connecteurs comme outils
class ConnectorTool(BaseTool):
    """Tool IA qui délègue à un connecteur pyconnectors."""

    def __init__(self, connector_name: str, connector_config: dict):
        self.connector_name = connector_name
        self.connector_config = connector_config

    def execute(self, **kwargs) -> dict:
        return execute_connector(self.connector_name, self.connector_config, **kwargs)

# Enregistrer des connecteurs comme outils pour l'agent
db_tool = ConnectorTool("database.postgresql", {"params": {"dsn": "..."}})
agent_service.register_tool(supervisor_agent, db_tool)

# L'agent décide quand et comment utiliser les connecteurs
response = agent_service.chat(
    agent=supervisor_agent,
    user_message="Query the database for the latest country statistics.",
)
```

---

## Dépendances optionnelles (`pyproject.toml`)

```toml
[project]
name = "pyworkflow-engine"
version = "0.8.0"

# ⚠️ ZÉRO dépendance obligatoire pour le core
dependencies = []

[project.optional-dependencies]
# ── Existants (inchangés) ──
django = ["django>=4.2", "djangorestframework>=3.14"]
fastapi = ["fastapi>=0.100", "uvicorn>=0.20"]
celery = ["celery>=5.3", "redis>=5.0"]
sqlalchemy = ["sqlalchemy>=2.0"]
cli = ["typer>=0.9", "rich>=13.0"]
tui = ["textual>=1.0", "rich>=13.0"]
gui = ["nicegui>=2.0"]
structlog = ["structlog>=24.0"]
api = ["fastapi>=0.100", "uvicorn[standard]>=0.20", "sse-starlette>=2.0"]
dataplatform = ["duckdb>=1.0", "pyarrow>=15.0"]

# ── IA — ADR-013 ──
pydantic = ["pydantic>=2.0", "pydantic-settings>=2.0"]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.30"]
ollama = ["ollama>=0.2"]
gemini = ["google-generativeai>=0.5"]
groq = ["groq>=0.5"]
llm = [
    "pyworkflow-engine[pydantic]",
    "pyworkflow-engine[openai]",
    "pyworkflow-engine[anthropic]",
    "pyworkflow-engine[ollama]",
    "pyworkflow-engine[gemini]",
    "pyworkflow-engine[groq]",
]
ai-tools = ["duckduckgo-search>=5.0", "httpx>=0.27"]
ai = ["pyworkflow-engine[llm,ai-tools]"]

# ── Connecteurs — ADR-016 ──
connectors = ["pyconnectors>=0.2.0"]

# ── Combinaisons ──
ai-django = ["pyworkflow-engine[ai,django]"]
ai-fastapi = ["pyworkflow-engine[ai,fastapi]"]
full-pipeline = ["pyworkflow-engine[ai,connectors]"]

# ── Dev ──
dev = ["pytest>=8.0", "pytest-cov>=4.0", "ruff>=0.4", "mypy>=1.10"]

# ── Tout ──
all = [
    "pyworkflow-engine[ai,connectors,django,fastapi,celery,sqlalchemy,cli,tui,gui,api,structlog,dataplatform]",
]
```

---

## Plan d'implémentation — 7 phases ordonnées

> Les phases 1-6 reprennent ADR-015. La **Phase 4 est enrichie** avec le bridge pyconnectors, et une **Phase 4b** est ajoutée pour la validation du bridge.

### Phase 1 — Fondations : enums unifiés et modèle Pipeline (semaine 1)

> **Objectif** : poser les bases sans casser l'existant.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 1.1 | Ajouter `StepType.LLM_CALL`, `.TOOL_CALL`, `.TOOL_RESULT`, `.AI_DECISION`, `.SKILL_EXECUTION` | `models/enums.py` | 013 |
| 1.2 | Ajouter `StepType.CONNECTOR` | `models/enums.py` | **016** |
| 1.3 | Ajouter `TriggerType.AI` | `models/enums.py` | 013 |
| 1.4 | Créer `models/connector.py` (`ConnectorRef`, `ConnectorOutcome`) | `models/connector.py` 🆕 | **016** |
| 1.5 | Ajouter `connector_ref: ConnectorRef | None` sur `Step` | `models/step.py` | **016** |
| 1.6 | Ajouter `connector_outcome: ConnectorOutcome | None` sur `StepRun` | `models/run.py` | **016** |
| 1.7 | Créer `models/pipeline.py` (`Pipeline`, `PipelineStage`) | `models/pipeline.py` 🆕 | 014 |
| 1.8 | Créer `models/pipeline_run.py` (`PipelineRun`, `StageRun`) | `models/pipeline_run.py` 🆕 | 014 |
| 1.9 | Exporter dans `models/__init__.py` (`ConnectorRef`, `ConnectorOutcome`, Pipeline, …) | `models/__init__.py` | 014+**016** |
| 1.10 | Tests unitaires | `tests/unit/test_pipeline_model.py`, `tests/unit/test_connector_model.py` 🆕 | 014+**016** |

**Validations** : `pytest tests/unit/`, `mypy`, `ruff`. Aucun test existant ne casse.

### Phase 2 — Decorators Pipeline + EventBus (semaine 2)

> **Objectif** : API déclarative `@pipeline`/`@stage` + EventBus unifié.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 2.1 | Créer `decorators/pipeline_decorator.py` (`@pipeline`, `@stage`, `PipelineBuilder`, `StageSpec`) | `decorators/pipeline_decorator.py` 🆕 | 014 |
| 2.2 | Exporter dans `decorators/__init__.py` | `decorators/__init__.py` | 014 |
| 2.3 | Promouvoir `ai_engine/events/` dans `events/` (EventBus unifié) | `events/bus.py`, `events/events.py` 🆕 | 013 |
| 2.4 | Ajouter événements Pipeline + Connector (`pipeline.started`, `connector.executed`, etc.) | `events/events.py` | 014+013+**016** |
| 2.5 | Tests | `tests/unit/test_pipeline_decorator.py`, `tests/unit/test_event_bus.py` 🆕 | 014+013 |

### Phase 3 — Modèles IA + config (semaine 3)

> **Objectif** : migrer tous les modèles `ai_engine` dans `models/ai/`.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 3.1 | Créer `models/ai/types.py` (enums IA + alias `ExecutionStatus = RunStatus`) | `models/ai/types.py` 🆕 | 013 |
| 3.2 | Copier et adapter `ai_engine/models/*.py` → `models/ai/*.py` | `models/ai/*.py` 🆕 | 013 |
| 3.3 | Ajouter champs IA optionnels sur `StepRun` (`agent_id`, `tool_id`, `token_usage`) | `models/run.py` | 013 |
| 3.4 | Créer `config/ai.py` (`AISettings`) | `config/ai.py` 🆕 | 013 |
| 3.5 | Fusionner exceptions IA dans `exceptions.py` | `exceptions.py` | 013 |
| 3.6 | Exporter dans `models/ai/__init__.py` | `models/ai/__init__.py` 🆕 | 013 |
| 3.7 | Tests | `tests/unit/models/ai/` 🆕 | 013 |

### Phase 4 — Ports IA + Adapters IA + Engine IA + Bridge ConnectorStep (semaine 4-5)

> **Objectif** : migrer la logique `ai_engine` + créer le bridge `pyconnectors`.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 4.1 | Créer `ports/ai/` (BaseLLMClient, BaseTool, BaseSkill, BaseAIStorage) | `ports/ai/*.py` 🆕 | 013 |
| 4.2 | Migrer `ai_engine/services/llm/` → `adapters/ai/llm/` | `adapters/ai/llm/*.py` 🆕 | 013 |
| 4.3 | Migrer `ai_engine/tools/` → `adapters/ai/tools/` | `adapters/ai/tools/*.py` 🆕 | 013 |
| 4.4 | Migrer `ai_engine/skills/` → `adapters/ai/skills/` | `adapters/ai/skills/*.py` 🆕 | 013 |
| 4.5 | Migrer `ai_engine/storage/` → `adapters/ai/storage/` | `adapters/ai/storage/*.py` 🆕 | 013 |
| 4.6 | Migrer `ai_engine/services/agent.py` → `engine/ai/agent_service.py` | `engine/ai/agent_service.py` 🆕 | 013 |
| 4.7 | Créer ponts IA : `AIStep`, `AITrigger`, `AgentExecutor`, `JobAsTool` | `adapters/ai/steps/`, `triggers/`, `executors/`, `bridges/` 🆕 | 013 |
| **4.8** | **Créer `adapters/steps/__init__.py`** | `adapters/steps/__init__.py` 🆕 | **016** |
| **4.9** | **Créer `adapters/steps/connector_step.py` (bridge pyconnectors)** | `adapters/steps/connector_step.py` 🆕 | **016** |
| 4.10 | Étendre `BaseStorage` avec méthodes Pipeline + IA (défaut `NotImplementedError`) | `ports/storage.py` | 013+014 |
| 4.11 | Implémenter dans `SQLiteStorage` (tables pipeline + IA) | `adapters/storage/sqlite.py` | 013+014 |
| 4.12 | Migrer adapters Django/FastAPI IA | `adapters/ai/django/`, `adapters/ai/fastapi/` 🆕 | 013 |
| 4.13 | Tests adapters IA | `tests/unit/adapters/ai/` | 013 |
| **4.14** | **Tests bridge ConnectorStep** | `tests/unit/adapters/steps/test_connector_step.py` 🆕 | **016** |

**Test plan pour le bridge (4.14)** :

```python
# tests/unit/adapters/steps/test_connector_step.py

def test_execute_connector_success(monkeypatch):
    """Le bridge retourne un dict valide quand le connecteur réussit."""
    ...

def test_execute_connector_failure_raises_step_error(monkeypatch):
    """Le bridge lève StepExecutionError quand ConnectorResult.success=False."""
    ...

def test_execute_connector_import_error():
    """Le bridge lève StepExecutionError si pyconnectors n'est pas installé."""
    ...

def test_execute_connector_context_keys():
    """Le dict retourné contient les clés _connector_* attendues."""
    ...

def test_execute_connector_passes_kwargs(monkeypatch):
    """Les kwargs sont bien transmis à connector.execute()."""
    ...
```

### Phase 5 — PipelineRunner promu + facade enrichie (semaine 5)

> **Objectif** : PipelineRunner citoyen de première classe.

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 5.1 | Promouvoir `pipelines/shared/runner.py` → `engine/pipeline_runner.py` | `engine/pipeline_runner.py` 🆕 | 014 |
| 5.2 | Enrichir `WorkflowEngine` : `run_pipeline()`, `run_pipeline_with_storage()` | `facade.py` | 014 |
| 5.3 | Enrichir `WorkflowEngine` : méthodes IA optionnelles (lazy import) | `facade.py` | 013 |
| 5.4 | Réécrire `pipelines/weekly/countries_to_dwh.py` avec `@pipeline`/`@stage` + `StepType.CONNECTOR` | `pipelines/weekly/countries_to_dwh.py` | 014+**016** |
| 5.5 | Rétrocompatibilité : `pipelines/shared/runner.py` délègue vers `engine/pipeline_runner.py` | `pipelines/shared/runner.py` | 014 |
| 5.6 | Tests intégration Pipeline + ConnectorStep | `tests/integration/test_pipeline_execution.py` 🆕 | 014+**016** |

### Phase 6 — Nettoyage + documentation (semaine 6)

| # | Tâche | Fichier(s) | ADR |
|---|---|---|---|
| 6.1 | Archiver `ai_engine/` dans `_archives/ai_engine/` | `_archives/ai_engine/` | 013 |
| 6.2 | Shim `ai_engine/__init__.py` avec re-exports + `DeprecationWarning` | `ai_engine/__init__.py` | 013 |
| 6.3 | Mettre à jour `pyproject.toml` (v0.8.0, extras IA + `connectors`) | `pyproject.toml` | 013+**016** |
| 6.4 | `pyconnectors` reste autonome — aucune modification | `pyconnectors/` | **016** |
| 6.5 | Validation : `grep -rni "from ai_engine"` → 0 (hors shim) | — | 013 |
| 6.6 | `pytest`, `mypy`, `ruff` — green | — | all |
| 6.7 | Guide migration `docs/guides/migrating-from-ai-engine.md` | `docs/guides/` 🆕 | 013 |
| 6.8 | Guide connecteurs `docs/guides/using-connectors-in-workflows.md` | `docs/guides/` 🆕 | **016** |
| 6.9 | `README.md`, `CHANGELOG.md` | — | all |
| 6.10 | Exemples : `examples/03_ai_step_in_pipeline.py`, `examples/04_connector_step.py`, `examples/05_hybrid_pipeline.py` | `examples/` 🆕 | 013+014+**016** |

### Phase 7 — Validation globale et release v0.8.0 (semaine 6)

| # | Tâche | Validation |
|---|---|---|
| 7.1 | `pip install pyworkflow-engine` (core seul) → zéro dépendance | ✅ |
| 7.2 | `pip install pyworkflow-engine[ai]` → modèles IA + LLM factory | ✅ |
| 7.3 | `pip install pyworkflow-engine[connectors]` → bridge ConnectorStep fonctionnel | ✅ |
| 7.4 | `pip install pyworkflow-engine[all]` → tout | ✅ |
| 7.5 | Workflows existants (ETL classiques) non impactés | ✅ Rétrocompat |
| 7.6 | `PipelineRunner` existant dans `pipelines/shared/` fonctionnel | ✅ Rétrocompat |
| 7.7 | `pyconnectors` fonctionne en standalone (aucune modification) | ✅ Autonomie |

---

## Règles de cohabitation dataclass / Pydantic / pyconnectors

```
┌──────────────────────────────────────────────────────────────────┐
│          models/ (dataclass stdlib)                               │
│  enums.py, job.py, step.py, run.py, pipeline.py, pipeline_run.py│
│                                                                   │
│  ⚠️ NE DOIT JAMAIS importer depuis models/ai/ NI pyconnectors   │
└──────────────────────┬───────────────────────────────────────────┘
                       │ peut importer
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│          models/ai/ (Pydantic BaseModel)                         │
│  agent.py, provider.py, message.py, ...                          │
│                                                                   │
│  ✅ PEUT importer RunStatus, StepType, etc. depuis models/       │
│  ⚠️ NE DOIT JAMAIS importer depuis pyconnectors                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│          pyconnectors/ (package autonome)                         │
│  BaseConnector, ConnectorFactory, ConnectorResult, ...            │
│                                                                   │
│  🔒 NE CONNAÎT PAS pyworkflow_engine — zéro import              │
└──────────────────────┬───────────────────────────────────────────┘
                       │ lazy import uniquement via
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│          adapters/steps/connector_step.py (bridge)                │
│                                                                   │
│  ✅ Importe pyconnectors (lazy, au moment de l'appel)            │
│  ✅ Importe pyworkflow_engine.exceptions                          │
│  🔄 Traduit ConnectorResult → dict contexte workflow              │
└──────────────────────────────────────────────────────────────────┘
```

**Règles de dépendances (graphe orienté)** :

```
pyconnectors  ──────────────(aucun lien)──────────────  models/ai/
      ↑ (lazy import)                                       ↑ (peut importer)
      │                                                     │
adapters/steps/connector_step.py           adapters/ai/*.py
      ↑                                                     ↑
      └────────────── engine/runner.py ────────────────────┘
                           ↑
                    engine/pipeline_runner.py
                           ↑
                        facade.py
```

---

## Matrice des impacts par fichier

> Delta vs ADR-015 marqué 🔶.

| Fichier | Phase | ADR | Nature du changement |
|---|---|---|---|
| `models/enums.py` | 1 | 013+014+**016** | Ajout valeurs (`StepType.CONNECTOR`) |
| 🔶 `models/connector.py` | 1 | **016** | 🆕 Création (`ConnectorRef`, `ConnectorOutcome`) |
| 🔶 `models/step.py` | 1 | **016** | Ajout champ `connector_ref: ConnectorRef \| None` |
| 🔶 `models/run.py` | 1+3 | 013+**016** | Ajout champs IA + `connector_outcome: ConnectorOutcome \| None` |
| `models/pipeline.py` | 1 | 014 | 🆕 Création |
| `models/pipeline_run.py` | 1 | 014 | 🆕 Création |
| `models/__init__.py` | 1 | 014+**016** | Ajout exports (`ConnectorRef`, `ConnectorOutcome`, Pipeline, …) |
| 🔶 `tests/unit/test_connector_model.py` | 1 | **016** | 🆕 Création |
| `decorators/pipeline_decorator.py` | 2 | 014 | 🆕 Création |
| `decorators/__init__.py` | 2 | 014 | Ajout exports |
| `events/bus.py` | 2 | 013 | 🆕 Création (depuis ai_engine) |
| `events/events.py` | 2 | 013+014+**016** | 🆕 Création (inclut `connector.*`) |
| `models/ai/*.py` | 3 | 013 | 🆕 Création (depuis ai_engine) |
| `models/run.py` | 3 | 013 | Ajout champs optionnels |
| `config/ai.py` | 3 | 013 | 🆕 Création |
| `exceptions.py` | 3 | 013 | Ajout exceptions IA |
| `ports/ai/*.py` | 4 | 013 | 🆕 Création |
| `adapters/ai/**` | 4 | 013 | 🆕 Création (depuis ai_engine) |
| 🔶 `adapters/steps/__init__.py` | 4 | **016** | 🆕 Création |
| 🔶 `adapters/steps/connector_step.py` | 4 | **016** | 🆕 Création (bridge) |
| `ports/storage.py` | 4 | 013+014 | Ajout méthodes (défaut NotImpl) |
| `adapters/storage/sqlite.py` | 4 | 013+014 | Ajout tables |
| `engine/ai/*.py` | 4 | 013 | 🆕 Création (depuis ai_engine) |
| 🔶 `tests/unit/adapters/steps/test_connector_step.py` | 4 | **016** | 🆕 Création |
| `engine/pipeline_runner.py` | 5 | 014 | 🆕 Création |
| `facade.py` | 5 | 013+014 | Ajout méthodes |
| 🔶 `pipelines/weekly/countries_to_dwh.py` | 5 | 014+**016** | Réécriture avec `@pipeline` + `CONNECTOR` |
| `pipelines/shared/runner.py` | 5 | 014 | Refactor → délègue |
| `pyproject.toml` | 6 | 013+**016** | Ajout extras IA + `connectors` |
| 🔶 `docs/guides/using-connectors-in-workflows.md` | 6 | **016** | 🆕 Création |
| 🔶 `examples/04_connector_step.py` | 6 | **016** | 🆕 Création |
| 🔶 `examples/05_hybrid_pipeline.py` | 6 | **016** | 🆕 Création |

**Total fichiers impactés par ADR-016** : ~8 fichiers supplémentaires vs ADR-015.

---

## Alternatives rejetées

### Fusionner `pyconnectors` dans `pyworkflow_engine`

- ✅ Un seul package à installer.
- ❌ Zéro doublon — aucun bénéfice structurel de la fusion.
- ❌ `pyconnectors` (50+ connecteurs, drivers lourds) enfermé dans un moteur de workflows.
- ❌ `pyconnectors` ne serait plus réutilisable indépendamment.
- ❌ Explosion des dépendances obligatoires.
- ❌ Violation du principe de séparation des préoccupations.

### Copier les modèles `pyconnectors` dans `models/connectors/`

- ✅ Indépendance de versioning.
- ❌ Duplication de code (`ConnectorConfig`, `ConnectorResult`, `BaseConnector`…).
- ❌ Dérive de code garantie.
- ❌ Deux hiérarchies d'exceptions pour les mêmes erreurs.

### Pas d'intégration — utiliser `pyconnectors` directement dans les handlers

- ✅ Zéro travail d'intégration.
- ❌ Pas de standardisation : chaque step gère `pyconnectors` à sa façon.
- ❌ Pas de traçabilité : les métadonnées connecteur (`_connector_*`) ne sont pas standardisées dans le contexte.
- ❌ Pas de type `StepType.CONNECTOR` : impossible de distinguer un step classique d'un step connecteur dans les outils de monitoring/GUI.

### Implémenter ADR-013, 014, 015 séparément puis ajouter pyconnectors

- ❌ Mêmes problèmes que l'implémentation séquentielle documentée dans ADR-015.
- ❌ `StepType` modifié une 3ᵉ fois pour ajouter `CONNECTOR`.
- ❌ Scénarios hybrides (Pipeline + IA + Connector) testés tardivement.

---

## Conséquences

### Positives

- **Un seul plan maître** : ADR-013 (fusion IA) + ADR-014 (Pipeline) + bridge pyconnectors.
- **Zéro conflit de merge** entre les trois intégrations.
- **Symétrie architecturale complète** : Step → Job → Pipeline × (classique + IA + connector).
- **`pyconnectors` reste autonome** : aucune modification, versionné et publiable indépendamment.
- **1 seul fichier bridge** (`connector_step.py`) pour toute l'intégration connecteurs.
- **`StepType.CONNECTOR`** : visibilité claire dans les GUI, CLI, logs, monitoring.
- **Lazy import** : le core ne dépend jamais de `pyconnectors` au niveau statique.
- **Scénarios hybrides testés dès la Phase 5** : Pipeline + IA + Connector validé ensemble.
- **Rétrocompatibilité totale** : core reste dataclass stdlib zéro dépendance.
- **7 phases incrémentales** : chaque phase validable indépendamment.

### Négatives / risques

- **Scope élargi** : ~38 fichiers (vs ~30 dans ADR-015) sur 6 semaines.
- **Dépendance optionnelle** : si `pyconnectors` change son API (`ConnectorResult`, `ConnectorFactory`), le bridge doit être adapté. Mitigé par le versioning `pyconnectors>=0.2.0`.
- **Review volumineuse** : mitigé en découpant en PRs par phase.

---

## Relations entre ADR

```
ADR-013 (ai_engine fusion)     ─────┐
                                     ├──→ ADR-015 (plan unifié 013+014)  ──→ 🔄 Remplacée par ADR-016
ADR-014 (Pipeline + @pipeline) ─────┘

ADR-013 ─────┐
ADR-014 ─────┼──→ ADR-016 (plan maître 013+014+pyconnectors bridge)  ← CETTE ADR
ADR-015 ─────┘
```

ADR-013 et ADR-014 restent comme **documents d'analyse** (contexte, options, décision). ADR-015 est **remplacée** par cette ADR-016 qui est le seul **plan d'exécution**.

---

## Statut

🔵 Proposition — en attente de validation. Supersède ADR-015. Les ADR-013 et ADR-014 restent comme documents d'analyse ; les ADR-013, 014, 015 sont marquées 🔄 Remplacée par ADR-016.
