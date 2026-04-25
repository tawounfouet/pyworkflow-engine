from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import boto3
except ImportError:
    boto3 = None


@connector("storage.hetzner")
class HetznerConnector(BaseConnector):
    """Hetzner Storage Box/Object Storage Connector using boto3 (S3 API)."""

    def execute(
        self, action: str, bucket: str, key: str, data: bytes | str | None = None
    ) -> dict[str, Any]:
        if boto3 is None:
            raise ImportError(
                "Hetzner connector requires boto3. Install with: pip install pyconnectors[s3]"
            )

        region = self.config.params.get("region_name", "fsn1")
        # Hetzner S3 endpoint format
        endpoint_url = f"https://{region}.your-objectstorage.com"

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=self.config.params.get("aws_access_key_id"),
            aws_secret_access_key=self.config.params.get("aws_secret_access_key"),
        )

        if action == "upload":
            if data is None:
                raise ValueError("Data must be provided for 'upload' action.")
            s3.put_object(Bucket=bucket, Key=key, Body=data)
            return {"status": "uploaded"}
        elif action == "download":
            response = s3.get_object(Bucket=bucket, Key=key)
            return {"status": "downloaded", "data": response["Body"].read()}
        elif action == "delete":
            s3.delete_object(Bucket=bucket, Key=key)
            return {"status": "deleted"}
        else:
            raise ValueError(f"Action '{action}' is not supported.")
