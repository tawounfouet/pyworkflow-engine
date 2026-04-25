# Facebook Graph API (`social.facebook`)

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `access_token` | User or Page access token (`EAAxxxxx`) |
| `api_version` | Graph API version (default: `v19.0`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"access_token": "EAAxxxxx"})
fb = ConnectorFactory.create("social.facebook", config=config)

# Current user
result = fb.safe_execute("me")
print(result.success, result.data)

# Page posts
result = fb.safe_execute("me/posts", fields="id,message,created_time", limit=10)
for post in result.data.get("data", []):
    print(post["message"])
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("social.facebook", ConnectorConfig(params={"access_token": "EAAxxxxx"}))

@connect("social.facebook")
def get_profile(conn):
    return conn.execute("me")

result = get_profile()
print(result.success, result.data)
```
