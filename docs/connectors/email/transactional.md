# Transactional Email APIs

Send emails via HTTP REST APIs — no SMTP server required.

All transactional connectors share the same `execute()` signature:

```python
execute(to_addr: str, subject: str, body_html: str, body_text: str | None = None) -> dict
```

| Connector | Key | `from_addr` config | Extra config | Dependencies |
|---|---|---|---|---|
| [Resend](resend.md) | `email.resend` | `from_addr` | `api_key` | `uv pip install "pyconnectors[email]"` |
| [Brevo](brevo.md) | `email.brevo` | `from_addr` | `api_key` | stdlib |
| [Mailchimp Transactional](mailchimp.md) | `email.mailchimp` | `from_addr` | `api_key` | stdlib |
| [MailerSend](mailersend.md) | `email.mailersend` | `from_addr` | `api_key` | stdlib |
| [Mailgun](mailgun.md) | `email.mailgun` | `from_addr` | `api_key`, `domain` | stdlib |
| [Amazon SES](ses.md) | `email.ses` | `from_addr` | AWS credentials | `uv pip install "pyconnectors[s3]"` |

---

## Quick example — Resend

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
