# ADR-017 — Couche de persistence unifiée : ModelRegistry + Repository CRUD générique

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| **ID**      | ADR-017                             |
| **Date**    | 12 avril 2026                       |
| **Statut**  | 🔵 Proposition                      |
| **Auteur**  | équipe pyworkflow-engine            |
| **Décisions liées** | ADR-006 (hexagonal), ADR-012 (rename persistence→storage), ADR-013 (AI engine), ADR-016 (master plan) |
| **Version cible** | v0.8.0                         |
| **Complète** | ADR-016 phase persistence          |

---

## Motivation

### Le problème

Le projet dispose actuellement de **deux systèmes de persistence parallèles** qui ne communiquent pas :

| Système | Port | Backends | Modèles couverts |
|---------|------|----------|-----------------|
| **Core workflow** | `ports/storage.py` → `BaseStorage` | `InMemoryStorage`, `SQLiteStorage`, `JSONFileStorage`, `SQLAlchemyStorage` | `Job`, `JobRun`, `StepRun`, `PipelineRun`, `StageRun` |
| **AI (ADR-013)** | `ports/ai/storage.py` → `BaseAIStorage` | *(pas encore implémenté)* | `Agent`, `LLMProviderConfig`, `ToolDefinition`, `Skill`, `Conversation`, `Message`, `Execution`, `ExecutionStep`, `Graph`, `AgentMemory`, `KnowledgeSource`, `Document`, `Chunk` |

Ce dualisme pose **6 problèmes concrets** :

| # | Problème | Impact |
|---|----------|--------|
| 1 | **Duplication du code de persistence** | Chaque backend (`InMemory`, `SQLite`, `JSONFile`, `SQLAlchemy`) devra être réécrit intégralement pour `BaseAIStorage` — soit **4 × 13 entités = 52 implémentations CRUD** manuelles |
| 2 | **Schéma SQL écrit à la main** | Le DDL est codé en dur dans `SQLiteStorage.SCHEMA_SQL` (300+ lignes). Chaque nouveau modèle nécessite l'écriture manuelle du CREATE TABLE + migration |
| 3 | **Sérialisation artisanale** | Chaque modèle a ses `_serialize_*` / `_deserialize_*` manuels dans chaque backend. Patterns répétitifs : `json.dumps()` / `json.loads()`, `datetime.fromisoformat()`, gestion des `None` |
| 4 | **Pas de registre de modèles** | Aucun mécanisme pour découvrir automatiquement quels modèles doivent avoir une table — contrairement à Django (`INSTALLED_APPS` + `ModelAdmin`) |
| 5 | **Pas de requêtage générique** | Chaque méthode `list_*` réécrit les clauses WHERE, ORDER BY, LIMIT/OFFSET manuellement. Pas de filtrage dynamique style `QuerySet.filter()` |
| 6 | **Cohabitation `dataclass` / Pydantic** | Les modèles core (`Job`, `Step`, `JobRun`) sont en `dataclass` stdlib, les modèles IA en `Pydantic BaseModel`. La persistence doit gérer les deux sans les coupler |

### L'inspiration : Django ORM

Django résout ces problèmes avec 3 concepts :

| Concept Django | Rôle | Équivalent proposé |
|----------------|------|-------------------|
| `django.db.models.Model` | Chaque modèle déclare ses champs + meta | `PersistableModel` + `__table_meta__` (déclaratif) |
| `django.apps.apps.get_models()` | Registre auto-discovery de tous les modèles | `ModelRegistry` (décorateur `@register`) |
| `Model.objects` (Manager) | CRUD + QuerySet avec filtres chainés | `Repository[T]` (générique, typé) |
| `manage.py migrate` | Génère/applique le DDL | `SchemaGenerator` + `UnifiedStorage.migrate()` |

### Ce que cette ADR ne fait PAS

- ❌ **Ne remplace pas** `BaseStorage` / `BaseAIStorage` — ils restent les ports hexagonaux
- ❌ **Ne force pas** Pydantic sur les modèles core — les `dataclass` restent
- ❌ **Ne supprime pas** les backends existants — `SQLiteStorage`, `InMemoryStorage` continuent de fonctionner
- ❌ **N'introduit pas** de dépendance externe (SQLAlchemy ORM, Tortoise, etc.)

---

## Inventaire complet des modèles à persister

### Modèles core (dataclass stdlib)

| Modèle | Fichier | Clé primaire | Table SQL | Statut |
|--------|---------|-------------|-----------|--------|
| `Job` | `models/job.py` | `name` | `jobs` | ✅ Table existe |
| `JobRun` | `models/run.py` | `job_run_id` | `job_runs` | ✅ Table existe |
| `StepRun` | `models/run.py` | `step_run_id` | `step_runs` | ✅ Table existe |
| `Pipeline` | `models/pipeline.py` | `name` | `pipelines` | ⚠️ Pas de table (sérialisé en JSON dans PipelineRun) |
| `PipelineRun` | `models/pipeline_run.py` | `pipeline_run_id` | `pipeline_runs` | ✅ Table existe (schema v3) |
| `StageRun` | `models/pipeline_run.py` | `stage_run_id` | `stage_runs` | ✅ Table existe (schema v3) |
| `ConnectorRef` | `models/connector.py` | *(embedded dans Step)* | — | — Design-time uniquement |
| `ConnectorOutcome` | `models/connector.py` | *(embedded dans StepRun)* | — | — Runtime, sérialisé en JSON dans StepRun.metadata |

