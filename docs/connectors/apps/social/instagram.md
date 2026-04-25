# Instagram Graph API (`social.instagram`)

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `access_token` | Instagram User access token (`EAAxxxxx`) |
| `api_version` | Graph API version (default: `v19.0`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"access_token": "EAAxxxxx"})
ig = ConnectorFactory.create("social.instagram", config=config)

# Media list
result = ig.safe_execute("me/media")
print(result.success, result.data)

# Single media details
result = ig.safe_execute("17854360229135492", fields="id,caption,media_type,timestamp")
print(result.data)
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("social.instagram", ConnectorConfig(params={"access_token": "EAAxxxxx"}))

@connect("social.instagram")
def fetch_media(conn):
    return conn.execute("me/media")

result = fetch_media()
print(result.success, result.data)
```
