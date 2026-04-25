# Auth Connectors

Handle token generation, OAuth2 flows, and SSO strategies. All connectors use `safe_execute()` — never raises, always returns `ConnectorResult`.

| Connector | Key | Dependencies |
|---|---|---|
| [JWT](jwt.md) | `auth.jwt` | `uv pip install "pyconnectors[auth]"` (`PyJWT`) |
| [OAuth2](oauth2.md) | `auth.oauth2` | stdlib only |
| [OIDC](oidc.md) | `auth.oidc` | stdlib only |
| [SAML 2.0](saml.md) | `auth.saml` | `python3-saml` |

> `http.oauth2` — OAuth2-aware REST connector — is documented in [http/oauth2.md](../http/oauth2.md).
