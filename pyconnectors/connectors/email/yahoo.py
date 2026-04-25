from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.yahoo")
class YahooConnector(BaseConnector):
    """Pre-configured Yahoo Mail connector that acts as a wrapper around SMTP."""

    def execute(self, to_addr: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email using Yahoo SMTP server."""
        try:
            import smtplib
            from email.mime.text import MIMEText
        except ImportError:
            raise ImportError(
                "YahooConnector requires smtplib and email packages from standard library."
            )

        host = "smtp.mail.yahoo.com"
        port = 465  # Yahoo usually requires SSL on port 465

        user = self.config.params.get("user")
        password = self.config.params.get("password")  # Note: Use App Passwords for Yahoo
        from_addr = self.config.params.get("from_addr", user)

        if not user or not password:
            raise ValueError("YahooConnector requires 'user' and 'password' in configuration.")

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr or ""
        msg["To"] = to_addr

        with smtplib.SMTP_SSL(host, port) as server:
            server.login(user, password)
            server.send_message(msg)

        return {"status": "sent", "provider": "yahoo"}
