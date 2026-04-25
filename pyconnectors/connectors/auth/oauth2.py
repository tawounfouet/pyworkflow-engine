import json
import urllib.parse
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("auth.oauth2")
class OAuth2Connector(BaseConnector):
    """OAuth2 standard flows (Client Credentials, Refresh Token) using stdlib."""

    def execute(self, action: str, refresh_token: str | None = None) -> dict[str, Any]:
        token_url = self.config.params.get("token_url")
        client_id = self.config.params.get("client_id")
        client_secret = self.config.params.get("client_secret")

        if not all([token_url, client_id, client_secret]):
            raise ValueError(
                "OAuth2Connector requires 'token_url', 'client_id', and 'client_secret'."
            )

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
        }

        if action == "client_credentials":
            payload["grant_type"] = "client_credentials"
            scopes = self.config.params.get("scopes")
            if scopes:
                payload["scope"] = " ".join(scopes)

        elif action == "refresh_token":
            if not refresh_token:
                raise ValueError("refresh_token must be provided for 'refresh_token' action.")
            payload["grant_type"] = "refresh_token"
            payload["refresh_token"] = refresh_token

        else:
            raise ValueError(
                f"Action '{action}' is not supported. Use 'client_credentials' or 'refresh_token'."
            )

        req_data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            token_url,
            data=req_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as response:
                return {"status": "success", "data": json.loads(response.read().decode("utf-8"))}
        except urllib.error.HTTPError as e:
            return {"status": "error", "error": json.loads(e.read().decode("utf-8"))}
