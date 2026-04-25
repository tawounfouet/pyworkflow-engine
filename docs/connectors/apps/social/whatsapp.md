# WhatsApp Cloud API (`social.whatsapp`)

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `access_token` | Meta / WhatsApp Business access token (`EAAxxxxx`) |
| `phone_number_id` | Sender phone number ID from the Meta dashboard |
| `api_version` | API version (default: `v19.0`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "access_token":    "EAAxxxxx",
    "phone_number_id": "1234567890",
})
wa = ConnectorFactory.create("social.whatsapp", config=config)

# Send a text message
result = wa.safe_execute("15551234567", "Hello from PyConnectors! 👋")
print("Sent:", result.success)
```

**`execute()` signature:**
```python
execute(to: str, message: str) -> dict
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("social.whatsapp", ConnectorConfig(params={
    "access_token":    "EAAxxxxx",
    "phone_number_id": "1234567890",
}))

@connect("social.whatsapp")
def send_alert(conn, phone: str, text: str):
    return conn.execute(phone, text)

result = send_alert(phone="15551234567", text="Pipeline finished ✅")
print(result.success, result.duration)
```
