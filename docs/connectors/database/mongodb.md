# MongoDB (`database.mongodb`)

**Requires:** `pymongo` — `uv pip install "pyconnectors[mongodb]"`

---

## Configuration

| Key | Description |
|---|---|
| `uri` / `url` / `database_url` | MongoDB connection URI |
| `database` | Target database name (**required**) |

---

## Usage

```python
import os
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "url":      os.environ["MONGODB_URL"],
    "database": os.environ.get("MONGODB_DATABASE", "default"),
})
mongo = ConnectorFactory.create("database.mongodb", config=config)

# insert_one
mongo.safe_execute("users", "insert_one", data={"name": "Alice", "role": "admin"})

# find
result = mongo.safe_execute("users", "find", query={"role": "admin"})
for doc in result.data:
    print(doc)

# find_one
result = mongo.safe_execute("users", "find_one", query={"name": "Alice"})
print(result.data)
```

**Supported actions:** `find`, `find_one`, `insert_one`
