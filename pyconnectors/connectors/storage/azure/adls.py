from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    from azure.storage.filedatalake import DataLakeServiceClient
except ImportError:
    DataLakeServiceClient = None


@connector("storage.adls")
class ADLSConnector(BaseConnector):
    """Azure Data Lake Storage Gen2 Connector using azure-storage-file-datalake."""

    def execute(
        self, action: str, file_system_name: str, file_path: str, data: bytes | str | None = None
    ) -> dict[str, Any]:
        if DataLakeServiceClient is None:
            raise ImportError(
                "ADLS connector requires azure-storage-file-datalake. Install with: pip install pyconnectors[adls]"
            )

        connection_string = self.config.params.get("connection_string")
        if not connection_string:
            raise ValueError("ADLSConnector requires 'connection_string' in configuration.")

        client = DataLakeServiceClient.from_connection_string(connection_string)
        file_system_client = client.get_file_system_client(file_system=file_system_name)
        file_client = file_system_client.get_file_client(file_path)

        if action == "upload":
            if data is None:
                raise ValueError("Data must be provided for 'upload' action.")
            file_client.upload_data(data, overwrite=True)
            return {"status": "uploaded"}
        elif action == "download":
            downloader = file_client.download_file()
            content = downloader.readall()
            return {"status": "downloaded", "data": content}
        elif action == "delete":
            file_client.delete_file()
            return {"status": "deleted"}
        else:
            raise ValueError(f"Action '{action}' is not supported.")
