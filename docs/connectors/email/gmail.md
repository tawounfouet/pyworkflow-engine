# Gmail (`email.gmail`)

Pre-configured SMTP wrapper for Gmail.

**Requires:** Nothing (stdlib `smtplib`)

> With 2FA enabled, generate an **App Password** from [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) — do not use your main password.

---

## Configuration

| Key | Description |
|---|---|
| `user` | Gmail address (`me@gmail.com`) |
| `password` | App Password (not your main password) |
| `from_addr` | Sender address (defaults to `user`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "user":     "me@gmail.com",
    "password": "app_password",
})
gmail = ConnectorFactory.create("email.gmail", config=config)

result = gmail.safe_execute(
    to_addr="friend@example.com",
    subject="Hello from PyConnectors!",
    body="Plain text body.",
    body_html="<p>HTML body.</p>",   # optional
)
print("Sent:", result.success)
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("email.gmail", ConnectorConfig(params={
    "user":     "me@gmail.com",
    "password": "app_password",
}))

@connect("email.gmail")
def send_welcome(conn, to_addr: str, username: str):
    return conn.execute(
        to_addr=to_addr,
        subject=f"Welcome, {username}!",
        body=f"Hi {username}, welcome aboard.",
    )

result = send_welcome(to_addr="new@example.com", username="Alice")
print(result.success, result.duration)
```