### Modèles IA (Pydantic BaseModel)

| Modèle | Fichier | Clé primaire | Table SQL cible | Statut |
|--------|---------|-------------|-----------------|--------|
| `LLMProviderConfig` | `models/ai/provider.py` | `id` | `providers` | 🆕 À créer |
| `Agent` | `models/ai/agent.py` | `id` | `agents` | 🆕 À créer |
| `AgentConfig` | `models/ai/agent.py` | *(embedded dans Agent)* | — | — Sérialisé en JSON dans `agents.config` |
| `ToolDefinition` | `models/ai/tool.py` | `id` | `tools` | 🆕 À créer |
| `Skill` | `models/ai/skill.py` | `id` | `skills` | 🆕 À créer |
| `AgentSkillAssignment` | `models/ai/skill.py` | `id` | `agent_skill_assignments` | 🆕 À créer |
| `Conversation` | `models/ai/conversation.py` | `id` | `conversations` | 🆕 À créer |
| `Message` | `models/ai/message.py` | `id` | `messages` | 🆕 À créer |
| `ToolCall` | `models/ai/message.py` | *(embedded dans Message)* | — | — Sérialisé en JSON dans `messages.tool_calls` |
| `ToolResult` | `models/ai/message.py` | *(embedded dans Message)* | — | — Sérialisé en JSON dans `messages.tool_result` |
| `TokenUsage` | `models/ai/message.py` | *(embedded dans Message)* | — | — Sérialisé en JSON dans `messages.token_usage` |
| `Execution` | `models/ai/execution.py` | `id` | `executions` | 🆕 À créer |
| `ExecutionStep` | `models/ai/execution.py` | `id` | `execution_steps` | 🆕 À créer |
| `Graph` | `models/ai/graph.py` | `id` | `graphs` | 🆕 À créer |
| `GraphNode` | `models/ai/graph.py` | *(embedded dans Graph)* | — | — Sérialisé en JSON dans `graphs.nodes` |
| `GraphEdge` | `models/ai/graph.py` | *(embedded dans Graph)* | — | — Sérialisé en JSON dans `graphs.edges` |
| `AgentMemory` | `models/ai/memory.py` | `id` | `memories` | 🆕 À créer |
| `KnowledgeSource` | `models/ai/knowledge.py` | `id` | `knowledge_sources` | 🆕 À créer |
| `Document` | `models/ai/knowledge.py` | `id` | `documents` | 🆕 À créer |
| `Chunk` | `models/ai/knowledge.py` | `id` | `chunks` | 🆕 À créer |

**Total : 13 nouvelles tables à créer** pour le sous-système IA, plus 1 table `pipelines` manquante pour le core.

### Règle d'embedding

Un sous-modèle est **embedded** (sérialisé en JSON dans une colonne de la table parente) quand :

