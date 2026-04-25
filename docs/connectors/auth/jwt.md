# JWT (`auth.jwt`)

Generate and validate JSON Web Tokens securely.

**Requires:** `PyJWT` — `uv pip install "pyconnectors[auth]"`

---

## Configuration

| Key | Description |
|---|---|
| `secret_key` | HMAC secret or RSA/EC private key |
| `algorithm` | Signing algorithm (default: `HS256`) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"secret_key": "my_secret", "algorithm": "HS256"})
jwt_conn = ConnectorFactory.create("auth.jwt", config=config)

# Encode
result = jwt_conn.safe_execute("encode", payload={"user_id": 123})
token = result.data["token"]
print(token)

# Decode
result = jwt_conn.safe_execute("decode", token=token)
print(result.data["payload"])   # {"user_id": 123}
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("auth.jwt", ConnectorConfig(params={"secret_key": "my_secret"}))

@connect("auth.jwt")
def issue_token(conn, user_id: int):
    return conn.execute("encode", payload={"user_id": user_id})

@connect("auth.jwt")
def verify_token(conn, token: str):
    return conn.execute("decode", token=token)

token_result = issue_token(user_id=42)
verified = verify_token(token=token_result.data["token"])
print(verified.data["payload"])   # {"user_id": 42}
```
