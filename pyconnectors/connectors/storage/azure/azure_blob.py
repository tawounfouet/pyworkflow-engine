from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    from azure.storage.blob import BlobServiceClient
except ImportError:
    BlobServiceClient = None


@connector("storage.azure_blob")
class AzureBlobConnector(BaseConnector):
    """Azure Blob Storage Connector using azure-storage-blob."""

    def execute(
        self, action: str, container_name: str, blob_name: str, data: bytes | str | None = None
    ) -> dict[str, Any]:
        if BlobServiceClient is None:
            raise ImportError(
                "Azure Blob connector requires azure-storage-blob. Install with: pip install pyconnectors[azure_blob]"
            )

        connection_string = self.config.params.get("connection_string")
        if not connection_string:
            raise ValueError("AzureBlobConnector requires 'connection_string' in configuration.")

        client = BlobServiceClient.from_connection_string(connection_string)
        blob_client = client.get_blob_client(container=container_name, blob=blob_name)

        if action == "upload":
            if data is None:
                raise ValueError("Data must be provided for 'upload' action.")
            blob_client.upload_blob(data, overwrite=True)
            return {"status": "uploaded"}
        elif action == "download":
            downloader = blob_client.download_blob()
            content = downloader.readall()
            return {"status": "downloaded", "data": content}
        elif action == "delete":
            blob_client.delete_blob()
            return {"status": "deleted"}
        else:
            raise ValueError(f"Action '{action}' is not supported.")
