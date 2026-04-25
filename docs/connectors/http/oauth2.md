# OAuth2 REST (`http.oauth2`)

Extends `http.rest` — automatically fetches an OAuth2 Bearer token on the first request and reuses / refreshes it on subsequent calls.

**Requires:** Nothing (stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `oauth2_token_url` | Token endpoint URL |
| `oauth2_client_id` | Client ID |
| `oauth2_client_secret` | Client secret |

All `http.rest` configuration keys are also accepted (base URL, session, etc.).

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "oauth2_token_url":     "https://auth.example.com/oauth/token",
    "oauth2_client_id":     "client_123",
    "oauth2_client_secret": "secret_abc",
})
api = ConnectorFactory.create("http.oauth2", config=config)

# Token is fetched automatically and injected as "Authorization: Bearer …"
result = api.safe_execute("GET", "https://api.example.com/protected/resource")
print(result.success, result.data)
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("http.oauth2", ConnectorConfig(params={
    "oauth2_token_url":     "https://auth.example.com/oauth/token",
    "oauth2_client_id":     "client_123",
    "oauth2_client_secret": "secret_abc",
}))

@connect("http.oauth2")
def fetch_protected(conn, path: str):
    return conn.execute("GET", f"https://api.example.com/{path}")

result = fetch_protected(path="users/me")
print(result.success, result.data)
```

---

> For the standalone OAuth2 token-exchange connector (without the HTTP wrapper), see [auth/oauth2.md](../auth/oauth2.md).
