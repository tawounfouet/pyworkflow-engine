# OpenID Connect (`auth.oidc`)

Generate authorization URLs and handle authorization-code-to-token exchanges.

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `issuer` | IdP base URL (e.g. `https://idp.example.com`) |
| `client_id` | OIDC client ID |
| `client_secret` | OIDC client secret |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "issuer":        "https://idp.example.com",
    "client_id":     "client_id",
    "client_secret": "client_secret",
})
oidc = ConnectorFactory.create("auth.oidc", config=config)

# Generate the login URL to redirect the user
result = oidc.safe_execute("auth_url", redirect_uri="https://myapp.com/callback")
print(result.data)   # {"url": "https://idp.example.com/authorize?..."}

# Exchange authorization code for tokens (callback handler)
result = oidc.safe_execute(
    "exchange_code",
    auth_code="code_from_callback",
    redirect_uri="https://myapp.com/callback",
)
print(result.data)   # {"access_token": "...", "id_token": "..."}
```
