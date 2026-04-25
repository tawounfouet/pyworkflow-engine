# SAML 2.0 (`auth.saml`)

Perform SAML 2.0 authentication as a Service Provider (SP).

**Requires:** `python3-saml`

---

## Configuration

| Key | Description |
|---|---|
| `saml_settings` | Full `python3-saml` settings dict (SP + IdP metadata) |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "saml_settings": {
        "strict": True,
        "sp": {
            "entityId": "https://myapp.com/sp",
            "assertionConsumerService": {
                "url": "https://myapp.com/acs",
            },
        },
        "idp": {
            "entityId": "https://idp.example.com",
            "singleSignOnService": {
                "url": "https://idp.example.com/sso",
            },
            "x509cert": "MIIC...",
        },
    }
})
saml = ConnectorFactory.create("auth.saml", config=config)

# Process the IdP POST response (e.g. in a web framework callback)
result = saml.safe_execute(request_data, action="process_response")
print(result.data["attributes"])
```

Refer to the [python3-saml documentation](https://github.com/SAML-Toolkits/python3-saml) for the full settings schema.
