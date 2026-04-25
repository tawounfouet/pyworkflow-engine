# Yahoo Mail (`email.yahoo`)

Pre-configured SMTP wrapper for Yahoo Mail.

**Requires:** Nothing (stdlib `smtplib`)

> With 2FA enabled, generate an **App Password** from [security.yahoo.com](https://security.yahoo.com).

---

## Configuration

| Key | Description |
|---|---|
| `user` | Yahoo address (`me@yahoo.com`) |
| `password` | App Password |
| `from_addr` | Sender address (defaults to `user`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "user":     "me@yahoo.com",
    "password": "app_password",
})
yahoo = ConnectorFactory.create("email.yahoo", config=config)

result = yahoo.safe_execute(
    to_addr="recipient@example.com",
    subject="Hello!",
    body="Plain text body.",
)
print("Sent:", result.success)
```
