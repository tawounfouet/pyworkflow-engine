# Quickstart

Lancez-vous avec PyConnectors en cinq minutes.

---

## Installation

```bash
# Recommandé — avec uv (évite les restrictions PEP 668 sur macOS/Linux)
uv pip install pyconnectors

# Ou avec pip (dans un environnement virtuel)
pip install pyconnectors

# Installation dev (mode éditable)
uv pip install -e "."
```

Installez les extras optionnels pour les familles de connecteurs dont vous avez besoin :

```bash
uv pip install "pyconnectors[postgresql]"   # PostgreSQL
uv pip install "pyconnectors[s3]"           # Amazon S3 (boto3)
uv pip install "pyconnectors[auth]"         # JWT (PyJWT)
uv pip install "pyconnectors[email]"        # Resend e-mail transactionnel
```

---

## Premier connecteur

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

# 1. Configurer
config = ConnectorConfig(params={"timeout": 10})

# 2. Créer via la Factory (déclenche l'enregistrement automatique)
http = ConnectorFactory.create("http.rest", config=config)

# 3. Exécuter — ne lève jamais d'exception, retourne toujours un ConnectorResult
result = http.safe_execute("GET", "https://jsonplaceholder.typicode.com/todos/1")

if result.success:
    print(f"✅  {result.data['body']}  ({result.duration:.2f}s)")
else:
    print(f"❌  {result.error}")
```

**Concepts clés :**
- `ConnectorConfig()` — instance par défaut (zéro config)
- `ConnectorFactory.create("http.rest", ...)` — résolution du connecteur via le registre
- `safe_execute()` — retourne toujours un `ConnectorResult`, ne lève jamais
- `result.success`, `result.data`, `result.error`, `result.duration`

---

## Chargement de la configuration

### Depuis un fichier JSON

```python
from pyconnectors import ConnectorConfig

config = ConnectorConfig.from_json_file("config.json")
```

```json
{
  "timeout": 30,
  "retries": 3,
  "base_url": "https://api.example.com",
  "api_key": "your_key"
}
```

### Depuis les variables d'environnement

```bash
export MYAPP_API_KEY=secret
export MYAPP_TIMEOUT=30
```

```python
from pyconnectors import ConnectorConfig

config = ConnectorConfig.from_env("MYAPP_")
# → params = {"api_key": "secret", "timeout": "30"}
```

---

## Hooks de cycle de vie

```python
def on_done(connector, result, *args, **kwargs):
    print(f"Terminé en {result.duration:.3f}s — success={result.success}")

http.add_hook("post_execute", on_done)
http.add_hook("on_error", lambda c, r, *a, **kw: print("Erreur :", r.error))
```

| Hook | Se déclenche |
|------|-------------|
| `pre_execute` | Avant chaque appel |
| `post_execute` | Après chaque appel réussi |
| `on_error` | Quand `execute()` lève une exception |

---

## API en ligne de commande

```bash
# Lister tous les connecteurs enregistrés
con list

# Inspecter un connecteur spécifique
con inspect http.rest

# Exécuter depuis un fichier de config JSON
con run config.json
```

Voir le [guide CLI](cli.md) pour la référence complète.

---

## API TaskFlow — `@connect` et `@flow` *(v0.4.0)*

L'API décorateur TaskFlow fournit l'injection automatique de connecteurs et la composition de flux.

### `@connect` — injecter un connecteur dans une fonction

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("database.sqlite", ConnectorConfig(params={"database": "app.db"}))

@connect("database.sqlite")
def create_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)")
    return "created"

@connect("database.sqlite")
def insert_user(conn, name: str):
    conn.execute("INSERT INTO users (name) VALUES (?)", (name,))
    return {"inserted": name}

result = create_table()
print(result.success)    # True
print(result.duration)   # 0.0003
```

La config peut aussi être passée directement au décorateur ou surchargée à l'appel :

```python
from pyconnectors import connect, ConnectorConfig

@connect("http.rest", config=ConnectorConfig(params={"base_url": "https://api.github.com"}))
def fetch_repos(conn, org="octocat"):
    return conn.execute(method="GET", url=f"/users/{org}/repos")

# Surcharger à l'appel (_config= a la priorité la plus haute)
result = fetch_repos(org="python", _config=ConnectorConfig(params={"base_url": "http://localhost"}))
```

**Ordre de résolution de la config :**
1. `_config=` au moment de l'appel *(priorité maximale)*
2. `config=` passé au décorateur
3. Config pré-enregistrée via `configure()`

### `@flow` — composer des étapes `@connect`

```python
from pyconnectors import connect, flow, configure, ConnectorConfig

configure("database.sqlite", ConnectorConfig(params={"database": "app.db"}))

@connect("database.sqlite")
def setup(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, name TEXT)")
    return "ready"

@connect("database.sqlite")
def record(conn, name: str):
    conn.execute("INSERT INTO events (name) VALUES (?)", (name,))
    return {"recorded": name}

@flow(name="event-pipeline")
def run_pipeline(event: str):
    setup()
    return record(name=event)

result = run_pipeline(event="deploy")
print(result.success)              # True
print(result.metadata["flow"])     # "event-pipeline"
```

Les exceptions sont automatiquement capturées dans un `ConnectorResult(success=False)` — pas de `try/except` nécessaire.

Voir [ADR-004](changelog/ADR-004-taskflow-decorators-connect-and-flow.md) pour la justification complète du design.

---

## Résumé des imports publics

Tous les symboles publics sont disponibles directement depuis `pyconnectors` :

```python
from pyconnectors import (
    ConnectorFactory,    # créer des connecteurs
    ConnectorConfig,     # configurer
    connector,           # décorateur de classe
    connect,             # décorateur de fonction TaskFlow
    flow,                # décorateur de flux TaskFlow
    configure,           # pré-enregistrer une config
    use,                 # exécuter un connecteur par nom
    reset,               # vider le registre
    list_types,          # lister les connecteurs disponibles
)
```

---

## Étapes suivantes

- 📖 **[Guide des exemples](examples.md)** — scripts exécutables pour chaque famille (HTTP, base de données, email, S3, OAuth2, …)
- 🏗️ **[Architecture](architecture.md)** — hiérarchie de classes, registre, modèle de résultat
- 🖥️ **[Référence CLI](cli.md)** — toutes les commandes et raccourcis shell
- 🤝 **[Contribution](contributing.md)** — comment ajouter un nouveau connecteur
