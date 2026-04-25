from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    import jwt
except ImportError:
    jwt = None


@connector("auth.jwt")
class JWTConnector(BaseConnector):
    """JWT Token Generator and Validator."""

    def execute(
        self, action: str, payload: dict[str, Any] | None = None, token: str | None = None
    ) -> dict[str, Any]:
        if jwt is None:
            raise ImportError(
                "JWT connector requires PyJWT. Install with: pip install pyconnectors[auth]"
            )

        secret = self.config.params.get("secret_key")
        algorithm = self.config.params.get("algorithm", "HS256")

        if not secret:
            raise ValueError("JWTConnector requires 'secret_key' in configuration.")

        if action == "encode":
            if not payload:
                raise ValueError("Payload must be provided for 'encode' action.")
            encoded = jwt.encode(payload, secret, algorithm=algorithm)
            return {"status": "success", "token": encoded}

        elif action == "decode":
            if not token:
                raise ValueError("Token must be provided for 'decode' action.")
            try:
                decoded = jwt.decode(token, secret, algorithms=[algorithm])
                return {"status": "success", "payload": decoded}
            except jwt.ExpiredSignatureError:
                return {"status": "error", "error": "Token has expired"}
            except jwt.InvalidTokenError as e:
                return {"status": "error", "error": f"Invalid token: {e}"}

        else:
            raise ValueError(f"Action '{action}' not supported.")
