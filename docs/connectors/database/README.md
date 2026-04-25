# Database Connectors

Connect to SQL and NoSQL databases. All connectors use `safe_execute()` — never raises, always returns `ConnectorResult`.

Every connector accepts a **connection URL** (PaaS / `.env` style) as well as individual host/port/user parameters.

| Connector | Key | Driver | Install extra |
|---|---|---|---|
| [PostgreSQL](postgresql.md) | `database.postgresql` | `psycopg` | `uv pip install "pyconnectors[postgresql]"` |
| [MySQL](mysql.md) | `database.mysql` | `pymysql` | `uv pip install "pyconnectors[mysql]" cryptography` |
| [MongoDB](mongodb.md) | `database.mongodb` | `pymongo` | `uv pip install "pyconnectors[mongodb]"` |
| [Redis](redis.md) | `database.redis` | `redis-py` | `uv pip install "pyconnectors[redis]"` |
| [SQLite](sqlite.md) | `database.sqlite` | stdlib `sqlite3` | — |

---

## Environment variables (`.env`)

```bash
POSTGRES_URL=postgres://user:pass@host:5432/dbname
MYSQL_URL=mysql://user:pass@host:3306/dbname
MONGODB_URL=mongodb://user:pass@host:27017/?directConnection=true
MONGODB_DATABASE=default
REDIS_URL=redis://default:pass@host:6379/0
SQLITE_DATABASE=./data/app.db
```

Load with `python-dotenv`:

```python
from dotenv import load_dotenv
load_dotenv()
```

---

## TaskFlow — `@connect`

All database connectors work with the `@connect` decorator:

```python
from pyconnectors import connect, flow, configure, ConnectorConfig

configure("database.sqlite", ConnectorConfig(params={"database": ":memory:"}))

@connect("database.sqlite")
def setup(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)")

@connect("database.sqlite")
def add_user(conn, name: str):
    conn.execute("INSERT INTO users (name) VALUES (?)", (name,))
    return {"added": name}

@connect("database.sqlite")
def list_users(conn):
    return conn.execute("SELECT * FROM users")

@flow(name="user-pipeline")
def run(name: str):
    setup()
    add_user(name=name)
    return list_users()

result = run(name="Alice")
print(result.data)               # [{"id": 1, "name": "Alice"}]
print(result.metadata["flow"])   # "user-pipeline"
```
