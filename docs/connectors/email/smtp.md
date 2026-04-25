# SMTP (`email.smtp`)

Send emails via any SMTP server.

**Requires:** Nothing (stdlib `smtplib`)

---

## Configuration

| Key | Description |
|---|---|
| `host` | SMTP server hostname |
| `port` | SMTP port (e.g. `587` for STARTTLS, `465` for SSL) |
| `user` | SMTP username |
| `password` | SMTP password |
| `from_addr` | Sender address |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "host":      "smtp.example.com",
    "port":      587,
    "user":      "user@example.com",
    "password":  "secret",
    "from_addr": "user@example.com",
})
smtp = ConnectorFactory.create("email.smtp", config=config)

result = smtp.safe_execute(
    to_addr="recipient@example.com",
    subject="Hello!",
    body="Plain text body.",
    body_html="<p>HTML body.</p>",   # optional
)
print("Sent:", result.success)
```

**`execute()` signature:**
```python
execute(to_addr: str, subject: str, body: str, body_html: str | None = None) -> None
```
