# S3-Compatible Connectors

All S3-compatible connectors share the same interface as [`storage.s3`](s3.md), using `boto3` under the hood with a custom endpoint URL.

**Requires:** `uv pip install "pyconnectors[s3]"`

---

## DigitalOcean Spaces (`storage.digitalocean`)

| Key | Description |
|---|---|
| `aws_access_key_id` | Spaces access key |
| `aws_secret_access_key` | Spaces secret key |
| `region_name` | Region slug (e.g. `nyc3`, `ams3`) |

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "aws_access_key_id":     "DO...",
    "aws_secret_access_key": "sec...",
    "region_name": "nyc3",
})
do = ConnectorFactory.create("storage.digitalocean", config=config)

result = do.safe_execute("upload", "my-space", "document.pdf", data=b"%PDF...")
print(result.success, result.data)
```

---

## Hetzner Object Storage (`storage.hetzner`)

| Key | Description |
|---|---|
| `aws_access_key_id` | Hetzner access key |
| `aws_secret_access_key` | Hetzner secret key |
| `region_name` | Region (e.g. `fsn1`, `nbg1`) |

```python
config = ConnectorConfig(params={
    "aws_access_key_id":     "...",
    "aws_secret_access_key": "...",
    "region_name": "fsn1",
})
hetzner = ConnectorFactory.create("storage.hetzner", config=config)
result = hetzner.safe_execute("upload", "my-bucket", "file.txt", data=b"hello")
```

---

## OVH Object Storage (`storage.ovh`)

| Key | Description |
|---|---|
| `aws_access_key_id` | OVH access key |
| `aws_secret_access_key` | OVH secret key |
| `region_name` | Region (e.g. `gra`, `sbg`) |

```python
config = ConnectorConfig(params={
    "aws_access_key_id":     "...",
    "aws_secret_access_key": "...",
    "region_name": "gra",
})
ovh = ConnectorFactory.create("storage.ovh", config=config)
result = ovh.safe_execute("upload", "my-container", "data.json", data=b"{}")
```

---

## MinIO (`storage.minio`)

| Key | Description |
|---|---|
| `aws_access_key_id` | MinIO access key |
| `aws_secret_access_key` | MinIO secret key |
| `endpoint_url` | MinIO server URL (e.g. `http://localhost:9000`) |

```python
config = ConnectorConfig(params={
    "aws_access_key_id":     "minioadmin",
    "aws_secret_access_key": "minioadmin",
    "endpoint_url":          "http://localhost:9000",
})
minio = ConnectorFactory.create("storage.minio", config=config)
result = minio.safe_execute("upload", "my-bucket", "hello.txt", data=b"Hello!")
```
