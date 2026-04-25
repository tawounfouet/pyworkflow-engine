from typing import Any
from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import boto3
except ImportError:
    boto3 = None


@connector("storage.s3")
class S3Connector(BaseConnector):
    """AWS S3 Storage Connector using boto3."""

    def execute(
        self, action: str, bucket: str, key: str, data: bytes | None = None
    ) -> dict[str, Any]:
        if boto3 is None:
            raise ImportError(
                "S3 connector requires boto3. Install with: pip install pyconnectors[s3]"
            )

        s3 = boto3.client(
            "s3",
            aws_access_key_id=self.config.params.get("aws_access_key_id"),
            aws_secret_access_key=self.config.params.get("aws_secret_access_key"),
            region_name=self.config.params.get("region_name"),
        )

        if action == "put":
            s3.put_object(Bucket=bucket, Key=key, Body=data)
            return {"status": "uploaded"}
        elif action == "get":
            response = s3.get_object(Bucket=bucket, Key=key)
            return {"status": "downloaded", "data": response["Body"].read()}
        else:
            raise ValueError(f"Unknown action: {action}")
