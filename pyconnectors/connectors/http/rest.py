import json
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector


@connector("http.rest")
class RestConnector(BaseConnector):
    """
    REST API Connector using stdlib urllib.
    Supports Basic Auth, Digest Auth, API Keys, and Persistent Sessions.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.cookie_jar = CookieJar()
        self._build_opener()

    def _build_opener(self) -> None:
        """Construct the opener with required handlers based on configuration."""
        handlers: list[Any] = []

        # 1. Session / Cookie Support
        if self.config.params.get("use_session", False):
            handlers.append(urllib.request.HTTPCookieProcessor(self.cookie_jar))

        # 2. Authentication
        auth_type = self.config.params.get("auth_type")
        if auth_type:
            auth_type = auth_type.lower()
            username = self.config.params.get("username")
            password = self.config.params.get("password")
            base_url = self.config.params.get("base_url")

            if auth_type in ("basic", "digest") and (not username or not password or not base_url):
                raise ValueError(
                    f"'{auth_type}' auth requires 'username', 'password', and 'base_url' in config."
                )

            password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            if base_url and username and password:
                password_mgr.add_password(None, base_url, username, password)

            if auth_type == "basic":
                handlers.append(urllib.request.HTTPBasicAuthHandler(password_mgr))
            elif auth_type == "digest":
                handlers.append(urllib.request.HTTPDigestAuthHandler(password_mgr))

        self.opener = urllib.request.build_opener(*handlers)

    def execute(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute an HTTP request.
        """
        req_headers = headers or {}
        if "Content-Type" not in req_headers:
            req_headers["Content-Type"] = "application/json"

        # 3. API Key Authentication (via Headers)
        api_key = self.config.params.get("api_key")
        api_key_header = self.config.params.get("api_key_header", "Authorization")
        api_key_prefix = self.config.params.get("api_key_prefix", "Bearer")
        api_key_in = self.config.params.get("api_key_in", "header").lower()

        if api_key and api_key_in == "header":
            if api_key_prefix:
                req_headers[api_key_header] = f"{api_key_prefix} {api_key}".strip()
            else:
                req_headers[api_key_header] = api_key

        # 4. API Key Authentication (via Query Parameters)
        final_query_params = query_params or {}
        if api_key and api_key_in == "query":
            api_key_query_param = self.config.params.get("api_key_query_param", "api_key")
            final_query_params[api_key_query_param] = api_key

        full_url = url
        if final_query_params:
            query_string = urllib.parse.urlencode(final_query_params)
            full_url = f"{url}?{query_string}" if "?" not in url else f"{url}&{query_string}"

        req_data = None
        if data:
            req_data = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            full_url, data=req_data, headers=req_headers, method=method.upper()
        )

        with self.opener.open(req) as response:
            return {"status": response.status, "body": response.read().decode("utf-8")}
