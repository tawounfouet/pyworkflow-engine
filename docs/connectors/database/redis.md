# Redis (`database.redis`)

**Requires:** `redis-py` — `uv pip install "pyconnectors[redis]"`

---

## Configuration

URL or individual parameters (first non-empty wins):

| Key | Description |
|---|---|
| `url` / `database_url` / `redis_url` | Redis URL |
| `host` | Default `localhost` |
| `port` | Default `6379` |
| `db` | Default `0` |

---

## Usage

```python
import os
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"url": os.environ["REDIS_URL"]})
r = ConnectorFactory.create("database.redis", config=config)

r.safe_execute("set", key="greeting", value="hello")

result = r.safe_execute("get", key="greeting")
print(result.data)   # "hello"

r.safe_execute("delete", key="greeting")
```

**Supported actions:** `set`, `get`, `delete`
