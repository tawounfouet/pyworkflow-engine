# Connectors — Reference

All connectors follow the same contract:

- Instantiate via `ConnectorFactory.create("category.name", config=...)`.
- Call `safe_execute(...)` — **never raises**, always returns a `ConnectorResult`.
- Call `execute(...)` directly when you want raw exceptions.
- Use `test_connection()` to validate credentials cheaply.

---

## Directory

| Category | Connectors | Folder |
|---|---|---|
| **apps/fitness** | Strava | [`apps/fitness/`](apps/fitness/) |
| **apps/payment** | Stripe, PayPal | [`apps/payment/`](apps/payment/) |
| **apps/social** | Facebook, Instagram, LinkedIn, Slack, TikTok, Twitter, WhatsApp | [`apps/social/`](apps/social/) |
| **auth** | JWT, OAuth2, OIDC, SAML | [`auth/`](auth/) |
| **database** | PostgreSQL, MySQL, MongoDB, Redis, SQLite | [`database/`](database/) |
| **email** | SMTP, IMAP, POP3, Gmail, Outlook, Yahoo, Resend, Brevo, Mailchimp, MailerSend, Mailgun, SES | [`email/`](email/) |
| **http** | REST, OAuth2 REST | [`http/`](http/) |
| **storage** | S3, DigitalOcean, Hetzner, OVH, MinIO, GCS, Azure Blob, ADLS, Cloudinary | [`storage/`](storage/) |

---

## Common patterns

### Factory + safe_execute

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"key": "value"})
conn = ConnectorFactory.create("category.name", config=config)

result = conn.safe_execute(...)
if result.success:
    print(result.data)
else:
    print(result.error)
```

### TaskFlow — @connect / @flow

```python
from pyconnectors import connect, flow, configure, ConnectorConfig

configure("category.name", ConnectorConfig(params={"key": "value"}))

@connect("category.name")
def my_step(conn, arg: str):
    return conn.execute(arg)

@flow(name="my-flow")
def run():
    return my_step(arg="hello")

result = run()
print(result.success, result.metadata["flow"])
```

### ConnectorResult fields

| Field | Type | Description |
|---|---|---|
| `success` | `bool` | `True` on success |
| `data` | `Any` | Parsed response / return value |
| `error` | `str \| None` | Error message on failure |
| `duration` | `float` | Wall-clock time in seconds |
| `metadata` | `dict` | Extra context (flow name, etc.) |
