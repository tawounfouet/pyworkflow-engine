import json
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("social.twitter")
class TwitterConnector(BaseConnector):
    """Twitter (X) API v2 connector."""

    def execute(
        self, endpoint: str, data: dict[str, Any] | None = None, method: str = "GET"
    ) -> dict[str, Any]:
        bearer_token = self.config.params.get("bearer_token")
        if not bearer_token:
            raise ValueError("TwitterConnector requires 'bearer_token' in configuration.")

        base_url = "https://api.twitter.com/2"
        url = f"{base_url}/{endpoint.lstrip('/')}"

        req_data = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {bearer_token}",
            },
            method=method.upper(),
        )

        with urllib.request.urlopen(req) as response:
            return {"status": response.status, "data": json.loads(response.read().decode("utf-8"))}
