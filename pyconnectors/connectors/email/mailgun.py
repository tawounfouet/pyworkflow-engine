import base64
import urllib.parse
import urllib.request
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.mailgun")
class MailgunConnector(BaseConnector):
    """Mailgun API Connector."""

    def execute(self, to_addr: str, subject: str, body_html: str) -> dict[str, Any]:
        api_key = self.config.params.get("api_key")
        if not api_key:
            raise ValueError("MailgunConnector requires 'api_key' in configuration.")

        domain = self.config.params.get("domain")
        if not domain:
            raise ValueError("MailgunConnector requires 'domain' in configuration.")

        from_addr = self.config.params.get("from_addr")
        if not from_addr:
            raise ValueError("MailgunConnector requires 'from_addr' in configuration.")

        payload = {
            "from": from_addr,
            "to": to_addr,
            "subject": subject,
            "html": body_html,
        }

        req_data = urllib.parse.urlencode(payload).encode("utf-8")
        auth_string = base64.b64encode(f"api:{api_key}".encode("utf-8")).decode("ascii")

        req = urllib.request.Request(
            f"https://api.mailgun.net/v3/{domain}/messages",
            data=req_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {auth_string}",
            },
            method="POST",
        )

        import json

        with urllib.request.urlopen(req) as response:
            return {"status": response.status, "data": json.loads(response.read().decode("utf-8"))}
