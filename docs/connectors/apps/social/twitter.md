# Twitter / X API v2 (`social.twitter`)

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `bearer_token` | App-only Bearer Token (`AAAAAAAAAAAAAAAAAAAxxxx`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"bearer_token": "AAAAAAAAAAAAAAAAAAAxxxx"})
tw = ConnectorFactory.create("social.twitter", config=config)

# Lookup the authenticated user
result = tw.safe_execute("users/me")
if result.success:
    print("User:", result.data)
else:
    print("Failed:", result.error)

# Recent tweets by user ID
result = tw.safe_execute("users/123456/tweets", max_results=10)
for tweet in result.data.get("data", []):
    print(tweet["text"])
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("social.twitter", ConnectorConfig(params={
    "bearer_token": "AAAAAAAAAAAAAAAAAAAxxxx",
}))

@connect("social.twitter")
def get_me(conn):
    return conn.execute("users/me")

result = get_me()
print(result.success, result.data)
```
