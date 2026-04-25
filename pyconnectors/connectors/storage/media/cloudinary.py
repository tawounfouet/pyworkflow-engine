from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import cloudinary
    import cloudinary.uploader
except ImportError:
    cloudinary = None


@connector("storage.cloudinary")
class CloudinaryConnector(BaseConnector):
    """Cloudinary Storage Connector."""

    def execute(self, action: str, file_path: str, public_id: str | None = None) -> dict[str, Any]:
        if cloudinary is None:
            raise ImportError(
                "Cloudinary connector requires cloudinary. Install with: pip install pyconnectors[cloudinary]"
            )

        cloud_name = self.config.params.get("cloud_name")
        api_key = self.config.params.get("api_key")
        api_secret = self.config.params.get("api_secret")

        if not all([cloud_name, api_key, api_secret]):
            raise ValueError(
                "CloudinaryConnector requires 'cloud_name', 'api_key', and 'api_secret' in configuration."
            )

        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)

        if action == "upload":
            response = cloudinary.uploader.upload(file_path, public_id=public_id)
            return {"status": "uploaded", "url": response.get("secure_url")}
        elif action == "delete":
            if not public_id:
                raise ValueError("public_id must be provided for 'delete' action.")
            response = cloudinary.uploader.destroy(public_id)
            return {"status": "deleted", "result": response.get("result")}
        else:
            raise ValueError(f"Action '{action}' is not supported.")
