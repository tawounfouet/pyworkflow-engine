import json
import urllib.parse
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("auth.oidc")
class OIDCConnector(BaseConnector):
    """OpenID Connect (OIDC) Connector."""

    def execute(
        self, action: str, auth_code: str | None = None, redirect_uri: str | None = None
    ) -> dict[str, Any]:
        issuer = self.config.params.get("issuer")
        client_id = self.config.params.get("client_id")
        client_secret = self.config.params.get("client_secret")

        if not all([issuer, client_id, client_secret]):
            raise ValueError("OIDCConnector requires 'issuer', 'client_id', and 'client_secret'.")

        # Discover endpoints (Simplified)
        # Normally you would fetch `issuer + "/.well-known/openid-configuration"`
        # But we assume the user provided endpoints explicitly or they follow standard patterns
        token_endpoint = self.config.params.get(
            "token_endpoint", f"{issuer}/protocol/openid-connect/token"
        )
        auth_endpoint = self.config.params.get(
            "authorization_endpoint", f"{issuer}/protocol/openid-connect/auth"
        )
        redirect_uri = redirect_uri or self.config.params.get("redirect_uri")

        if action == "auth_url":
            if not redirect_uri:
                raise ValueError("redirect_uri is required to generate auth_url.")
            params = {
                "client_id": client_id,
                "response_type": "code",
                "scope": "openid profile email",
                "redirect_uri": redirect_uri,
            }
            query = urllib.parse.urlencode(params)
            return {"status": "success", "url": f"{auth_endpoint}?{query}"}

        elif action == "exchange_code":
            if not auth_code or not redirect_uri:
                raise ValueError("auth_code and redirect_uri are required to exchange_code.")

            payload = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            }
            req_data = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(
                token_endpoint,
                data=req_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )

            try:
                with urllib.request.urlopen(req) as response:
                    return {
                        "status": "success",
                        "data": json.loads(response.read().decode("utf-8")),
                    }
            except urllib.error.HTTPError as e:
                return {"status": "error", "error": json.loads(e.read().decode("utf-8"))}
        else:
            raise ValueError(f"Action '{action}' is not supported.")
