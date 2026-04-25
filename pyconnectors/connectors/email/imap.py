import imaplib
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.imap")
class IMAPConnector(BaseConnector):
    """IMAP Email Connector for generic hosting providers (cPanel, OVH, IONOS, LWS, etc.)."""

    def execute(
        self, folder: str = "INBOX", action: str = "list", search_criteria: str = "ALL"
    ) -> dict[str, Any]:
        host = self.config.params.get("host")
        if not host:
            raise ValueError("IMAPConnector requires 'host' in configuration.")

        port = self.config.params.get("port", 993)
        user = self.config.params.get("user")
        password = self.config.params.get("password")
        use_ssl = self.config.params.get("use_ssl", True)

        if not user or not password:
            raise ValueError("IMAPConnector requires 'user' and 'password' in configuration.")

        try:
            if use_ssl:
                mail: imaplib.IMAP4 = imaplib.IMAP4_SSL(host, port)
            else:
                mail = imaplib.IMAP4(host, port)

            mail.login(user, password)
            mail.select(folder)

            if action == "list":
                status, messages = mail.search(None, search_criteria)
                if status == "OK":
                    msg_ids = messages[0].split()
                    return {
                        "status": "success",
                        "count": len(msg_ids),
                        "messages": [m.decode("utf-8") for m in msg_ids],
                    }
                return {"status": "error", "message": "Failed to search folder"}
            else:
                raise ValueError(f"Action '{action}' is not supported yet.")

        finally:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
