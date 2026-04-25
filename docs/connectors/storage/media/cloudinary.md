# Cloudinary (`storage.cloudinary`)

**Requires:** `cloudinary` — `uv pip install "pyconnectors[cloudinary]"`

---

## Configuration

| Key | Description |
|---|---|
| `cloud_name` | Cloudinary cloud name |
| `api_key` | Cloudinary API key |
| `api_secret` | Cloudinary API secret |

---

## Differences from other storage connectors

- `bucket` is **ignored** — Cloudinary organises assets by public ID, not buckets.
- For `upload`: `file_path` is a **local file path**.
- For `delete`: `public_id` is required (the Cloudinary asset identifier).

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "cloud_name": "my-cloud",
    "api_key":    "123456789",
    "api_secret": "abc...",
})
cloudinary = ConnectorFactory.create("storage.cloudinary", config=config)

# Upload a local file
result = cloudinary.safe_execute("upload", bucket=None, file_path="/tmp/photo.jpg")
print("Upload:", result.success, result.data)

# Delete by public ID
result = cloudinary.safe_execute("delete", bucket=None, public_id="photo")
print("Deleted:", result.success)
```
