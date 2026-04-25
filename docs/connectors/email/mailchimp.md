# Mailchimp Transactional (`email.mailchimp`)

**Requires:** Nothing (stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `api_key` | Mailchimp Transactional (Mandrill) API key |
| `from_addr` | Verified sender address |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "api_key":   "md-...",
    "from_addr": "noreply@my-domain.com",
})
mc = ConnectorFactory.create("email.mailchimp", config=config)

result = mc.safe_execute(
    to_addr="user@example.com",
    subject="Hello!",
    body_html="<p>Hello from Mailchimp Transactional!</p>",
)
print("Sent:", result.success)
```
