# Amazon SES (`email.ses`)

**Requires:** `boto3` — `uv pip install "pyconnectors[s3]"`

---

## Configuration

| Key | Description |
|---|---|
| `aws_access_key_id` | AWS access key |
| `aws_secret_access_key` | AWS secret key |
| `region_name` | AWS region (default `us-east-1`) |
| `from_addr` | Verified sender address or domain |

---

## Usage

```python
from pyconnectors import ConnectorFactory, ConnectorConfig

config = ConnectorConfig(params={
    "aws_access_key_id":     "AKIA...",
    "aws_secret_access_key": "wJal...",
    "region_name":           "us-east-1",
    "from_addr":             "noreply@example.com",
})
ses = ConnectorFactory.create("email.ses", config=config)

result = ses.safe_execute(
    to_addr="user@example.com",
    subject="Hello via SES",
    body_html="<p>HTML body</p>",
    body_text="Plain text fallback",
)
print(result.success, result.data)
```