- Il n'a pas d'identité propre (pas d'ID)
- Il n'est jamais requêté indépendamment
- Il est toujours lu/écrit avec son parent

Exemples : `AgentConfig`, `ToolCall`, `TokenUsage`, `GraphNode`, `GraphEdge`, `ProviderSettings`, `ProviderCapabilities`, `PricingConfig`.

---

## Architecture proposée

### Vue d'ensemble

```
                  ┌─────────────────────────────────────┐
                  │         scripts/migrate.py           │  ← CLI "manage.py migrate"
                  └─────────────────┬───────────────────┘
                                    │
                  ┌─────────────────▼───────────────────┐
                  │          UnifiedStorage              │  ← Façade (point d'entrée)
                  │  .agents  .providers  .messages      │    (raccourcis nommés)
                  │  .repository(MyModel)                │    (accès générique)
                  │  .migrate()                          │    (DDL auto)
                  └──┬────────────┬─────────────────┬───┘
                     │            │                 │
           ┌─────────▼──┐  ┌─────▼───────┐  ┌─────▼──────┐
           │ Repository  │  │ Repository  │  │ Repository │  ← CRUD générique
           │  <Agent>    │  │ <Provider>  │  │ <Message>  │    (style Manager)
           └──────┬──────┘  └──────┬──────┘  └──────┬─────┘
                  │                │                 │
           ┌──────▼────────────────▼─────────────────▼─────┐
           │            ModelSerializer                     │  ← to_row() / from_row()
           │  Pydantic → dict SQL     dict SQL → Pydantic   │    (JSON, datetime, bool)
           └──────────────────┬────────────────────────────┘
                              │
           ┌──────────────────▼────────────────────────────┐
           │            SchemaGenerator                     │  ← DDL auto depuis TableMeta
           │  generate_create_table()  generate_indexes()   │
           └──────────────────┬────────────────────────────┘
                              │
           ┌──────────────────▼────────────────────────────┐
           │   @ModelRegistry.register + __table_meta__     │  ← Déclaration (style Meta)
           │   Agent, Provider, Conversation, Message ...   │
           └────────────────────────────────────────────────┘
```

### Relation avec l'architecture hexagonale existante

```
    ports/                          adapters/storage/
    ├── storage.py (BaseStorage)    ├── memory.py (InMemoryStorage)     ← EXISTANT
    │     Jobs, JobRuns, Pipelines  ├── sqlite.py (SQLiteStorage)          (inchangé)
    │                               ├── json_file.py (JSONFileStorage)
    │                               ├── sqlalchemy.py (SQLAlchemyStorage)
    ├── ai/                         │
    │   └── storage.py              ├── unified.py (UnifiedStorage)     ← 🆕 NOUVEAU
    │       (BaseAIStorage)         │     ModelRegistry + Repository
    │                               ├── persistable.py                  ← 🆕 port
    │                               ├── schema_generator.py             ← 🆕
    │                               └── repository.py                   ← 🆕
    └── ...                         └── ...
```

Le `UnifiedStorage` est un **nouvel adapter** qui coexiste avec les backends existants. Il peut **remplacer progressivement** les implémentations manuelles une fois stabilisé.

---

## Composant 1 : `PersistableModel` + `TableMeta` + `ModelRegistry`

### Fichier : `ports/persistable.py`

Le contrat déclaratif — chaque modèle Pydantic qui doit être persisté annotera une `ClassVar[TableMeta]` et sera enregistré via `@ModelRegistry.register`.

```python
# ports/persistable.py
"""
Port — Contrat de persistence déclarative pour les modèles Pydantic.

Inspiration : django.db.models.Model + Meta + AppConfig.ready()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel


class ColumnType(StrEnum):
    """Types de colonnes SQL supportés."""
    TEXT = "TEXT"
    INTEGER = "INTEGER"
    REAL = "REAL"
    BOOLEAN = "INTEGER"     # SQLite n'a pas de bool natif
    JSON = "JSON"           # stocké comme TEXT, sérialisé/désérialisé
    TIMESTAMP = "TIMESTAMP"


@dataclass
class ColumnDef:
    """Définition d'une colonne SQL."""
    name: str
    col_type: ColumnType
    primary_key: bool = False
    nullable: bool = True
    default: Any = None
    foreign_key: str | None = None   # "table.column"
    index: bool = False


@dataclass
class TableMeta:
    """Métadonnées de persistence pour un modèle Pydantic.

    Équivalent du `class Meta:` de Django.
    """
    table_name: str
    columns: list[ColumnDef]
    indexes: list[tuple[str, ...]] = field(default_factory=list)
    foreign_keys_cascade: bool = True


class PersistableModel(BaseModel):
    """Mixin pour les modèles Pydantic qui doivent être persistés.

    Chaque sous-classe DOIT déclarer ``__table_meta__`` (ClassVar[TableMeta]).
    """
    __table_meta__: ClassVar[TableMeta]


class ModelRegistry:
    """Registre centralisé de tous les modèles persistables.

    Analogue à ``django.apps.apps.get_models()``.
    """
    _models: dict[str, type[PersistableModel]] = {}

    @classmethod
    def register(cls, model: type[PersistableModel]) -> type[PersistableModel]:
        """Décorateur d'enregistrement."""
        meta = getattr(model, "__table_meta__", None)
        if meta is None:
            raise ValueError(f"{model.__name__} must define __table_meta__")
        cls._models[meta.table_name] = model
        return model

    @classmethod
    def get_all(cls) -> dict[str, type[PersistableModel]]:
        return dict(cls._models)

    @classmethod
    def get_model(cls, table_name: str) -> type[PersistableModel] | None:
        return cls._models.get(table_name)

    @classmethod
    def clear(cls) -> None:
        cls._models.clear()
```

### Pourquoi `PersistableModel` hérite de `BaseModel` (Pydantic)

| Alternative | Avantage | Inconvénient |
|-------------|----------|-------------|
| **Mixin sans héritage** | Compatible dataclass + Pydantic | Pas de validation, pas de `model_validate()` |
| **Protocol** | Duck-typing pur | Pas d'outillage IDE, pas de contrainte forte |
| **Héritage Pydantic** (retenu) | `model_validate()` gratuit, sérialisation intégrée, compatible IDE | Limité aux modèles Pydantic (modèles AI) |

Les modèles core (`Job`, `JobRun`, `StepRun`) en `dataclass` **ne sont pas concernés** — ils restent persistés par `BaseStorage` / `SQLiteStorage`. Le `PersistableModel` ne couvre que les **nouveaux modèles IA et futurs modèles**.

---

## Composant 2 : `SchemaGenerator` + `ModelSerializer`

### Fichier : `adapters/storage/schema_generator.py`

Génère le DDL SQL depuis les `TableMeta` et sérialise/désérialise les modèles.

```python
# adapters/storage/schema_generator.py

class SchemaGenerator:
    """Génère le DDL SQLite depuis les TableMeta enregistrés."""

    @staticmethod
    def generate_create_table(meta: TableMeta) -> str:
        """CREATE TABLE IF NOT EXISTS..."""

    @staticmethod
    def generate_indexes(meta: TableMeta) -> list[str]:
        """CREATE INDEX IF NOT EXISTS..."""

    @classmethod
    def generate_full_schema(cls) -> str:
        """DDL complet pour TOUS les modèles du ModelRegistry."""


class ModelSerializer:
    """Sérialise/désérialise Pydantic ↔ lignes SQL."""

    @classmethod
    def to_row(cls, instance: PersistableModel) -> dict[str, Any]:
        """Modèle Pydantic → dict SQL-ready.

        Gère automatiquement :
        - JSON: BaseModel → model_dump_json(), dict/list → json.dumps()
        - TIMESTAMP: datetime → isoformat()
        - BOOLEAN: bool → 0/1
        - SecretStr → get_secret_value()
        - StrEnum → .value
        """

    @classmethod
    def from_row(cls, model_class, row) -> PersistableModel:
        """Ligne SQL (dict ou sqlite3.Row) → modèle Pydantic.

        Gère automatiquement :
        - JSON: str → json.loads()
        - TIMESTAMP: str → datetime.fromisoformat()
        - BOOLEAN: 0/1 → bool
        """
```

### Règles de sérialisation

| Type Python | Type colonne | Sérialisation | Désérialisation |
|-------------|-------------|---------------|-----------------|
| `str` | TEXT | Identité | Identité |
| `int` | INTEGER | Identité | Identité |
| `float` | REAL | Identité | Identité |
| `bool` | INTEGER | `1` / `0` | `bool(value)` |
| `datetime` | TIMESTAMP | `.isoformat()` | `datetime.fromisoformat()` |
| `dict`, `list` | JSON (TEXT) | `json.dumps()` | `json.loads()` |
| `BaseModel` (embedded) | JSON (TEXT) | `.model_dump_json()` | `model_validate()` |
| `SecretStr` | TEXT | `.get_secret_value()` | *(non reconstitué — sécurité)* |
| `StrEnum` | TEXT | `.value` | *(géré par Pydantic `model_validate`)* |
| `None` | — | `NULL` | `None` |

---

## Composant 3 : `Repository[T]` — CRUD générique

### Fichier : `adapters/storage/repository.py`

Repository paramétré par le type de modèle, analogue à `Model.objects` (Django Manager).

```python
# adapters/storage/repository.py

class Repository(Generic[T]):
    """Repository CRUD générique, paramétré par type[T: PersistableModel]."""

    def __init__(self, connection: sqlite3.Connection, model_class: type[T]): ...

    # ── Create ──
    def create(self, instance: T) -> T: ...
    def create_or_update(self, instance: T) -> T: ...       # INSERT OR REPLACE

    # ── Read ──
    def get(self, pk: str) -> T | None: ...
    def get_or_raise(self, pk: str) -> T: ...                # lève LookupError
    def filter(self, *, order_by=None, limit=None, offset=0, **conditions) -> list[T]: ...
    def all(self, order_by=None) -> list[T]: ...
    def count(self, **conditions) -> int: ...
    def exists(self, pk: str) -> bool: ...

    # ── Update ──
    def update(self, instance: T) -> T: ...                  # auto-update updated_at

    # ── Delete ──
    def delete(self, pk: str) -> bool: ...
    def delete_where(self, **conditions) -> int: ...
```

### Filtres dynamiques (style Django `QuerySet.filter()`)

Le `Repository.filter()` supporte des opérateurs via le suffixe `__` :

| Syntaxe | SQL généré | Exemple |
|---------|-----------|---------|
| `field=value` | `field = ?` | `role="researcher"` |
| `field__gte=value` | `field >= ?` | `created_at__gte="2026-01-01"` |
| `field__lte=value` | `field <= ?` | `total_tokens__lte=10000` |
| `field__gt=value` | `field > ?` | `priority__gt=5` |
| `field__lt=value` | `field < ?` | `cost__lt=1.0` |
| `field__like=value` | `field LIKE ?` | `name__like="%bot%"` |
| `field__in=values` | `field IN (?, ?, ?)` | `status__in=["active", "paused"]` |
| `field__isnull=True` | `field IS NULL` | `expires_at__isnull=True` |

**Pas d'injection SQL** : tous les filtres utilisent des paramètres positionnels (`?`).

---

## Composant 4 : `UnifiedStorage` — façade avec repos nommés

### Fichier : `adapters/storage/unified.py`

Point d'entrée unique qui compose `SchemaGenerator` + `Repository`.

```python
# adapters/storage/unified.py

class UnifiedStorage:
    """Backend de persistence unifié avec auto-discovery des modèles."""

    def __init__(self, database_path: str = "./workflow.db"): ...

    @property
    def connection(self) -> sqlite3.Connection: ...    # thread-local, lazy

    # ── Migration ──
    def migrate(self) -> list[str]: ...                # crée toutes les tables

    # ── Accès générique ──
    def repository(self, model_class: type[T]) -> Repository[T]: ...

    # ── Raccourcis nommés (IDE-friendly) ──
    @property
    def agents(self) -> Repository[Agent]: ...
    @property
    def providers(self) -> Repository[LLMProviderConfig]: ...
    @property
    def conversations(self) -> Repository[Conversation]: ...
    @property
    def messages(self) -> Repository[Message]: ...
    @property
    def tools(self) -> Repository[ToolDefinition]: ...
    @property
    def skills(self) -> Repository[Skill]: ...
    @property
    def graphs(self) -> Repository[Graph]: ...
    @property
    def executions(self) -> Repository[Execution]: ...
    @property
    def execution_steps(self) -> Repository[ExecutionStep]: ...
    @property
    def memories(self) -> Repository[AgentMemory]: ...
    @property
    def knowledge_sources(self) -> Repository[KnowledgeSource]: ...
    @property
    def documents(self) -> Repository[Document]: ...
    @property
    def chunks(self) -> Repository[Chunk]: ...

    # ── Observabilité ──
    def health_check(self) -> dict[str, Any]: ...
    def get_table_names(self) -> list[str]: ...
    def close(self) -> None: ...
```

---

## Composant 5 : `scripts/migrate.py` — CLI de migration

### Fichier : `scripts/migrate.py`

```bash
# Appliquer les migrations (créer/mettre à jour les tables)
python -m scripts.migrate

# Voir le DDL sans exécuter
python -m scripts.migrate --dry-run

# Base de données personnalisée
python -m scripts.migrate --db ./my_database.db
```

### Intégration future avec le CLI adapter (ADR-008)

```bash
# Via le CLI Typer (futur)
pyworkflow db migrate
pyworkflow db migrate --dry-run
pyworkflow db status
pyworkflow db reset --confirm
```

---

## Déclaration des `__table_meta__` — mapping complet

### Table `agents`

```python
@ModelRegistry.register
class Agent(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="agents",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("slug", ColumnType.TEXT),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("role", ColumnType.TEXT, nullable=False),
            ColumnDef("provider_id", ColumnType.TEXT, foreign_key="providers.id"),
            ColumnDef("model", ColumnType.TEXT),
            ColumnDef("system_prompt", ColumnType.TEXT),
            ColumnDef("welcome_message", ColumnType.TEXT),
            ColumnDef("config", ColumnType.JSON),               # AgentConfig embedded
            ColumnDef("tool_ids", ColumnType.JSON),              # list[str]
            ColumnDef("skill_ids", ColumnType.JSON),             # list[str]
            ColumnDef("knowledge_base_ids", ColumnType.JSON),    # list[str]
            ColumnDef("owner_id", ColumnType.TEXT),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("slug",), ("role",), ("provider_id",), ("owner_id",)],
    )
```

### Table `providers`

```python
@ModelRegistry.register
class LLMProviderConfig(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="providers",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("provider_type", ColumnType.TEXT, nullable=False),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("default_model", ColumnType.TEXT, nullable=False),
            ColumnDef("api_key", ColumnType.TEXT),               # SecretStr
            ColumnDef("api_base_url", ColumnType.TEXT),
            ColumnDef("extra_secrets", ColumnType.JSON),
            ColumnDef("settings", ColumnType.JSON),              # ProviderSettings embedded
            ColumnDef("capabilities", ColumnType.JSON),          # ProviderCapabilities embedded
            ColumnDef("pricing", ColumnType.JSON),               # PricingConfig embedded
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("is_default", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("provider_type",), ("is_active",)],
    )
```

### Table `conversations`

```python
@ModelRegistry.register
class Conversation(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="conversations",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("title", ColumnType.TEXT),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="agents.id"),
            ColumnDef("owner_id", ColumnType.TEXT),
            ColumnDef("status", ColumnType.TEXT, nullable=False),
            ColumnDef("summary", ColumnType.TEXT),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("message_count", ColumnType.INTEGER),
            ColumnDef("total_tokens", ColumnType.INTEGER),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
            ColumnDef("last_message_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("agent_id",), ("owner_id",), ("status",)],
    )
```

### Table `messages`

```python
@ModelRegistry.register
class Message(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="messages",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("conversation_id", ColumnType.TEXT, foreign_key="conversations.id"),
            ColumnDef("role", ColumnType.TEXT, nullable=False),
            ColumnDef("content", ColumnType.TEXT),
            ColumnDef("tool_calls", ColumnType.JSON),            # list[ToolCall] embedded
            ColumnDef("tool_result", ColumnType.JSON),           # ToolResult embedded
            ColumnDef("token_usage", ColumnType.JSON),           # TokenUsage embedded
            ColumnDef("model_used", ColumnType.TEXT),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("conversation_id",), ("role",), ("created_at",)],
    )
```

### Table `tools`

```python
@ModelRegistry.register
class ToolDefinition(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="tools",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("key", ColumnType.TEXT, nullable=False),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("tool_type", ColumnType.TEXT),
            ColumnDef("parameters_schema", ColumnType.JSON),
            ColumnDef("return_type", ColumnType.TEXT),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("key",), ("tool_type",)],
    )
```

### Table `skills`

```python
@ModelRegistry.register
class Skill(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="skills",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("key", ColumnType.TEXT, nullable=False),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("category", ColumnType.TEXT),
            ColumnDef("system_prompt", ColumnType.TEXT),
            ColumnDef("required_tool_ids", ColumnType.JSON),
            ColumnDef("config", ColumnType.JSON),
            ColumnDef("recommended_provider_id", ColumnType.TEXT),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("key",), ("category",)],
    )
```

### Table `executions`

```python
@ModelRegistry.register
class Execution(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="executions",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="agents.id"),
            ColumnDef("conversation_id", ColumnType.TEXT, foreign_key="conversations.id"),
            ColumnDef("status", ColumnType.TEXT, nullable=False),
            ColumnDef("input_data", ColumnType.JSON),
            ColumnDef("output_data", ColumnType.JSON),
            ColumnDef("error", ColumnType.TEXT),
            ColumnDef("token_usage", ColumnType.JSON),           # TokenUsage embedded
            ColumnDef("total_cost", ColumnType.REAL),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("started_at", ColumnType.TIMESTAMP),
            ColumnDef("completed_at", ColumnType.TIMESTAMP),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("agent_id",), ("conversation_id",), ("status",)],
    )
```

### Table `execution_steps`

```python
@ModelRegistry.register
class ExecutionStep(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="execution_steps",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("execution_id", ColumnType.TEXT, foreign_key="executions.id"),
            ColumnDef("step_type", ColumnType.TEXT, nullable=False),
            ColumnDef("order", ColumnType.INTEGER),
            ColumnDef("input_data", ColumnType.JSON),
            ColumnDef("output_data", ColumnType.JSON),
            ColumnDef("error", ColumnType.TEXT),
            ColumnDef("agent_id", ColumnType.TEXT),
            ColumnDef("tool_id", ColumnType.TEXT),
            ColumnDef("token_usage", ColumnType.JSON),           # TokenUsage embedded
            ColumnDef("tokens_used", ColumnType.INTEGER),
            ColumnDef("cost", ColumnType.REAL),
            ColumnDef("duration_ms", ColumnType.INTEGER),
            ColumnDef("started_at", ColumnType.TIMESTAMP),
            ColumnDef("completed_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("execution_id",), ("step_type",)],
    )
```

### Table `graphs`

```python
@ModelRegistry.register
class Graph(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="graphs",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("slug", ColumnType.TEXT),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="agents.id"),
            ColumnDef("status", ColumnType.TEXT),
            ColumnDef("nodes", ColumnType.JSON),                 # list[GraphNode] embedded
            ColumnDef("edges", ColumnType.JSON),                 # list[GraphEdge] embedded
            ColumnDef("entry_node_id", ColumnType.TEXT),
            ColumnDef("state_schema", ColumnType.JSON),
            ColumnDef("owner_id", ColumnType.TEXT),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("slug",), ("agent_id",), ("status",)],
    )
```

### Table `memories`

```python
@ModelRegistry.register
class AgentMemory(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="memories",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="agents.id"),
            ColumnDef("memory_type", ColumnType.TEXT),
            ColumnDef("key", ColumnType.TEXT, nullable=False),
            ColumnDef("content", ColumnType.TEXT, nullable=False),
            ColumnDef("embedding", ColumnType.JSON),             # list[float]
            ColumnDef("relevance_score", ColumnType.REAL),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("expires_at", ColumnType.TIMESTAMP),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("agent_id",), ("memory_type",), ("agent_id", "key")],
    )
```

### Table `knowledge_sources`

```python
@ModelRegistry.register
class KnowledgeSource(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="knowledge_sources",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("description", ColumnType.TEXT),
            ColumnDef("source_type", ColumnType.TEXT, nullable=False),
            ColumnDef("content", ColumnType.TEXT),
            ColumnDef("file_path", ColumnType.TEXT),
            ColumnDef("url", ColumnType.TEXT),
            ColumnDef("index_status", ColumnType.TEXT),
            ColumnDef("document_count", ColumnType.INTEGER),
            ColumnDef("chunk_count", ColumnType.INTEGER),
            ColumnDef("embedding_model", ColumnType.TEXT),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("source_type",), ("index_status",)],
    )
```

### Table `documents`

```python
@ModelRegistry.register
class Document(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="documents",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("source_id", ColumnType.TEXT, foreign_key="knowledge_sources.id"),
            ColumnDef("title", ColumnType.TEXT),
            ColumnDef("content", ColumnType.TEXT),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("chunk_count", ColumnType.INTEGER),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
            ColumnDef("updated_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("source_id",)],
    )
```

### Table `chunks`

```python
@ModelRegistry.register
class Chunk(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="chunks",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("document_id", ColumnType.TEXT, foreign_key="documents.id"),
            ColumnDef("content", ColumnType.TEXT, nullable=False),
            ColumnDef("embedding", ColumnType.JSON),             # list[float]
            ColumnDef("chunk_index", ColumnType.INTEGER),
            ColumnDef("metadata", ColumnType.JSON),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("document_id",), ("chunk_index",)],
    )
```

### Table `agent_skill_assignments`

```python
@ModelRegistry.register
class AgentSkillAssignment(PersistableModel):
    __table_meta__ = TableMeta(
        table_name="agent_skill_assignments",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("agent_id", ColumnType.TEXT, foreign_key="agents.id"),
            ColumnDef("skill_id", ColumnType.TEXT, foreign_key="skills.id"),
            ColumnDef("proficiency", ColumnType.TEXT),
            ColumnDef("priority", ColumnType.INTEGER),
            ColumnDef("config_overrides", ColumnType.JSON),
            ColumnDef("assigned_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("agent_id",), ("skill_id",), ("agent_id", "skill_id")],
    )
```

---

## Relation entre `BaseAIStorage` et `UnifiedStorage`

### Option retenue : `UnifiedStorage` implémente `BaseAIStorage`

`UnifiedStorage` peut servir d'**adapter concret** pour le port `BaseAIStorage` :

```python
class UnifiedStorage(BaseAIStorage):
    """Implémente BaseAIStorage via les Repository génériques."""

    def save_agent(self, agent: Agent) -> Agent:
        return self.agents.create_or_update(agent)

    def get_agent(self, agent_id: str) -> Agent | None:
        return self.agents.get(agent_id)

    def list_agents(self, *, owner_id=None, role=None, is_active=None):
        conditions = {}
        if owner_id is not None: conditions["owner_id"] = owner_id
        if role is not None: conditions["role"] = role
        if is_active is not None: conditions["is_active"] = is_active
        return self.agents.filter(**conditions)

    def delete_agent(self, agent_id: str) -> bool:
        return self.agents.delete(agent_id)

    # ... idem pour chaque entité
```

Chaque méthode abstraite de `BaseAIStorage` est un **one-liner** qui délègue au `Repository` correspondant. Plus besoin d'écrire 52 implémentations manuelles.

---

## Diagramme des relations entre tables

```
                    providers
                       │ 1
                       │
                       ▼ *
    skills ◄──── agents ────► conversations ────► messages
       │          │   │           │
       │          │   │           │
       ▼          │   ▼           ▼
 agent_skill_     │  graphs    executions ────► execution_steps
 assignments      │
                  │
                  ▼
               memories

    knowledge_sources ────► documents ────► chunks
```

### Clés étrangères

| Table enfant | Colonne FK | Table parent | Colonne PK | CASCADE DELETE |
|-------------|-----------|-------------|-----------|---------------|
| `agents` | `provider_id` | `providers` | `id` | ✅ |
| `conversations` | `agent_id` | `agents` | `id` | ✅ |
| `messages` | `conversation_id` | `conversations` | `id` | ✅ |
| `executions` | `agent_id` | `agents` | `id` | ✅ |
| `executions` | `conversation_id` | `conversations` | `id` | ✅ |
| `execution_steps` | `execution_id` | `executions` | `id` | ✅ |
| `graphs` | `agent_id` | `agents` | `id` | ✅ |
| `memories` | `agent_id` | `agents` | `id` | ✅ |
| `agent_skill_assignments` | `agent_id` | `agents` | `id` | ✅ |
| `agent_skill_assignments` | `skill_id` | `skills` | `id` | ✅ |
| `documents` | `source_id` | `knowledge_sources` | `id` | ✅ |
| `chunks` | `document_id` | `documents` | `id` | ✅ |

---

## Plan d'implémentation

### Phase 1 — Fondations (sprint 1)

| Tâche | Fichier | Effort |
|-------|---------|--------|
| Créer `PersistableModel`, `TableMeta`, `ModelRegistry` | `ports/persistable.py` | S |
| Créer `SchemaGenerator`, `ModelSerializer` | `adapters/storage/schema_generator.py` | M |
| Créer `Repository[T]` avec CRUD + filtres | `adapters/storage/repository.py` | M |
| Tests unitaires du Repository (InMemory-style) | `tests/test_repository.py` | M |

### Phase 2 — Déclaration des modèles (sprint 1)

| Tâche | Fichier | Effort |
|-------|---------|--------|
| Ajouter `__table_meta__` sur tous les modèles IA | `models/ai/*.py` | M |
| Faire hériter de `PersistableModel` | `models/ai/*.py` | S |
| Tester la génération DDL complète | `tests/test_schema_generator.py` | S |

### Phase 3 — UnifiedStorage (sprint 2)

| Tâche | Fichier | Effort |
|-------|---------|--------|
| Créer `UnifiedStorage` avec `migrate()` | `adapters/storage/unified.py` | M |
| Implémenter `BaseAIStorage` via Repository | `adapters/storage/unified.py` | M |
| Ajouter les raccourcis nommés | `adapters/storage/unified.py` | S |
| Tests d'intégration CRUD end-to-end | `tests/test_unified_storage.py` | L |

### Phase 4 — CLI et intégration (sprint 2)

| Tâche | Fichier | Effort |
|-------|---------|--------|
| Script `migrate.py` avec `--dry-run` | `scripts/migrate.py` | S |
| Intégrer dans `WorkflowEngine.facade.py` | `facade.py` | S |
| Commande CLI `pyworkflow db migrate` | `adapters/cli/` | M |
| Documentation utilisateur | `docs/guides/` | M |

### Phase 5 — Migration progressive des backends (sprint 3+)

| Tâche | Effort | Priorité |
|-------|--------|----------|
| Adapter `InMemoryStorage` pour utiliser les Repository IA | M | Haute |
| Adapter `SQLiteStorage` pour utiliser le schema auto-généré | L | Moyenne |
| Adapter `JSONFileStorage` pour les modèles IA | M | Basse |
| Adapter `SQLAlchemyStorage` pour les modèles IA | L | Basse |

---

## Alternatives considérées

### Alternative 1 : SQLAlchemy ORM complet

| Avantage | Inconvénient |
|----------|-------------|
| ORM mature, migrations (Alembic), QueryBuilder | Dépendance lourde (40+ fichiers) |
| Support multi-DB natif | Contradictoire avec la philosophie "stdlib first" du core |
| Lazy loading, relations | Complexité pour des besoins CRUD simples |

**Rejetée** : trop lourd. `SQLAlchemyStorage` existe déjà comme adapter optionnel pour ceux qui veulent PostgreSQL/MySQL. Le `UnifiedStorage` couvre le cas SQLite/développement sans dépendance.

### Alternative 2 : Tortoise ORM / Pydantic-SQLAlchemy

| Avantage | Inconvénient |
|----------|-------------|
| Intégration Pydantic native | Dépendance externe supplémentaire |
| AsyncIO-first | Le moteur est synchrone actuellement |

**Rejetée** : prématuré tant que le moteur n'est pas async.

### Alternative 3 : Étendre `BaseStorage` pour tous les modèles

| Avantage | Inconvénient |
|----------|-------------|
| Interface unique | `BaseStorage` deviendrait une interface de 100+ méthodes |
| Compatible avec les 4 backends | Chaque backend devrait implémenter 100+ méthodes manuellement |

**Rejetée** : explosion combinatoire. C'est exactement le problème que le `Repository` générique résout.

### Alternative 4 : Persistence Pydantic via `model_dump()` / `model_validate()` directe

| Avantage | Inconvénient |
|----------|-------------|
| Zéro code supplémentaire | Pas de requêtage SQL (juste dump/load JSON) |
| Fonctionne immédiatement | Pas de filtres, pas d'index, pas de FK |

**Rejetée** : ne scale pas au-delà de quelques dizaines d'objets.

---

## Contraintes et règles de conception

### Règle 1 : Pas d'import circulaire

```
ports/persistable.py  ← NE dépend de RIEN sauf stdlib + pydantic
models/ai/*.py        ← Importent ports/persistable
adapters/storage/*    ← Importent ports/persistable + models/ai
```

### Règle 2 : Cohabitation `dataclass` / Pydantic

- Les modèles core (`Job`, `Step`, `JobRun`, `StepRun`, `PipelineRun`, `StageRun`) restent en `dataclass`
- Les modèles IA héritent désormais de `PersistableModel` (qui hérite de `BaseModel` Pydantic)
- Les deux systèmes coexistent — le `Repository` générique ne concerne que les `PersistableModel`

### Règle 3 : Zéro dépendance externe ajoutée

- `ports/persistable.py` : `pydantic` (déjà dans `[ai]` extras)
- `adapters/storage/repository.py` : `sqlite3` (stdlib)
- `adapters/storage/schema_generator.py` : `json` (stdlib)

### Règle 4 : Thread-safety

Le `UnifiedStorage` utilise des connexions thread-local (même pattern que `SQLiteStorage`).

### Règle 5 : Ordre de création des tables

Le `SchemaGenerator` doit respecter l'ordre des clés étrangères :

1. `providers` (pas de FK)
2. `agents` (FK → providers)
3. `skills` (pas de FK)
4. `tools` (pas de FK)
5. `conversations` (FK → agents)
6. `messages` (FK → conversations)
7. `executions` (FK → agents, conversations)
8. `execution_steps` (FK → executions)
9. `graphs` (FK → agents)
10. `memories` (FK → agents)
11. `agent_skill_assignments` (FK → agents, skills)
12. `knowledge_sources` (pas de FK)
13. `documents` (FK → knowledge_sources)
14. `chunks` (FK → documents)

Le `ModelRegistry` expose une méthode `get_ordered()` qui résout cet ordre via un tri topologique des FK.

---

## Métriques de succès

| Métrique | Avant (actuel) | Après (cible) |
|----------|----------------|---------------|
| Lignes de code pour 1 nouveau modèle persisté | ~200 (DDL + serialize + deserialize × 4 backends) | ~30 (TableMeta + `@register`) |
| Temps d'ajout d'une entité IA | ~2h (4 backends) | ~15min (déclarer + migrate) |
| Backends couverts pour les modèles IA | 0 | 1 (SQLite via UnifiedStorage) |
| Tests CRUD par entité | 0 | ~10 (via tests paramétrés) |
| Requêtes ad-hoc possibles | Non (méthodes fixes) | Oui (`filter()` dynamique) |

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|-----------|
| Performance des filtres dynamiques vs SQL écrit à la main | Faible | Moyen | Les index sont déclarés dans `TableMeta`. Le SQL généré est paramétrisé. Benchmark à faire en phase 3. |
| Injection SQL via `filter()` | Faible | Critique | Tous les filtres utilisent des `?` positionnels. Les noms de colonnes sont validés contre `TableMeta.columns`. |
| Incompatibilité future avec les migrations de schéma | Moyen | Moyen | Le `SchemaGenerator` utilise `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`. Les migrations destructives (ALTER TABLE) ne sont pas supportées dans la v1 — prévoir un outil de migration dédié en phase 5. |
| Complexité de la cohabitation `BaseStorage` + `UnifiedStorage` | Moyen | Faible | Les deux systèmes sont indépendants. La façade choisit lequel utiliser selon le type de modèle. Convergence progressive. |

---

## Références

- [Django Model Meta options](https://docs.djangoproject.com/en/5.0/ref/models/options/)
- [Django Managers](https://docs.djangoproject.com/en/5.0/topics/db/managers/)
- [Repository Pattern (Martin Fowler)](https://martinfowler.com/eaaCatalog/repository.html)
- ADR-006 — Architecture hexagonale (`ports/` + `adapters/`)
- ADR-012 — Renommage `persistence` → `storage`
- ADR-013 — Intégration AI Engine (modèles Pydantic dans `models/ai/`)
- ADR-016 — Plan maître d'intégration
