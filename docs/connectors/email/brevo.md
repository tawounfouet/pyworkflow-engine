# Brevo (`email.brevo`)

**Requires:** Nothing (stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `api_key` | Brevo API key |
| `from_addr` | Verified sender address |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "api_key":   "xkeysib-...",
    "from_addr": "noreply@my-domain.com",
})
brevo = ConnectorFactory.create("email.brevo", config=config)

result = brevo.safe_execute(
    to_addr="user@example.com",
    subject="Hello!",
    body_html="<p>Hello from Brevo!</p>",
)
print("Sent:", result.success)
```
