# Azure Blob Storage (`storage.azure_blob`)

**Requires:** `azure-storage-blob` — `uv pip install "pyconnectors[azure_blob]"`

---

## Configuration

| Key | Description |
|---|---|
| `connection_string` | Azure Storage connection string |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "connection_string": "DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net",
})
blob = ConnectorFactory.create("storage.azure_blob", config=config)

# Upload
result = blob.safe_execute("upload", "my-container", "hello.txt", data=b"Hello!")
print("Upload:", result.success)

# Download
result = blob.safe_execute("download", "my-container", "hello.txt")
print("Content:", result.data)

# Delete
result = blob.safe_execute("delete", "my-container", "hello.txt")
print("Deleted:", result.success)
```
