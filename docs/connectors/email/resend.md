# Resend (`email.resend`)

**Requires:** `uv pip install "pyconnectors[email]"`

---

## Configuration

| Key | Description |
|---|---|
| `api_key` | Resend API key (`re_...`) |
| `from_addr` | Verified sender address or domain |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "api_key":   "re_123...",
    "from_addr": "info@my-domain.com",
})
resend = ConnectorFactory.create("email.resend", config=config)

result = resend.safe_execute(
    to_addr="user@example.com",
    subject="Hello!",
    body_html="<h1>Hello from PyConnectors!</h1>",
    body_text="Hello from PyConnectors!",
)
print("Sent:", result.success, result.data)
```
