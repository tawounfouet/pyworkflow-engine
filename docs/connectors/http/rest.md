# REST (`http.rest`)

Generic REST client with flexible authentication support.

**Requires:** Nothing (stdlib `urllib`)

---

## Configuration

| Auth method | Keys |
|---|---|
| **API key — header** | `api_key`, `api_key_in: "header"` (default), `api_key_header` (default `"Authorization"`), `api_key_prefix` (default `"Bearer"`) |
| **API key — query param** | `api_key`, `api_key_in: "query"`, `api_key_query_param` (default `"api_key"`) |
| **Basic / Digest** | `auth_type: "basic"\|"digest"`, `username`, `password`, `base_url` |
| **Session (cookies)** | `use_session: true` |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

# Anonymous GET
http = ConnectorFactory.create("http.rest", config=ConnectorConfig())
result = http.safe_execute("GET", "https://api.github.com/users/octocat")
print(result.success, result.data)

# Bearer token
config = ConnectorConfig(params={
    "api_key":        "my_secret_token",
    "api_key_header": "Authorization",
    "api_key_prefix": "Bearer",
})
http = ConnectorFactory.create("http.rest", config=config)
result = http.safe_execute("GET", "https://api.example.com/protected")

# Basic auth + persistent session
config = ConnectorConfig(params={
    "auth_type": "basic",
    "username":  "admin",
    "password":  "password123",
    "base_url":  "https://httpbin.org",
    "use_session": True,
})
http = ConnectorFactory.create("http.rest", config=config)
http.safe_execute("GET", "https://httpbin.org/basic-auth/admin/password123")
result = http.safe_execute("GET", "https://httpbin.org/cookies")

# POST with JSON body
http = ConnectorFactory.create("http.rest", config=ConnectorConfig())
result = http.safe_execute(
    "POST",
    "https://jsonplaceholder.typicode.com/posts",
    data={"title": "Hello", "body": "World", "userId": 1},
)
print(result.data)   # {"id": 101, ...}
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("http.rest", ConnectorConfig(params={"api_key": "my_token"}))

@connect("http.rest")
def get_user(conn, user_id: int):
    return conn.execute("GET", f"https://api.example.com/users/{user_id}")

result = get_user(user_id=42)
print(result.success, result.data)
```
