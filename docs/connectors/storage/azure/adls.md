# Azure Data Lake Gen2 (`storage.adls`)

**Requires:** `azure-storage-file-datalake` — `uv pip install "pyconnectors[adls]"`

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
adls = ConnectorFactory.create("storage.adls", config=config)

# Upload
result = adls.safe_execute("upload", "my-filesystem", "path/to/file.json", data=b'{"key": "value"}')
print("Upload:", result.success)

# Download
result = adls.safe_execute("download", "my-filesystem", "path/to/file.json")
print("Content:", result.data)

# Delete
result = adls.safe_execute("delete", "my-filesystem", "path/to/file.json")
print("Deleted:", result.success)
```
