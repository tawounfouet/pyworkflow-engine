# MySQL (`database.mysql`)

**Requires:** `pymysql` + `cryptography` — `uv pip install "pyconnectors[mysql]" cryptography`

> `cryptography` is required when the server uses `caching_sha2_password` (MySQL 8 default).

---

## Configuration

URL or individual parameters (first non-empty wins):

| Key | Description |
|---|---|
| `url` / `database_url` / `mysql_url` | MySQL connection URL |
| `host` | Default `localhost` |
| `port` | Default `3306` |
| `user` | MySQL username |
| `password` | MySQL password |
| `database` | Database name |

---

## Usage

```python
import os
from pyconnectors import ConnectorFactory, ConnectorConfig

# From a URL
config = ConnectorConfig(params={"url": os.environ["MYSQL_URL"]})
mysql = ConnectorFactory.create("database.mysql", config=config)

# From individual params
config = ConnectorConfig(params={
    "host":     os.environ["MYSQL_HOST"],
    "port":     int(os.environ["MYSQL_PORT"]),
    "user":     os.environ["MYSQL_USER"],
    "password": os.environ["MYSQL_PASSWORD"],
    "database": os.environ["MYSQL_DATABASE"],
})
mysql = ConnectorFactory.create("database.mysql", config=config)

result = mysql.safe_execute("SELECT VERSION()")
print(result.data)
```
