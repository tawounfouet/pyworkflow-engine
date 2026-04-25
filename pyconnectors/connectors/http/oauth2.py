from typing import Any

from pyconnectors.config.base import ConnectorConfig
from pyconnectors.connectors.auth.oauth2 import OAuth2Connector
from pyconnectors.connectors.http.rest import RestConnector
from pyconnectors.adapters.registry.memory import connector


@connector("http.oauth2")
class OAuth2RestConnector(RestConnector):
    """
    Extends RestConnector to automatically fetch and inject OAuth2 Bearer Tokens.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.token: str | None = None

        # Extract OAuth2 specific configuration
        self.oauth2_config = ConnectorConfig(
            params={
                "token_url": self.config.params.get("oauth2_token_url"),
                "client_id": self.config.params.get("oauth2_client_id"),
                "client_secret": self.config.params.get("oauth2_client_secret"),
                "scopes": self.config.params.get("oauth2_scopes", []),
            }
        )
        self.auth_connector = OAuth2Connector(self.oauth2_config)

    def _fetch_token(self) -> None:
        """Fetches a new client credentials token."""
        result = self.auth_connector.safe_execute("client_credentials")
        if not result.success:
            raise ValueError(f"Failed to fetch OAuth2 token: {result.error}")
        self.token = result.data.get("data", {}).get("access_token")

    def execute(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Executes the HTTP request, injecting the OAuth2 Bearer token automatically.
        """
        if not self.token:
            self._fetch_token()

        req_headers = headers or {}
        req_headers["Authorization"] = f"Bearer {self.token}"

        # Delegate execution to the parent REST connector
        result = super().execute(
            method, url, data=data, headers=req_headers, query_params=query_params
        )

        # Super simple token expiry retry (assumes 401 means expired)
        if result.get("status") == 401:
            self._fetch_token()
            req_headers["Authorization"] = f"Bearer {self.token}"
            result = super().execute(
                method, url, data=data, headers=req_headers, query_params=query_params
            )

        return result
