import json
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from typing import Any, Callable, Tuple

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

_BASE_URL = "https://www.strava.com/api/v3"
_TOKEN_URL = "https://www.strava.com/oauth/token"
_PAGE_PAUSE_S = 2.0


@connector("fitness.strava")
class StravaConnector(BaseConnector):
    """Strava API v3 Connector using stdlib only.

    Supports two authentication modes:

    1. **Static access token** (simple / short-lived scripts)::

        ConnectorConfig(params={"access_token": "<token>"})

    2. **OAuth2 refresh token** (production / long-running jobs — recommended)::

        ConnectorConfig(params={
            "client_id":     "<STRAVA_CLIENT_ID>",
            "client_secret": "<STRAVA_CLIENT_SECRET>",
            "refresh_token": "<STRAVA_REFRESH_TOKEN>",
        })

       The access token is refreshed automatically on init and on every 401.

    Rate limiting (200 req/15 min, 2 000 req/day) is handled transparently:
    the connector reads ``X-RateLimit-*`` headers and backs off on 429.
    """

    # ── Init / auth ──────────────────────────────────────────────────────────

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self._access_token: str | None = self.config.params.get("access_token")
        self._max_retries: int = int(self.config.params.get("max_retries", 3))

        # If refresh-token credentials are provided, fetch a fresh access token
        # immediately so the connector is ready without an explicit call.
        if not self._access_token and self._has_refresh_creds():
            self._refresh_access_token()

    def _has_refresh_creds(self) -> bool:
        return all(
            self.config.params.get(k) for k in ("client_id", "client_secret", "refresh_token")
        )

    def _refresh_access_token(self) -> None:
        """Exchange the refresh token for a new access token (stdlib only)."""
        client_id = self.config.params.get("client_id")
        client_secret = self.config.params.get("client_secret")
        refresh_token = self.config.params.get("refresh_token")

        if not (client_id and client_secret and refresh_token):
            raise ValueError(
                "StravaConnector: 'client_id', 'client_secret', and 'refresh_token' "
                "are required to refresh the OAuth2 token."
            )

        payload = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        ).encode("utf-8")

        req = urllib.request.Request(_TOKEN_URL, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        self._access_token = data["access_token"]
        # Strava may rotate the refresh token — persist the new one.
        new_refresh = data.get("refresh_token")
        if new_refresh and new_refresh != refresh_token:
            self.config.params["refresh_token"] = new_refresh

    # ── Core execute ─────────────────────────────────────────────────────────

    def execute(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        method: str = "GET",
    ) -> dict[str, Any]:
        """Perform a single authenticated request against the Strava API.

        Args:
            endpoint: Relative path, e.g. ``"athlete/activities"``.
            data:     For GET — converted to query-string params.
                      For other methods — serialised as JSON body.
            method:   HTTP method (default ``"GET"``).

        Returns:
            ``{"status": int, "data": dict | list}``

        Raises:
            ValueError: If no access token is available.
        """
        if not self._access_token:
            raise ValueError(
                "StravaConnector requires either 'access_token' or "
                "('client_id', 'client_secret', 'refresh_token') in configuration."
            )

        for attempt in range(self._max_retries + 1):
            req = self._build_request(endpoint, data, method)
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    body = response.read().decode("utf-8")
                    self._check_rate_limit_headers(dict(response.headers))
                    return {
                        "status": response.status,
                        "data": json.loads(body) if body else {},
                    }

            except urllib.error.HTTPError as exc:
                # Read the body once — a second call always returns b"".
                error_body = exc.read()
                try:
                    error_json: Any = (
                        json.loads(error_body.decode("utf-8")) if error_body else str(exc)
                    )
                except (ValueError, UnicodeDecodeError):
                    error_json = str(exc)

                if exc.code == 401 and self._has_refresh_creds() and attempt < self._max_retries:
                    self._refresh_access_token()
                    continue

                if exc.code == 429 and attempt < self._max_retries:
                    self._handle_rate_limit(dict(exc.headers), attempt)
                    continue

                return {"status": exc.code, "error": error_json}

        raise RuntimeError("StravaConnector: exceeded max retries.")

    # ── Pagination helper ────────────────────────────────────────────────────

    def get_paginated(
        self,
        endpoint: str,
        per_page: int = 200,
        start_page: int = 1,
        extra_params: dict[str, Any] | None = None,
        page_callback: Callable[[int, list[dict[str, Any]]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Iterate through all pages of a paginated Strava endpoint.

        A ``_PAGE_PAUSE_S`` second pause is applied between pages to stay
        within Strava's rate limits.

        Args:
            endpoint:      Relative path, e.g. ``"athlete/activities"``.
            per_page:      Items per page (Strava max is 200).
            start_page:    First page to fetch (useful for crash recovery).
            extra_params:  Additional query parameters forwarded to every request.
            page_callback: Optional ``callback(page, items)`` called after each page.

        Returns:
            Flat list of all items across all pages.
        """
        all_items: list[dict[str, Any]] = []
        page = start_page

        while True:
            params: dict[str, Any] = {"page": page, "per_page": per_page}
            if extra_params:
                params.update(extra_params)

            result = self.execute(endpoint, data=params, method="GET")

            if "error" in result:
                raise urllib.error.HTTPError(
                    url=endpoint,
                    code=result["status"],
                    msg=str(result["error"]),
                    hdrs=None,  # type: ignore[arg-type]
                    fp=None,
                )

            items: list[dict[str, Any]] = result.get("data", [])
            if not items:
                break

            all_items.extend(items)

            if page_callback is not None:
                page_callback(page, items)

            if len(items) < per_page:
                # Partial page — no more data to fetch.
                break

            page += 1
            time.sleep(_PAGE_PAUSE_S)

        return all_items

    # ── test_connection ───────────────────────────────────────────────────────

    def test_connection(self) -> Tuple[bool, str]:
        """Validate credentials with a lightweight ``GET /athlete`` request."""
        result = self.execute("athlete")
        if "error" in result:
            return False, f"Strava connection failed: {result['error']}"
        athlete = result.get("data", {})
        name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
        return True, f"Connected as {name or 'unknown athlete'} (id={athlete.get('id')})"

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_request(
        self,
        endpoint: str,
        data: dict[str, Any] | None,
        method: str,
    ) -> urllib.request.Request:
        url = f"{_BASE_URL}/{endpoint.lstrip('/')}"
        req_data: bytes | None = None

        if method.upper() == "GET" and data:
            url = f"{url}?{urllib.parse.urlencode(data)}"
        elif data:
            req_data = json.dumps(data).encode("utf-8")

        headers: dict[str, str] = {"Authorization": f"Bearer {self._access_token}"}
        if req_data:
            headers["Content-Type"] = "application/json"

        return urllib.request.Request(url, data=req_data, headers=headers, method=method.upper())

    def _handle_rate_limit(self, headers: dict[str, str], attempt: int) -> None:
        """Back off appropriately on a 429 response."""
        usage = headers.get("X-Ratelimit-Usage", "")
        limit = headers.get("X-Ratelimit-Limit", "")

        if usage and limit:
            try:
                _, usage_daily = map(int, usage.split(","))
                _, limit_daily = map(int, limit.split(","))
                if usage_daily >= limit_daily:
                    raise RuntimeError(
                        f"Strava daily quota exhausted ({usage_daily}/{limit_daily}). "
                        "Retry tomorrow."
                    )
            except (ValueError, IndexError):
                pass
            wait = 15 * 60  # 15-minute sliding window
        else:
            wait = 60 * (2**attempt)  # exponential back-off

        time.sleep(wait)

    def _check_rate_limit_headers(self, headers: dict[str, str]) -> None:
        """Emit warnings when approaching Strava's rate limits."""
        limit_header = headers.get("X-Ratelimit-Limit")
        usage_header = headers.get("X-Ratelimit-Usage")
        if not (limit_header and usage_header):
            return
        try:
            lim_15m, lim_day = map(int, limit_header.split(","))
            use_15m, use_day = map(int, usage_header.split(","))
        except (ValueError, AttributeError):
            return
        if use_15m >= lim_15m * 0.8:
            warnings.warn(
                f"StravaConnector: approaching 15-min rate limit ({use_15m}/{lim_15m})",
                stacklevel=4,
            )
        if use_day >= lim_day * 0.9:
            warnings.warn(
                f"StravaConnector: approaching daily rate limit ({use_day}/{lim_day})",
                stacklevel=4,
            )
