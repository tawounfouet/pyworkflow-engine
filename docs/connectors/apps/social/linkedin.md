# LinkedIn REST API (`social.linkedin`)

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `access_token` | OAuth2 access token (`AQVxxxx`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"access_token": "AQVxxxx"})
li = ConnectorFactory.create("social.linkedin", config=config)

# Current user profile
result = li.safe_execute("me")
print(result.success, result.data)

# Share a post (UGC Post)
result = li.safe_execute(
    "ugcPosts",
    method="POST",
    data={
        "author": "urn:li:person:ABC123",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": "Hello from PyConnectors!"},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    },
)
print(result.success, result.data)
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("social.linkedin", ConnectorConfig(params={"access_token": "AQVxxxx"}))

@connect("social.linkedin")
def get_profile(conn):
    return conn.execute("me")

result = get_profile()
print(result.success, result.data)
```
