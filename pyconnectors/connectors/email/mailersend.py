import json
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.mailersend")
class MailerSendConnector(BaseConnector):
    """MailerSend API Connector."""

    def execute(
        self, to_addr: str, subject: str, body_html: str, from_name: str | None = None
    ) -> dict[str, Any]:
        api_key = self.config.params.get("api_key")
        if not api_key:
            raise ValueError("MailerSendConnector requires 'api_key' in configuration.")

        from_addr = self.config.params.get("from_addr")
        if not from_addr:
            raise ValueError("MailerSendConnector requires 'from_addr' in configuration.")

        sender = {"email": from_addr}
        if from_name:
            sender["name"] = from_name

        payload = {
            "from": sender,
            "to": [{"email": to_addr}],
            "subject": subject,
            "html": body_html,
        }

        req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            "https://api.mailersend.com/v1/email",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "X-Requested-With": "XMLHttpRequest",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            return {
                "status": response.status,
            }
