# Architecture

PyConnectors est construit sur une **architecture hexagonale** (Ports & Adapters, ADR-001/002/003) avec une API publique en trois niveaux d'abstraction (ADR-004).

---

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Niveaux d'abstraction](#niveaux-dabstraction)
- [Concepts fondamentaux](#concepts-fondamentaux)
  - [ConnectorConfig](#connectorconfig)
  - [BaseConnector](#baseconnector)
  - [ConnectorResult](#connectorresult)
  - [Registre & Factory](#registre--factory)
  - [Exceptions](#exceptions)
- [Architecture hexagonale](#architecture-hexagonale)
- [Flux d'exécution](#flux-dexécution)
- [API TaskFlow (v0.4.0)](#api-taskflow-v040)
- [Dépendances](#dépendances)

---

## Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────────────┐
│                        pyconnectors                                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    API publique (api.py)                     │    │
│  │  @connector  @connect  @flow  configure  use  reset          │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                        │
│  ┌──────────────────────────▼──────────────────────────────────┐    │
│  │                      Services                                │    │
│  │  ConnectorFactory  ·  ConnectorService  ·  ConnectorLoader   │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                        │
│  ┌──────────┐  ┌────────────▼──────────┐  ┌──────────────────┐     │
│  │  Ports   │  │      Adapters         │  │     Models       │     │
│  │ (ABCs)   │  │  registry · auth      │  │  BaseConnector   │     │
│  │          │  │  logging  · config    │  │  ConnectorResult │     │
│  └──────────┘  └───────────────────────┘  │  ConnectorConfig │     │
│                                           │  Exceptions      │     │
│                                           └──────────────────┘     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Connectors (42+)                           │   │
│  │  http · database · email · storage · social · payment · auth  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Niveaux d'abstraction

```
Niveau 3 — Applicatif   @flow(name="...")
                            ↓ compose des
Niveau 2 — Service      @connect("key") / configure() / use()
                            ↓ délègue à
Niveau 1 — Infra        @connector("key") → Registre → Factory.create() → instance.execute()
```

| Niveau | API | Cible |
|--------|-----|-------|
| **3 — Applicatif** | `@connect`, `@flow` | Développeur application |
| **2 — Service** | `configure`, `use` | Développeur application |
| **1 — Infra** | `@connector`, `ConnectorFactory` | Développeur de connecteurs |

---

## Concepts fondamentaux

### ConnectorConfig

`dataclass` central de configuration. Sépare `params` (données publiques) et `secrets` (exclus de la sérialisation).

```python
from pyconnectors import ConnectorConfig, AuthMethod

config = ConnectorConfig(
    name="Mon API",
    params={"base_url": "https://api.example.com", "timeout": 30},
    secrets={"api_key": "sk_live_xxx"},   # jamais loggé ni sérialisé
    auth_method=AuthMethod.API_KEY,
    tags=["production"],
)
```

**Constructeurs alternatifs :**

```python
# Depuis un dict
config = ConnectorConfig.from_dict({"params": {"database": "app.db"}})

# Depuis un fichier JSON
config = ConnectorConfig.from_json_file("config/db.json")

# Depuis des variables d'environnement
config = ConnectorConfig.from_env("PG_")   # charge toutes les vars PG_*
```

**Méthodes lifecycle :**

```python
config.increment_usage()   # incrémente usage_count
config.mark_active()       # status → ACTIVE
config.mark_inactive()     # status → INACTIVE
config.mark_error("msg")   # status → ERROR
config.get_merged_config() # params + secrets fusionnés
```

---

### BaseConnector

Classe de base abstraite pour tous les connecteurs synchrones. Tout connecteur doit :
1. Hériter de `BaseConnector`
2. Implémenter `execute(*args, **kwargs) -> Any`

```python
from pyconnectors import BaseConnector, connector

@connector("myapp.service")
class MyConnector(BaseConnector):
    """Description affichée dans `con list`."""

    def execute(self, **kwargs):
        # logique métier — peut lever librement des exceptions
        return {"result": "ok"}

    def test_connection(self):
        # override optionnel — health-check léger
        return True, "OK"
```

**`safe_execute()` — ne lève jamais :**

```python
result = conn.safe_execute(query="SELECT 1")
# Équivalent à :
#   try: execute(query="SELECT 1") → ConnectorResult(success=True, data=...)
#   except: ConnectorResult(success=False, error=str(e), ...)
```

**Hooks lifecycle :**

```python
conn.add_hook("pre_execute",  lambda c, *a, **kw: print("avant"))
conn.add_hook("post_execute", lambda c, r, *a, **kw: print(f"après {r.duration:.3f}s"))
conn.add_hook("on_error",     lambda c, r, *a, **kw: print(f"erreur: {r.error}"))
```

**`AsyncBaseConnector` — pour l'async I/O :**

```python
from pyconnectors import AsyncBaseConnector

class MyAsyncConnector(AsyncBaseConnector):
    async def execute(self, **kwargs):
        ...   # coroutine libre
```

---

### ConnectorResult

Envelope standardisée retournée par `safe_execute()` et tous les décorateurs TaskFlow.

```python
result = connector.safe_execute(query="SELECT * FROM users")

result.success    # bool
result.data       # Any — données retournées par execute()
result.error      # Optional[str] — message si success=False
result.duration   # float — temps d'exécution en secondes
result.metadata   # Dict[str, Any] — contexte additionnel

result.to_dict()  # sérialisation plain dict
```

**Combinateurs fonctionnels (Railway-Oriented Programming) :**

```python
names = (
    result
    .map(lambda rows: [r["name"] for r in rows])          # transforme data
    .flat_map(lambda names: another_connector(names))      # chaîne un autre ConnectorResult
    .on_error(lambda e: logger.error("failed: %s", e))    # side-effect sur erreur
    .unwrap_or([])                                          # extrait data ou valeur par défaut
)

result.unwrap()               # extrait data ou lève ValueError si failure
result.unwrap_or_else(fn)     # extrait data ou appelle fn(error)
```

---

### Registre & Factory

**Registre** (`InMemoryRegistryAdapter`) — stocke les classes par clé :

```python
from pyconnectors import InMemoryRegistryAdapter, connector

# Le décorateur @connector enregistre dans _default_registry (singleton)
@connector("myapp.service")
class MyConnector(BaseConnector): ...

# Enregistrement manuel
registry = InMemoryRegistryAdapter()
registry.register("myapp.service", MyConnector)
cls = registry.get("myapp.service")          # → MyConnector
names = registry.list_names()                # → ["myapp.service"]
registry.is_registered("myapp.service")     # → True
```

**Factory** (`ConnectorFactory`) — instancie depuis le registre :

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

# Stateless (API classe — le plus courant)
conn = ConnectorFactory.create("http.rest", config=ConnectorConfig())

# Avec logger personnalisé (API instance)
from pyconnectors import StdlibLoggerAdapter
factory = ConnectorFactory(logger=StdlibLoggerAdapter("myapp"))
result = factory.execute("http.rest", config, method="GET", url="/api")
ok, msg = factory.test_connector("http.rest", config)
```

Les connecteurs built-in sont **auto-chargés** au premier appel de `Factory.create()` (via `_BUILTIN_MODULES`). Aucun import manuel requis.

---

### Exceptions

Hiérarchie avec héritage mixte Python (chaque exception hérite aussi d'une exception stdlib) :

```
PyConnectorsError (Exception)
├── ConnectorNotFoundError     → aussi KeyError
├── ConnectorConfigurationError → aussi ValueError
├── ConnectorExecutionError     → aussi RuntimeError
├── ConnectorInactiveError      → aussi ValueError
├── ConnectorConnectionError    → aussi ConnectionError
├── ConnectorAuthError
└── ConnectorTimeoutError       → aussi TimeoutError
```

```python
from pyconnectors import ConnectorNotFoundError, ConnectorExecutionError

try:
    result = factory.execute("unknown.connector", config)
except ConnectorNotFoundError as e:
    print(e)   # "Connector 'unknown.connector' not found in registry. Available: [...]"
```

---

## Architecture hexagonale

```
           ┌─────────────────────────────────────────┐
           │              Cœur (stdlib only)          │
           │                                          │
           │  ports/          ← interfaces ABCs        │
           │  ├── registry.py  (RegistryPort)          │
           │  ├── logger.py    (LoggerPort)            │
           │  └── auth_strategy.py                    │
           │                                          │
           │  models/         ← entités               │
           │  ├── base.py     (BaseConnector)          │
           │  ├── result.py   (ConnectorResult)        │
           │  ├── config/     (ConnectorConfig)        │
           │  ├── specs.py    (ConnectSpec/FlowSpec)   │
           │  ├── exceptions.py                       │
           │  ├── enums.py                            │
           │  └── lifecycle.py                        │
           └──────────────────┬──────────────────────┘
                              │ implements
           ┌──────────────────▼──────────────────────┐
           │            Adapters                      │
           │  adapters/registry/memory.py             │
           │  adapters/auth/bearer|api_key|basic|...  │
           │  adapters/logging/stdlib.py              │
           └──────────────────┬──────────────────────┘
                              │ uses
           ┌──────────────────▼──────────────────────┐
           │         Services & API                   │
           │  services/factory.py                     │
           │  services/connector_service.py           │
           │  api.py  (@connect @flow configure use)  │
           └─────────────────────────────────────────┘
```

**Règle de dépendance :** les couches intérieures (`ports/`, `models/`) ne dépendent jamais des couches extérieures.

---

## Flux d'exécution

**Appel direct (Niveau 1) :**

```
app code
  → ConnectorFactory.create("http.rest", config)
  → InMemoryRegistryAdapter.get("http.rest") → RestConnector class
  → RestConnector(config).__init__()
  → conn.safe_execute(method="GET", url="/api")
    → pre_execute hooks
    → conn.execute(method="GET", url="/api")     ← logique métier
    → post_execute / on_error hooks
    → ConnectorResult(success=True, data=..., duration=...)
```

**Avec TaskFlow (Niveau 2/3) :**

```
@connect("http.rest")
def fetch(conn, org): return conn.execute(...)

fetch(org="octocat")
  → résolution config (_config= > config= > configure())
  → ConnectorFactory.create("http.rest", resolved_config)
  → inject conn as 1st arg → call user function
  → wrap return in ConnectorResult
```

---

## API TaskFlow (v0.4.0)

Les deux décorateurs de fonction introduits par ADR-004 :

| Décorateur | Rôle | Métadonnées |
|---|---|---|
| `@connector("key")` | Enregistre une **classe** dans le registre | — |
| `@connect("key")` | Injecte un connecteur dans une **fonction** | `__connect_spec__` (ConnectSpec) |
| `@flow(name=...)` | Compose des `@connect` en pipeline | `__flow_spec__` (FlowSpec) |

```python
@dataclass(frozen=True)
class ConnectSpec:
    connector_type: str           # "http.rest"
    name: str                     # nom de la fonction
    config: Optional[dict]        # config figée au décorateur
    tags: FrozenSet[str]

@dataclass(frozen=True)
class FlowSpec:
    name: str                     # nom du flow
    connects: tuple[str, ...]     # @connect détectés dans le corps
    description: str
    tags: FrozenSet[str]
```

Voir [ADR-004](changelog/ADR-004-taskflow-decorators-connect-and-flow.md) pour le design complet.

---

## Dépendances

**Cœur — zéro dépendance externe :**

| Module | Stdlib utilisée |
|---|---|
| `models/`, `ports/`, `config/` | `dataclasses`, `abc`, `uuid`, `datetime`, `typing` |
| `adapters/registry/` | `threading`, `logging` |
| `adapters/auth/` | `base64`, `urllib` |
| `api.py` | `functools`, `time`, `warnings` |
| `services/factory.py` | `importlib`, `time` |
| `cli/` | `typer`, `rich` *(dépendance optionnelle)* |

**Dépendances optionnelles par connecteur :**

| Extra | Packages | Connecteurs activés |
|---|---|---|
| `postgresql` | `psycopg[binary]` | `database.postgresql` |
| `mysql` | `pymysql`, `cryptography` | `database.mysql` |
| `mongodb` | `pymongo` | `database.mongodb` |
| `redis` | `redis` | `database.redis` |
| `s3` | `boto3` | `storage.s3`, `storage.minio`, `storage.digitalocean`, `storage.hetzner`, `storage.ovh`, `email.ses` |
| `gcs` | `google-cloud-storage` | `storage.gcs` |
| `azure_blob` | `azure-storage-blob` | `storage.azure_blob` |
| `adls` | `azure-storage-file-datalake` | `storage.adls` |
| `cloudinary` | `cloudinary` | `storage.cloudinary` |
| `auth` | `PyJWT` | `auth.jwt` |
| `payment` | `stripe` | `payment.stripe` |

```bash
# Installer plusieurs extras
uv pip install "pyconnectors[postgresql,redis,s3,auth]"
```
