# HTTP Connectors

Standard connectors for REST APIs and OAuth2-protected resources — zero external dependencies (stdlib `urllib` only). All connectors use `safe_execute()` — never raises, always returns `ConnectorResult`.

| Connector | Key | Description |
|---|---|---|
| [REST](rest.md) | `http.rest` | Generic REST client with API key, Basic, Digest auth and session support |
| [OAuth2 REST](oauth2.md) | `http.oauth2` | Extends `http.rest` — auto-fetches and refreshes Bearer tokens |
