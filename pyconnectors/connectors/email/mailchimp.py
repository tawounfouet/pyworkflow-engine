import json
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.mailchimp")
class MailchimpConnector(BaseConnector):
    """Mailchimp Transactional API Connector (formerly Mandrill)."""

    def execute(
        self, to_addr: str, subject: str, body_html: str, from_name: str | None = None
    ) -> dict[str, Any]:
        api_key = self.config.params.get("api_key")
        if not api_key:
            raise ValueError("MailchimpConnector requires 'api_key' in configuration.")

        from_addr = self.config.params.get("from_addr")
        if not from_addr:
            raise ValueError("MailchimpConnector requires 'from_addr' in configuration.")

        payload = {
            "key": api_key,
            "message": {
                "html": body_html,
                "subject": subject,
                "from_email": from_addr,
                "to": [{"email": to_addr, "type": "to"}],
            },
        }

        if from_name:
            payload["message"]["from_name"] = from_name

        req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            "https://mandrillapp.com/api/1.0/messages/send.json",
            data=req_data,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            return {"status": response.status, "data": json.loads(response.read().decode("utf-8"))}
