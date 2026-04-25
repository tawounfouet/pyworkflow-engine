import json
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.brevo")
class BrevoConnector(BaseConnector):
    """Brevo (formerly Sendinblue) Transactional Email API Connector."""

    def execute(
        self, to_addr: str, subject: str, body_html: str, sender_name: str | None = None
    ) -> dict[str, Any]:
        api_key = self.config.params.get("api_key")
        if not api_key:
            raise ValueError("BrevoConnector requires 'api_key' in configuration.")

        from_addr = self.config.params.get("from_addr")
        if not from_addr:
            raise ValueError("BrevoConnector requires 'from_addr' in configuration.")

        sender = {"email": from_addr}
        if sender_name:
            sender["name"] = sender_name

        payload = {
            "sender": sender,
            "to": [{"email": to_addr}],
            "subject": subject,
            "htmlContent": body_html,
        }

        req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "api-key": api_key,
                "Accept": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            return {
                "status": response.status,
                "data": (
                    json.loads(response.read().decode("utf-8")) if response.status == 201 else {}
                ),
            }
