from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.gmail")
class GmailConnector(BaseConnector):
    """Pre-configured Gmail connector that acts as a wrapper around SMTP/IMAP."""

    def execute(self, to_addr: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email using Gmail SMTP server. For receiving, IMAP should be used."""
        try:
            import smtplib
            from email.mime.text import MIMEText
        except ImportError:
            raise ImportError(
                "GmailConnector requires smtplib and email packages from standard library."
            )

        host = "smtp.gmail.com"
        port = 587

        user = self.config.params.get("user")
        password = self.config.params.get("password")  # Note: Use App Passwords if 2FA is enabled.
        from_addr = self.config.params.get("from_addr", user)

        if not user or not password:
            raise ValueError("GmailConnector requires 'user' and 'password' in configuration.")

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr or ""
        msg["To"] = to_addr

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

        return {"status": "sent", "provider": "gmail"}
