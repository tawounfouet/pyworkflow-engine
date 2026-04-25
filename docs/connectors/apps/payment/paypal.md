# PayPal (`payment.paypal`)

Interacts with the [PayPal REST API](https://developer.paypal.com/api/rest/). The OAuth2 access token is fetched automatically from your client credentials.

**Requires:** Nothing (uses stdlib `urllib`)

---

## Configuration

| Key | Description |
|---|---|
| `client_id` | PayPal application Client ID |
| `client_secret` | PayPal application Client Secret |
| `environment` | `"sandbox"` (default) or `"live"` |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "client_id":     "CLIENT_ID",
    "client_secret": "SECRET",
    "environment":   "sandbox",
})
paypal = ConnectorFactory.create("payment.paypal", config=config)

# Create an Order
result = paypal.safe_execute(
    "v2/checkout/orders",
    data={
        "intent": "CAPTURE",
        "purchase_units": [{"amount": {"currency_code": "USD", "value": "100.00"}}],
    },
    method="POST",
)
if result.success:
    print("Order ID:", result.data["id"])

# Capture an Order
result = paypal.safe_execute(
    f"v2/checkout/orders/{order_id}/capture",
    method="POST",
)
print(result.success, result.data["status"])
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("payment.paypal", ConnectorConfig(params={
    "client_id":     "CLIENT_ID",
    "client_secret": "SECRET",
    "environment":   "sandbox",
}))

@connect("payment.paypal")
def create_order(conn, amount_usd: str):
    return conn.execute(
        "v2/checkout/orders",
        data={
            "intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": "USD", "value": amount_usd}}],
        },
        method="POST",
    )

result = create_order(amount_usd="49.99")
print(result.success, result.data["id"])
```
