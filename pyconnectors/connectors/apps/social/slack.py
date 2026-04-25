from typing import Any
from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import json
    import urllib.request
except ImportError:
    pass


@connector("social.slack")
class SlackConnector(BaseConnector):
    """Slack webhook connector."""

    def execute(self, text: str, channel: str | None = None) -> dict[str, Any]:
        webhook_url = self.config.params.get("webhook_url")
        if not webhook_url:
            raise ValueError("SlackConnector requires 'webhook_url' in configuration.")

        payload = {"text": text}
        if channel:
            payload["channel"] = channel

        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            return {"status": response.status}
