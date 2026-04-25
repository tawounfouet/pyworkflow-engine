import json
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("social.tiktok")
class TikTokConnector(BaseConnector):
    """TikTok Display API connector."""

    def execute(
        self, endpoint: str, data: dict[str, Any] | None = None, method: str = "POST"
    ) -> dict[str, Any]:
        access_token = self.config.params.get("access_token")
        if not access_token:
            raise ValueError("TikTokConnector requires 'access_token' in configuration.")

        base_url = "https://open.tiktokapis.com/v2"
        url = f"{base_url}/{endpoint.lstrip('/')}"

        req_data = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            method=method.upper(),
        )

        with urllib.request.urlopen(req) as response:
            return {"status": response.status, "data": json.loads(response.read().decode("utf-8"))}
