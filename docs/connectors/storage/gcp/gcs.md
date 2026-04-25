# Google Cloud Storage (`storage.gcs`)

**Requires:** `google-cloud-storage` — `uv pip install "pyconnectors[gcs]"`

---

## Configuration

| Key | Description |
|---|---|
| `credentials_path` | Path to service account JSON key file (optional — defaults to ambient ADC) |
| `project` | GCP project ID |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "project": "my-gcp-project",
    # "credentials_path": "/path/to/key.json",  # omit to use ADC
})
gcs = ConnectorFactory.create("storage.gcs", config=config)

# Upload
result = gcs.safe_execute("upload", "my-bucket", "hello.txt", data=b"Hello!")
print("Upload:", result.success)

# Download
result = gcs.safe_execute("download", "my-bucket", "hello.txt")
print("Content:", result.data)

# Delete
result = gcs.safe_execute("delete", "my-bucket", "hello.txt")
print("Deleted:", result.success)
```
