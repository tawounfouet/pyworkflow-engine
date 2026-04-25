# Mailgun (`email.mailgun`)

**Requires:** Nothing (stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `api_key` | Mailgun private API key |
| `domain` | Sending domain (e.g. `mg.my-domain.com`) |
| `from_addr` | Sender address |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "api_key":   "key-...",
    "domain":    "mg.my-domain.com",
    "from_addr": "noreply@my-domain.com",
})
mg = ConnectorFactory.create("email.mailgun", config=config)

result = mg.safe_execute(
    to_addr="user@example.com",
    subject="Hello!",
    body_html="<p>Hello from Mailgun!</p>",
    body_text="Hello from Mailgun!",
)
print("Sent:", result.success)
```
