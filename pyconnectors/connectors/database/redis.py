from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import redis
except ImportError:
    redis = None


@connector("database.redis")
class RedisConnector(BaseConnector):
    """Redis Connector using redis-py."""

    def execute(self, action: str, key: str | None = None, value: str | bytes | None = None) -> Any:
        if redis is None:
            raise ImportError(
                "Redis connector requires redis. Install with: pip install pyconnectors[redis]"
            )

        # Accept DATABASE_URL / REDIS_URL (PaaS standard) as aliases
        url = (
            self.config.params.get("url")
            or self.config.params.get("database_url")
            or self.config.params.get("redis_url")
        )

        if not url:
            host = self.config.params.get("host", "localhost")
            port = self.config.params.get("port", 6379)
            db = self.config.params.get("db", 0)
            client = redis.Redis(host=host, port=port, db=db)
        else:
            client = redis.from_url(url)

        try:
            if action == "set" and key and value is not None:
                return client.set(key, value)
            elif action == "get" and key:
                val = client.get(key)
                return val.decode("utf-8") if isinstance(val, bytes) else val
            elif action == "delete" and key:
                return client.delete(key)
            else:
                raise ValueError(
                    f"Action '{action}' is not supported or missing required arguments."
                )
        finally:
            client.close()
