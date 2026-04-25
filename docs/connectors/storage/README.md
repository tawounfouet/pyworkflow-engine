# Storage Connectors

Store and retrieve files across cloud vendors. All connectors use `safe_execute()` — never raises, always returns `ConnectorResult`.

## Standard operations

Every storage connector accepts:

| Param | Values | Notes |
|---|---|---|
| `action` | `"upload"`, `"download"`, `"delete"` | Required |
| `bucket` / `container` / `space` | Bucket or container name | Required |
| `key` / `blob_name` / `file_path` | Path within the bucket | Required |
| `data` | `bytes` or `str` | Required for `upload` |

---

## Native cloud connectors

| Connector | Key | Provider | Install extra |
|---|---|---|---|
| [Azure Blob Storage](azure/blob.md) | `storage.azure_blob` | Microsoft Azure | `uv pip install "pyconnectors[azure_blob]"` |
| [Azure Data Lake Gen2](azure/adls.md) | `storage.adls` | Microsoft Azure | `uv pip install "pyconnectors[adls]"` |
| [Google Cloud Storage](gcp/gcs.md) | `storage.gcs` | Google Cloud | `uv pip install "pyconnectors[gcs]"` |
| [Cloudinary](media/cloudinary.md) | `storage.cloudinary` | Cloudinary | `uv pip install "pyconnectors[cloudinary]"` |

## S3-compatible connectors

All use `boto3` — `uv pip install "pyconnectors[s3]"`

| Connector | Key | Endpoint |
|---|---|---|
| [Amazon S3](s3/s3.md) | `storage.s3` | AWS |
| [DigitalOcean Spaces](s3/digitalocean.md) | `storage.digitalocean` | `https://[region].digitaloceanspaces.com` |
| [Hetzner Object Storage](s3/hetzner.md) | `storage.hetzner` | `https://[region].your-objectstorage.com` |
| [OVH Object Storage](s3/ovh.md) | `storage.ovh` | `https://s3.[region].perf.cloud.ovh.net` |
| [MinIO](s3/minio.md) | `storage.minio` | Custom endpoint |

---

## TaskFlow — `@connect`

```python
from pyconnectors import connect, configure, ConnectorConfig
import os

configure("storage.s3", ConnectorConfig(params={
    "aws_access_key_id":     os.environ["AWS_ACCESS_KEY_ID"],
    "aws_secret_access_key": os.environ["AWS_SECRET_ACCESS_KEY"],
    "region_name": "us-east-1",
}))

@connect("storage.s3")
def upload_report(conn, data: bytes, filename: str):
    return conn.execute("upload", "reports-bucket", filename, data=data)

@connect("storage.s3")
def download_report(conn, filename: str):
    return conn.execute("download", "reports-bucket", filename)

upload_report(data=b"report content", filename="report-2026.txt")
result = download_report(filename="report-2026.txt")
print(result.data)   # b"report content"
```
