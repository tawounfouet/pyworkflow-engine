from typing import Any
from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import smtplib
    from email.mime.text import MIMEText
except ImportError:
    pass


@connector("email.smtp")
class SMTPConnector(BaseConnector):
    """SMTP Email Connector."""

    def execute(
        self, to_addr: str, subject: str, body: str, html: bool = False
    ) -> dict[str, Any]:
        host = self.config.params.get("host", "localhost")
        port = self.config.params.get("port", 25)
        user = self.config.params.get("user")
        password = self.config.params.get("password")
        from_addr = self.config.params.get("from_addr", "no-reply@localhost")

        msg = MIMEText(body, "html" if html else "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr

        use_ssl = self.config.params.get("use_ssl", False)

        if use_ssl:
            # Port 465 — SSL natif (SMTP_SSL)
            with smtplib.SMTP_SSL(host, port) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            # Port 587 — STARTTLS
            with smtplib.SMTP(host, port) as server:
                server.ehlo()
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)

        return {"status": "sent"}
