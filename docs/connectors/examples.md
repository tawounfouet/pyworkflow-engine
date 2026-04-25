# Examples Guide

All runnable examples live in the [`examples/`](../examples/) directory.  
Run any of them from the project root with:

```bash
uv run python examples/<filename>.py
```

---

## Table of Contents

| # | File | Topic |
|---|------|-------|
| 01 | [`01_basic_usage.py`](#01-basic-usage) | HTTP REST — minimal setup |
| 02 | [`02_from_json_config.py`](#02-configuration-from-json) | Load config from a JSON file |
| 03 | [`03_from_env_vars.py`](#03-configuration-from-environment-variables) | Load config from env vars |
| 04 | [`04_hooks_and_logging.py`](#04-hooks--lifecycle-logging) | Pre / post / on_error hooks |
| 08 | [`08_database_connectors.py`](#08-database-connectors) | SQLite in-memory & persistent |
| 09 | [`09_email_connectors.py`](#09-email-connectors) | Resend API & Gmail SMTP |
| 10 | [`10_social_connectors.py`](#10-social-connectors) | Twitter / X API v2 |
| 11 | [`11_storage_connectors.py`](#11-storage-connectors) | Amazon S3 |
| 12 | [`12_http_auth.py`](#12-http-authentication) | Basic Auth, API Keys & sessions |
| 13 | [`13_auth_connectors.py`](#13-auth-connectors) | JWT encoding & OAuth2 flow |
| 14 | [`14_real_databases.py`](#14-real-cloud-databases) | PostgreSQL · MySQL · MongoDB · Redis via `.env` |
| 15 | [TaskFlow](#15-taskflow-api) | `@connect` + `@flow` pipeline |

---

## 01 — Basic Usage

**File:** `examples/01_basic_usage.py`  
**Dependencies:** none (stdlib only)

The simplest possible example. Creates an `http.rest` connector with a default config and fetches a public JSON endpoint.

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig()
http = ConnectorFactory.create("http.rest", config=config)

result = http.safe_execute("GET", "https://jsonplaceholder.typicode.com/todos/1")

if result.success:
    print(f"Duration: {result.duration:.2f}s")
    print("Data:", result.data["body"])
else:
    print("Failed:", result.error)
```

**Key concepts:**
- `ConnectorConfig()` — zero-config default instance
- `ConnectorFactory.create("http.rest", ...)` — connector resolution by registry key
- `safe_execute()` — always returns a `ConnectorResult`; never raises
- `result.success`, `result.data`, `result.error`, `result.duration`

---

## 02 — Configuration from JSON

**File:** `examples/02_from_json_config.py`  
**Dependencies:** none

Load connector configuration from a JSON file using `ConnectorConfig.from_json_file()`.

```python
import json, tempfile
from pyconnectors import ConnectorFactory, ConnectorConfig

config_data = {"timeout": 10, "retries": 3, "base_url": "https://api.example.com"}

with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
    json.dump(config_data, f)
    config_path = f.name

config = ConnectorConfig.from_json_file(config_path)
connector = ConnectorFactory.create("http.rest", config=config)
print("Params:", connector.config.params)
```

**Key concepts:**
- `ConnectorConfig.from_json_file(path)` — reads any JSON file into `config.params`
- Useful for storing per-environment settings or sharing configs across scripts

**Typical `config.json` shape:**
```json
{
  "timeout": 30,
  "retries": 3,
  "base_url": "https://api.example.com",
  "api_key": "your_key_here"
}
```

---

## 03 — Configuration from Environment Variables

**File:** `examples/03_from_env_vars.py`  
**Dependencies:** none

Load configuration from prefixed environment variables using `ConnectorConfig.from_env()`.

```python
import os
from pyconnectors import ConnectorFactory, ConnectorConfig

os.environ["PG_DSN"] = "postgres://user:pass@localhost:5432/db"
os.environ["PG_POOL_SIZE"] = "10"

config = ConnectorConfig.from_env("PG_")
connector = ConnectorFactory.create("database.postgresql", config=config)
print("Params:", connector.config.params)
# → {"dsn": "postgres://...", "pool_size": "10"}
```

**Key concepts:**
- `ConnectorConfig.from_env(prefix)` — collects all env vars with the given prefix, strips the prefix, and lowercases the keys
- Ideal for 12-factor / containerised deployments (Docker, Kubernetes)

**Setting vars in a `.env` file (with `python-dotenv`):**
```bash
# .env
PG_DSN=postgres://user:pass@localhost:5432/db
PG_POOL_SIZE=10
```
```python
from dotenv import load_dotenv
load_dotenv()
config = ConnectorConfig.from_env("PG_")
```

---

## 04 — Hooks & Lifecycle Logging

**File:** `examples/04_hooks_and_logging.py`  
**Dependencies:** none

Register callbacks for three lifecycle events: `pre_execute`, `post_execute`, and `on_error`.

```python
import logging
from pyconnectors import ConnectorFactory, ConnectorConfig

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hooks")

def pre_log(connector, *args, **kwargs):
    log.info(f"[PRE]  Starting {connector.__class__.__name__}")

def post_log(connector, result, *args, **kwargs):
    log.info(f"[POST] Finished in {result.duration:.3f}s — success={result.success}")

def error_log(connector, result, *args, **kwargs):
    log.error(f"[ERR]  {result.error}")

config = ConnectorConfig()
http = ConnectorFactory.create("http.rest", config=config)

http.add_hook("pre_execute", pre_log)
http.add_hook("post_execute", post_log)
http.add_hook("on_error", error_log)

http.safe_execute("GET", "https://httpbin.org/get")   # triggers pre + post
http.safe_execute("GET", "invalid_url")                # triggers pre + on_error
```

**Hook signatures:**

| Event | Callback signature |
|---|---|
| `pre_execute` | `fn(connector, *args, **kwargs)` |
| `post_execute` | `fn(connector, result, *args, **kwargs)` |
| `on_error` | `fn(connector, result, *args, **kwargs)` |

**Use-cases:** observability, metrics, alerting, request tracing.

---

## 08 — Database Connectors

**File:** `examples/08_database_connectors.py`  
**Dependencies:** none (uses Python's built-in `sqlite3`)

Demonstrates DDL, inserts, and queries against an in-memory SQLite database.

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"database": ":memory:"})
sqlite = ConnectorFactory.create("database.sqlite", config=config)

# CREATE TABLE
sqlite.safe_execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL
    )
""")

# INSERT rows (parameterised — SQL injection safe)
sqlite.safe_execute("INSERT INTO users (name, email) VALUES (?, ?)", ("Alice", "alice@example.com"))
sqlite.safe_execute("INSERT INTO users (name, email) VALUES (?, ?)", ("Bob",   "bob@example.com"))

# SELECT
result = sqlite.safe_execute("SELECT * FROM users")
if result.success:
    for row in result.data:
        print(f"- {row['name']} ({row['email']})")
```

**Other supported databases (optional dependencies):**

| Connector key | Install extra |
|---|---|
| `database.postgresql` | `pip install pyconnectors[postgresql]` |
| `database.mysql` | `pip install pyconnectors[mysql]` |
| `database.sqlite` | built-in ✅ |

---

## 09 — Email Connectors

**File:** `examples/09_email_connectors.py`  
**Dependencies:** `pip install pyconnectors[email]` for Resend; Gmail uses stdlib `smtplib`

Two email connectors are demonstrated: **Resend** (transactional API) and **Gmail** (SMTP).

```python
import os
from pyconnectors import ConnectorFactory, ConnectorConfig

# --- Resend (transactional API) ---
resend_config = ConnectorConfig(params={
    "api_key": os.environ.get("RESEND_API_KEY", "re_demo"),
    "from_addr": "onboarding@resend.dev",
})
resend = ConnectorFactory.create("email.resend", config=resend_config)
result = resend.safe_execute(
    to_addr="test@example.com",
    subject="Hello from PyConnectors!",
    body_html="<h1>Hello!</h1>",
)
print("Resend:", "OK" if result.success else result.error)

# --- Gmail (SMTP + App Password) ---
gmail_config = ConnectorConfig(params={
    "user": "your_email@gmail.com",
    "password": "your_app_password",   # generate at myaccount.google.com → Security
})
gmail = ConnectorFactory.create("email.gmail", config=gmail_config)
# gmail.safe_execute(to_addr="...", subject="...", body="...")
```

> **Tip:** For Gmail, [create an App Password](https://myaccount.google.com/apppasswords) — regular account passwords won't work with SMTP.

---

## 10 — Social Connectors

**File:** `examples/10_social_connectors.py`  
**Dependencies:** none (uses stdlib `urllib`)

Calls the **Twitter / X API v2** using a Bearer Token (read-only endpoints).

```python
import os
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "bearer_token": os.environ.get("TWITTER_BEARER_TOKEN", "mock_token"),
})
twitter = ConnectorFactory.create("social.twitter", config=config)

result = twitter.safe_execute("users/me")
if result.success:
    print("User:", result.data)
else:
    print("Failed (expected with mock token):", result.error)
```

**How to get a Bearer Token:**
1. Create a project at [developer.twitter.com](https://developer.twitter.com/en/portal/dashboard)
2. Generate a Bearer Token under *Keys & Tokens*
3. Export it: `export TWITTER_BEARER_TOKEN=AAA...`

---

## 11 — Storage Connectors

**File:** `examples/11_storage_connectors.py`  
**Dependencies:** `pip install pyconnectors[s3]` (installs `boto3`)

Upload and download objects to/from **Amazon S3**.

```python
import os
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "aws_access_key_id":     os.environ.get("AWS_ACCESS_KEY_ID"),
    "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
    "region_name": "us-east-1",
})
s3 = ConnectorFactory.create("storage.s3", config=config)

# Upload
result = s3.safe_execute(
    action="upload",
    bucket="my-bucket",
    key="hello.txt",
    data=b"Hello from PyConnectors!",
)
print("Upload:", "OK" if result.success else result.error)

# Download
result = s3.safe_execute(action="download", bucket="my-bucket", key="hello.txt")
if result.success:
    print("Downloaded:", result.data)
```

**Credential setup (recommended — no hardcoding):**
```bash
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=wJal...
# or use an IAM role / instance profile in production
```

---

## 12 — HTTP Authentication

**File:** `examples/12_http_auth.py`  
**Dependencies:** none

Three authentication patterns for the `http.rest` connector, all tested against [httpbin.org](https://httpbin.org).

### Basic Auth + Session Persistence

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "auth_type": "basic",
    "username": "user",
    "password": "password",
    "base_url": "https://httpbin.org",
    "use_session": True,   # persists cookies across requests
})
http = ConnectorFactory.create("http.rest", config=config)

result = http.safe_execute("GET", "https://httpbin.org/basic-auth/user/password")
print("Auth:", "OK" if result.success else "Failed")

# Session cookies persist automatically
http.safe_execute("GET", "https://httpbin.org/cookies/set?mycookie=chocolate")
r = http.safe_execute("GET", "https://httpbin.org/cookies")
print("Cookies:", r.data)
```

### API Key in Header

```python
config = ConnectorConfig(params={
    "api_key": "super_secret_token",
    "api_key_header": "Authorization",
    "api_key_prefix": "Bearer",   # → "Authorization: Bearer super_secret_token"
})
http = ConnectorFactory.create("http.rest", config=config)
result = http.safe_execute("GET", "https://httpbin.org/headers")
```

### API Key in Query String

```python
config = ConnectorConfig(params={
    "api_key": "abc123xyz",
    "api_key_in": "query",
    "api_key_query_param": "token",   # → ?token=abc123xyz
})
http = ConnectorFactory.create("http.rest", config=config)
result = http.safe_execute("GET", "https://httpbin.org/get")
```

---

## 13 — Auth Connectors

**File:** `examples/13_auth_connectors.py`  
**Dependencies:** `pip install pyconnectors[auth]` for JWT

### JWT — Encode & Decode

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"secret_key": "super_secret_key"})
jwt_conn = ConnectorFactory.create("auth.jwt", config=config)

# Encode
payload = {"user_id": 42, "role": "admin"}
result_enc = jwt_conn.safe_execute("encode", payload=payload)
token = result_enc.data["token"]
print("Token:", token)

# Decode
result_dec = jwt_conn.safe_execute("decode", token=token)
print("Payload:", result_dec.data["payload"])
# → {"user_id": 42, "role": "admin"}
```

### OAuth2 — Auto Token Injection

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "oauth2_token_url":      "https://auth.example.com/oauth/token",
    "oauth2_client_id":      "client_123",
    "oauth2_client_secret":  "secret_abc",
})
api = ConnectorFactory.create("http.oauth2", config=config)

# The connector fetches a token automatically, then injects it as a Bearer header
result = api.safe_execute("GET", "https://api.example.com/protected/resource")
```

> The `http.oauth2` connector wraps `http.rest` — it fetches an access token on the first request and reuses it (with automatic refresh) for subsequent calls.

---

## 14 — Real Cloud Databases

**File:** `examples/14_real_databases.py`  
**Dependencies:** `psycopg[binary]`, `pymysql`, `cryptography`, `pymongo`, `redis`, `python-dotenv`

```bash
uv pip install "pyconnectors[postgresql,mysql,mongodb,redis]" cryptography python-dotenv
```

Connects to all four live cloud databases in sequence, reading credentials from a `.env` file. Each section creates a temporary table / collection / key, performs a full read-write cycle, then cleans up.

```python
from dotenv import load_dotenv
load_dotenv()   # reads POSTGRES_URL, MYSQL_URL, MONGODB_URL, REDIS_URL from .env

import os
from pyconnectors import ConnectorFactory, ConnectorConfig

# PostgreSQL — URL param key: "url" (alias for "dsn")
pg = ConnectorFactory.create(
    "database.postgresql",
    config=ConnectorConfig(params={"url": os.environ["POSTGRES_URL"]}),
)
result = pg.safe_execute("SELECT version()")
print(result.data[0][0])   # PostgreSQL 17.x on …

# MySQL — URL parsed automatically via urllib.parse.urlparse
mysql = ConnectorFactory.create(
    "database.mysql",
    config=ConnectorConfig(params={"url": os.environ["MYSQL_URL"]}),
)
result = mysql.safe_execute("SELECT VERSION()")
print(result.data)

# MongoDB — URL param key: "url" (alias for "uri")
mongo = ConnectorFactory.create(
    "database.mongodb",
    config=ConnectorConfig(params={
        "url": os.environ["MONGODB_URL"],
        "database": os.environ.get("MONGODB_DATABASE", "default"),
    }),
)
mongo.safe_execute("demo", "insert_one", data={"hello": "world"})

# Redis — URL param key: "url"
r = ConnectorFactory.create(
    "database.redis",
    config=ConnectorConfig(params={"url": os.environ["REDIS_URL"]}),
)
r.safe_execute("set", key="ping", value="pong")
print(r.safe_execute("get", key="ping").data)   # "pong"
```

**Key concepts:**
- All four connectors accept a single `url` / `uri` / `dsn` param — no manual host/port/user parsing needed
- `python-dotenv`'s `load_dotenv()` populates `os.environ` from `.env` before any connector is created
- `safe_execute()` wraps every call — connection errors surface in `result.error`, never as uncaught exceptions
- MySQL 8 requires the `cryptography` package for `caching_sha2_password` authentication

**`.env` template** (copy from `.env.example`):

```bash
POSTGRES_URL=postgres://user:pass@host:5432/dbname
MYSQL_URL=mysql://user:pass@host:3306/dbname
MONGODB_URL=mongodb://user:pass@host:27017/?directConnection=true
MONGODB_DATABASE=default
REDIS_URL=redis://default:pass@host:6379/0
```

---

## 15 — TaskFlow API

**Dependencies:** none (built-in `database.sqlite`)

Demonstrates the `@connect` + `@flow` decorator API introduced in v0.4.0. The full pipeline is composed of three `@connect` steps wired together inside a `@flow`.

```python
from pyconnectors import connect, flow, configure, ConnectorConfig

configure("database.sqlite", ConnectorConfig(params={"database": ":memory:"}))

@connect("database.sqlite")
def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    return "db ready"

@connect("database.sqlite")
def record_event(conn, name: str):
    conn.execute("INSERT INTO events (name) VALUES (?)", (name,))
    return {"recorded": name}

@connect("database.sqlite")
def fetch_events(conn):
    return conn.execute("SELECT * FROM events")

@flow(name="event-pipeline")
def run_pipeline(event: str):
    init_db()
    record_event(name=event)
    return fetch_events()

# Execute the flow
result = run_pipeline(event="deploy-v0.4.0")
print(result.success)            # True
print(result.data)               # [{"id": 1, "name": "deploy-v0.4.0"}]
print(result.metadata["flow"])   # "event-pipeline"
print(f"{result.duration:.4f}s") # total wall-clock time
```

**Key concepts:**
- `configure()` pre-registers a config for a connector type — no import of the connector module needed
- `@connect` wraps a plain function: the live connector instance is injected as the **first** argument
- Every `@connect` call returns a `ConnectorResult`, even on exception (`success=False`)
- `@flow` measures total duration and injects `metadata["flow"]` into the returned result
- Config resolution order: `_config=` at call-time → `config=` on decorator → `configure()` store

See [ADR-004](changelog/ADR-004-taskflow-decorators-connect-and-flow.md) for the full design rationale.

---

## Running All Examples

```bash
# Run individually
uv run python examples/01_basic_usage.py
uv run python examples/04_hooks_and_logging.py
uv run python examples/08_database_connectors.py

# Real cloud databases (requires .env with credentials)
uv pip install "pyconnectors[postgresql,mysql,mongodb,redis]" cryptography python-dotenv
uv run python examples/14_real_databases.py

# With optional dependencies
uv pip install "pyconnectors[s3]"
uv run python examples/11_storage_connectors.py

uv pip install "pyconnectors[auth]"
uv run python examples/13_auth_connectors.py
```

---

## Writing Your Own Connector

Every connector follows the same pattern — use `@connector` to register and subclass `BaseConnector`:

```python
from pyconnectors import BaseConnector, connector, ConnectorFactory, ConnectorConfig

@connector("myservice.myconnector")
class MyConnector(BaseConnector):
    """One-line description shown in `con list`."""

    def execute(self, *args, **kwargs):
        # Your logic here — raise exceptions freely; safe_execute() catches them
        response = do_something(*args, **kwargs)
        return response
```

Then use it exactly like any built-in connector:

```python
config = ConnectorConfig(params={"api_key": "secret"})
conn = ConnectorFactory.create("myservice.myconnector", config=config)
result = conn.safe_execute(...)
if result.success:
    print(result.data)
```

Or with the TaskFlow API:

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("myservice.myconnector", ConnectorConfig(params={"api_key": "secret"}))

@connect("myservice.myconnector")
def do_thing(conn, payload: dict):
    return conn.execute(payload)

result = do_thing(payload={"key": "value"})
print(result.success, result.data)
```

See the [architecture guide](architecture.md) for the full class hierarchy and the [contributing guide](../contributing.md) for conventions.
