import base64
import json
import urllib.parse
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("payment.paypal")
class PayPalConnector(BaseConnector):
    """PayPal REST API Connector using stdlib."""

    def execute(
        self, endpoint: str, data: dict[str, Any] | None = None, method: str = "GET"
    ) -> dict[str, Any]:
        client_id = self.config.params.get("client_id")
        client_secret = self.config.params.get("client_secret")
        environment = self.config.params.get("environment", "sandbox")

        if not all([client_id, client_secret]):
            raise ValueError("PayPalConnector requires 'client_id' and 'client_secret'.")

        base_url = (
            "https://api-m.paypal.com"
            if environment == "live"
            else "https://api-m.sandbox.paypal.com"
        )

        # 1. Fetch OAuth2 Bearer Token
        auth_string = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode(
            "ascii"
        )
        token_req = urllib.request.Request(
            f"{base_url}/v1/oauth2/token",
            data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8"),
            headers={
                "Authorization": f"Basic {auth_string}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(token_req) as token_res:
                token_data = json.loads(token_res.read().decode("utf-8"))
                access_token = token_data.get("access_token")
        except urllib.error.HTTPError as e:
            return {"status": "error", "error": f"Auth failed: {e.read().decode('utf-8')}"}

        # 2. Make Actual API Call
        url = f"{base_url}/{endpoint.lstrip('/')}"
        req_data = json.dumps(data).encode("utf-8") if data else None

        api_req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(api_req) as response:
                response_body = response.read().decode("utf-8")
                return {
                    "status": response.status,
                    "data": json.loads(response_body) if response_body else {},
                }
        except urllib.error.HTTPError as e:
            return {
                "status": e.code,
                "error": json.loads(e.read().decode("utf-8")) if e.read() else str(e),
            }
