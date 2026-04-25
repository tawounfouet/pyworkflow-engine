# MailerSend (`email.mailersend`)

**Requires:** Nothing (stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `api_key` | MailerSend API token |
| `from_addr` | Verified sender address |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "api_key":   "mlsn...",
    "from_addr": "noreply@my-domain.com",
})
ms = ConnectorFactory.create("email.mailersend", config=config)

result = ms.safe_execute(
    to_addr="user@example.com",
    subject="Hello!",
    body_html="<p>Hello from MailerSend!</p>",
)
print("Sent:", result.success)
```
