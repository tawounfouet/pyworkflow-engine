import json
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("social.instagram")
class InstagramConnector(BaseConnector):
    """Instagram Graph API connector."""

    def execute(
        self, endpoint: str, data: dict[str, Any] | None = None, method: str = "GET"
    ) -> dict[str, Any]:
        access_token = self.config.params.get("access_token")
        if not access_token:
            raise ValueError("InstagramConnector requires 'access_token' in configuration.")

        api_version = self.config.params.get("api_version", "v19.0")
        base_url = f"https://graph.instagram.com/{api_version}"
        url = f"{base_url}/{endpoint.lstrip('/')}"

        if method.upper() == "GET":
            url += f"?access_token={access_token}"
            req_data = None
        else:
            payload = data or {}
            payload["access_token"] = access_token
            req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method=method.upper(),
        )

        with urllib.request.urlopen(req) as response:
            return {"status": response.status, "data": json.loads(response.read().decode("utf-8"))}
