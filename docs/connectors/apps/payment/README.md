# Payment Connectors

Automate payment processing and billing operations. All connectors use `safe_execute()` — never raises, always returns `ConnectorResult`.

| Connector | Key | Dependencies |
|---|---|---|
| [Stripe](stripe.md) | `payment.stripe` | `uv pip install "pyconnectors[payment]"` |
| [PayPal](paypal.md) | `payment.paypal` | stdlib only |
