from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    from google.cloud import storage
except ImportError:
    storage = None


@connector("storage.gcs")
class GCSConnector(BaseConnector):
    """Google Cloud Storage Connector using google-cloud-storage."""

    def execute(
        self, action: str, bucket_name: str, blob_name: str, data: bytes | str | None = None
    ) -> dict[str, Any]:
        if storage is None:
            raise ImportError(
                "GCS connector requires google-cloud-storage. Install with: pip install pyconnectors[gcs]"
            )

        credentials_path = self.config.params.get("credentials_path")
        project = self.config.params.get("project")

        if credentials_path:
            client = storage.Client.from_service_account_json(credentials_path)
        elif project:
            client = storage.Client(project=project)
        else:
            client = storage.Client()

        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        if action == "upload":
            if data is None:
                raise ValueError("Data must be provided for 'upload' action.")
            if isinstance(data, str):
                blob.upload_from_string(data)
            else:
                blob.upload_from_string(data)
            return {"status": "uploaded"}
        elif action == "download":
            content = blob.download_as_bytes()
            return {"status": "downloaded", "data": content}
        elif action == "delete":
            blob.delete()
            return {"status": "deleted"}
        else:
            raise ValueError(f"Action '{action}' is not supported.")
