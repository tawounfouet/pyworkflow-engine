# SQLite (`database.sqlite`)

**Requires:** Nothing (stdlib `sqlite3`)

A single persistent connection is kept open across all `execute()` calls — `:memory:` databases survive between calls without data loss.

---

## Configuration

| Key | Description |
|---|---|
| `database` | Path to SQLite file, or `:memory:` (default) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

# In-memory — fast, zero setup
config = ConnectorConfig(params={"database": ":memory:"})
sqlite = ConnectorFactory.create("database.sqlite", config=config)

sqlite.safe_execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
sqlite.safe_execute("INSERT INTO items (name) VALUES (?)", ("Widget",))

result = sqlite.safe_execute("SELECT * FROM items")
print(result.data)   # [{"id": 1, "name": "Widget"}]

sqlite.close()   # release the connection explicitly
```

> Results are returned as **lists of dicts** (column name → value).

---

## Persistent file

```python
config = ConnectorConfig(params={"database": "/tmp/myapp.db"})
sqlite = ConnectorFactory.create("database.sqlite", config=config)
```
