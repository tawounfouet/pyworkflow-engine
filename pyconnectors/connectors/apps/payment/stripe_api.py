from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import stripe
except ImportError:
    stripe = None


@connector("payment.stripe")
class StripeConnector(BaseConnector):
    """Stripe API Connector."""

    def execute(self, resource: str, action: str, **kwargs: Any) -> Any:
        if stripe is None:
            raise ImportError(
                "Stripe connector requires stripe SDK. Install with: pip install pyconnectors[payment]"
            )

        api_key = self.config.params.get("api_key")
        if not api_key:
            raise ValueError("StripeConnector requires 'api_key' in configuration.")

        stripe.api_key = api_key

        # Support basic resources dynamically
        # e.g. resource="Customer", action="create", email="test@test.com"
        # Maps to stripe.Customer.create(email="test@test.com")
        try:
            stripe_resource = getattr(stripe, resource)
            stripe_method = getattr(stripe_resource, action)
            return stripe_method(**kwargs)
        except AttributeError as e:
            raise ValueError(f"Stripe resource '{resource}' or action '{action}' not found: {e}")
        except Exception as e:
            return {"error": str(e)}
