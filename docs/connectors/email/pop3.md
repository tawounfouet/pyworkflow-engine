# POP3 (`email.pop3`)

Fetch basic inbox stats via POP3.

**Requires:** Nothing (stdlib `poplib`)

---

## Configuration

| Key | Description |
|---|---|
| `host` | POP3 server hostname |
| `port` | POP3 port (default `995`) |
| `user` | POP3 username |
| `password` | POP3 password |
| `use_ssl` | `True` (default) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "host":     "pop.example.com",
    "port":     995,
    "user":     "user@example.com",
    "password": "secret",
})
pop3 = ConnectorFactory.create("email.pop3", config=config)

result = pop3.safe_execute()
print(result.success, result.data)
```
