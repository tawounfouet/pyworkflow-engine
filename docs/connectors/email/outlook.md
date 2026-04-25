# Outlook (`email.outlook`)

Pre-configured SMTP wrapper for Outlook / Hotmail / Microsoft 365.

**Requires:** Nothing (stdlib `smtplib`)

> With 2FA enabled, generate an **App Password** from your Microsoft account security settings.

---

## Configuration

| Key | Description |
|---|---|
| `user` | Outlook address (`me@outlook.com`) |
| `password` | App Password |
| `from_addr` | Sender address (defaults to `user`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "user":     "me@outlook.com",
    "password": "app_password",
})
outlook = ConnectorFactory.create("email.outlook", config=config)

result = outlook.safe_execute(
    to_addr="recipient@example.com",
    subject="Hello!",
    body="Plain text body.",
)
print("Sent:", result.success)
```
