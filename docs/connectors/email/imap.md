# IMAP (`email.imap`)

Search and read emails via IMAP.

**Requires:** Nothing (stdlib `imaplib`)

---

## Configuration

| Key | Description |
|---|---|
| `host` | IMAP server hostname |
| `port` | IMAP port (default `993`) |
| `user` | IMAP username |
| `password` | IMAP password |
| `use_ssl` | `True` (default) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "host":     "imap.example.com",
    "port":     993,
    "user":     "user@example.com",
    "password": "secret",
})
imap = ConnectorFactory.create("email.imap", config=config)

result = imap.safe_execute(search_criteria="UNSEEN")
if result.success:
    for msg in result.data:
        print(msg["subject"], msg["from"])
```
