# Slack Webhooks (`social.slack`)

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `webhook_url` | Incoming Webhook URL from the Slack app settings |

Create a webhook at [api.slack.com/apps](https://api.slack.com/apps) → your app → **Incoming Webhooks**.

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "webhook_url": "https://hooks.slack.com/services/T.../B.../xxx",
})
slack = ConnectorFactory.create("social.slack", config=config)

# Send a message
result = slack.safe_execute("Hello from PyConnectors! 🚀")
print("Sent:", result.success)

# Send to a specific channel (must be allowed by the webhook config)
result = slack.safe_execute("Deployment complete ✅", channel="#deployments")
print("Sent:", result.success)
```

**`execute()` signature:**
```python
execute(message: str, channel: str | None = None) -> dict
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("social.slack", ConnectorConfig(params={
    "webhook_url": "https://hooks.slack.com/services/T.../B.../xxx",
}))

@connect("social.slack")
def notify_deploy(conn, version: str):
    return conn.execute(f"✅ Deployed pyconnectors v{version}")

result = notify_deploy(version="1.0.0")
print(result.success, result.duration)
```
