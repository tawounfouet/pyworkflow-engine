# TikTok Display API (`social.tiktok`)

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `access_token` | OAuth2 access token (`act.xxxxx`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"access_token": "act.xxxxx"})
tk = ConnectorFactory.create("social.tiktok", config=config)

# User info
result = tk.safe_execute("user/info/")
print(result.success, result.data)

# User videos
result = tk.safe_execute("video/list/")
print(result.data)
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("social.tiktok", ConnectorConfig(params={"access_token": "act.xxxxx"}))

@connect("social.tiktok")
def get_user_info(conn):
    return conn.execute("user/info/")

result = get_user_info()
print(result.success, result.data)
```
