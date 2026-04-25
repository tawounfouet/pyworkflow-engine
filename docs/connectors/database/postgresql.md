# PostgreSQL (`database.postgresql`)

**Requires:** `psycopg` — `uv pip install "pyconnectors[postgresql]"`

---

## Configuration

Accepts the first non-empty key among:

| Key | Description |
|---|---|
| `dsn` | Postgres connection string |
| `url` | Alias for `dsn` |
| `database_url` | Generic PaaS alias |

---

## Usage

```python
import os
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"url": os.environ["POSTGRES_URL"]})
pg = ConnectorFactory.create("database.postgresql", config=config)

# DDL
pg.safe_execute("""
    CREATE TABLE IF NOT EXISTS users (
        id   SERIAL PRIMARY KEY,
        name TEXT NOT NULL
    )
""")

# DML — positional params use %s
pg.safe_execute("INSERT INTO users (name) VALUES (%s)", ("Alice",))

# Query
result = pg.safe_execute("SELECT id, name FROM users")
if result.success:
    for row in result.data:
        print(row)   # (1, 'Alice')
```
