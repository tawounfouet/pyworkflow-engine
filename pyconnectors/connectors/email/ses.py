from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import boto3
except ImportError:
    boto3 = None


@connector("email.ses")
class SESConnector(BaseConnector):
    """AWS Simple Email Service (SES) Connector using boto3."""

    def execute(
        self, to_addr: str, subject: str, body_html: str, body_text: str | None = None
    ) -> dict[str, Any]:
        if boto3 is None:
            raise ImportError(
                "SES connector requires boto3. Install with: pip install pyconnectors[s3] or pip install boto3"
            )

        from_addr = self.config.params.get("from_addr")
        if not from_addr:
            raise ValueError("SESConnector requires 'from_addr' in configuration.")

        client = boto3.client(
            "ses",
            aws_access_key_id=self.config.params.get("aws_access_key_id"),
            aws_secret_access_key=self.config.params.get("aws_secret_access_key"),
            region_name=self.config.params.get("region_name", "us-east-1"),
        )

        message: dict[str, Any] = {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Html": {"Data": body_html, "Charset": "UTF-8"}},
        }

        if body_text:
            message["Body"]["Text"] = {"Data": body_text, "Charset": "UTF-8"}

        response = client.send_email(
            Source=from_addr,
            Destination={"ToAddresses": [to_addr]},
            Message=message,
        )

        return {"status": "sent", "message_id": response["MessageId"]}
