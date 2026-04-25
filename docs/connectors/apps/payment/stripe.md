# Stripe (`payment.stripe`)

Dynamic gateway to the official [Stripe Python SDK](https://stripe.com/docs/api). Any Stripe resource and action are accessible via `execute(resource, action, **kwargs)`.

**Requires:** `stripe` — `uv pip install "pyconnectors[payment]"`

---

## Configuration

| Key | Description |
|---|---|
| `api_key` | Stripe secret key (`sk_test_...` or `sk_live_...`) |

---

## Usage

**`execute()` signature:**
```python
execute(resource: str, action: str, **kwargs) -> Any
```

Maps directly to `stripe.<Resource>.<action>(**kwargs)`.

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={"api_key": "sk_test_12345"})
stripe_conn = ConnectorFactory.create("payment.stripe", config=config)

# Create a customer
result = stripe_conn.safe_execute("Customer", "create", email="test@example.com", name="John Doe")
if result.success:
    print("Customer ID:", result.data["id"])

# List customers
result = stripe_conn.safe_execute("Customer", "list", limit=10)
for customer in result.data["data"]:
    print(customer["email"])

# Create a Checkout Session
result = stripe_conn.safe_execute(
    "checkout.Session",
    "create",
    payment_method_types=["card"],
    mode="payment",
    success_url="https://example.com/success",
    cancel_url="https://example.com/cancel",
    line_items=[{
        "price_data": {
            "currency": "usd",
            "product_data": {"name": "T-shirt"},
            "unit_amount": 2000,
        },
        "quantity": 1,
    }],
)
if result.success:
    print("Checkout URL:", result.data["url"])
```

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig

configure("payment.stripe", ConnectorConfig(params={"api_key": "sk_test_12345"}))

@connect("payment.stripe")
def create_customer(conn, email: str, name: str):
    return conn.execute("Customer", "create", email=email, name=name)

@connect("payment.stripe")
def create_checkout(conn, customer_id: str, amount_cents: int):
    return conn.execute(
        "checkout.Session",
        "create",
        customer=customer_id,
        payment_method_types=["card"],
        mode="payment",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Order"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
    )

customer = create_customer(email="user@example.com", name="Alice")
if customer.success:
    checkout = create_checkout(customer_id=customer.data["id"], amount_cents=4900)
    print("Checkout URL:", checkout.data["url"])
```
