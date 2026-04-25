import json
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.resend")
class ResendConnector(BaseConnector):
    """Resend Email API Connector."""

    def execute(self, to_addr: str, subject: str, body_html: str) -> dict[str, Any]:
        api_key = self.config.params.get("api_key")
        if not api_key:
            raise ValueError("ResendConnector requires 'api_key' in configuration.")

        from_addr = self.config.params.get("from_addr")
        if not from_addr:
            raise ValueError("ResendConnector requires 'from_addr' in configuration.")

        payload = {
            "from": from_addr,
            "to": [to_addr],
            "subject": subject,
            "html": body_html,
        }

        req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "pyconnectors/1.0",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            return {"status": response.status, "data": json.loads(response.read().decode("utf-8"))}
