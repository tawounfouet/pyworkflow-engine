import json
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("social.whatsapp")
class WhatsAppConnector(BaseConnector):
    """WhatsApp Cloud API connector."""

    def execute(self, to: str, message: str, phone_number_id: str | None = None) -> dict[str, Any]:
        access_token = self.config.params.get("access_token")
        if not access_token:
            raise ValueError("WhatsAppConnector requires 'access_token' in configuration.")

        pid = phone_number_id or self.config.params.get("phone_number_id")
        if not pid:
            raise ValueError(
                "WhatsAppConnector requires 'phone_number_id' via execute args or configuration."
            )

        api_version = self.config.params.get("api_version", "v19.0")
        url = f"https://graph.facebook.com/{api_version}/{pid}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message},
        }

        req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            return {"status": response.status, "data": json.loads(response.read().decode("utf-8"))}
