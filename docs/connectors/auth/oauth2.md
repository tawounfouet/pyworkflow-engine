# OAuth2 (`auth.oauth2`)

Handle basic token exchanges: client credentials and refresh token grants.

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `token_url` | Token endpoint URL |
| `client_id` | OAuth2 client ID |
| `client_secret` | OAuth2 client secret |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "token_url":     "https://auth.server.com/token",
    "client_id":     "client_abc",
    "client_secret": "secret_xyz",
})
oauth2 = ConnectorFactory.create("auth.oauth2", config=config)

# Client credentials grant
result = oauth2.safe_execute("client_credentials")
print(result.data["access_token"])

# Refresh a token
result = oauth2.safe_execute("refresh_token", refresh_token="old_refresh_token")
print(result.data["access_token"])
```

> For an OAuth2-aware REST connector that automatically injects the Bearer token into API requests, see [http/oauth2.md](../http/oauth2.md).
