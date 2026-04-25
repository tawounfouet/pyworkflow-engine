import poplib
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("email.pop3")
class POP3Connector(BaseConnector):
    """POP3 Email Connector for generic hosting providers."""

    def execute(self, action: str = "stat") -> dict[str, Any]:
        host = self.config.params.get("host")
        if not host:
            raise ValueError("POP3Connector requires 'host' in configuration.")

        port = self.config.params.get("port", 995)
        user = self.config.params.get("user")
        password = self.config.params.get("password")
        use_ssl = self.config.params.get("use_ssl", True)

        if not user or not password:
            raise ValueError("POP3Connector requires 'user' and 'password' in configuration.")

        try:
            if use_ssl:
                mail: poplib.POP3 = poplib.POP3_SSL(host, port)
            else:
                mail = poplib.POP3(host, port)

            mail.user(user)
            mail.pass_(password)

            if action == "stat":
                num_messages, total_size = mail.stat()
                return {"status": "success", "count": num_messages, "size": total_size}
            elif action == "list":
                response, listings, octets = mail.list()
                return {"status": "success", "messages": [lst.decode("utf-8") for lst in listings]}
            else:
                raise ValueError(f"Action '{action}' is not supported yet.")

        finally:
            try:
                mail.quit()
            except Exception:
                pass
