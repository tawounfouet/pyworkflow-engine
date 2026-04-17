"""
adapters/ai/tools/http_client — Tools HTTP GET / POST pour agents LLM.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from pyworkflow_engine.models.ai.types import ToolType
from pyworkflow_engine.ports.ai.tool import BaseTool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15
_MAX_RESPONSE_BYTES = 50_000


class HttpGetTool(BaseTool):
    """Effectue une requête HTTP GET et retourne le corps de la réponse."""

    key = "http_get"
    name = "HTTP GET"
    description = (
        "Performs an HTTP GET request to the specified URL and returns the response body. "
        "Use this to fetch data from REST APIs, web pages, or any HTTP endpoint."
    )
    tool_type = ToolType.API
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to send the GET request to.",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs.",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["url"],
    }

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def run(self, url: str = "", headers: dict[str, str] | None = None, **_: Any) -> str:  # type: ignore[override]
        req = urllib.request.Request(url, headers=headers or {})
        req.add_header("User-Agent", "pyworkflow-ai-http/1.0")
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:  # noqa: S310
                raw = resp.read(_MAX_RESPONSE_BYTES)
                body = raw.decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            return f"HTTP Error {exc.code}: {exc.reason} — URL: {url}"
        except urllib.error.URLError as exc:
            return f"URL Error: {exc.reason} — URL: {url}"
        except Exception as exc:
            logger.warning("HTTP GET failed for '%s': %s", url, exc)
            return f"Error: {exc}"
        suffix = (
            f"\n[Response truncated at {_MAX_RESPONSE_BYTES} bytes]"
            if len(raw) >= _MAX_RESPONSE_BYTES
            else ""
        )
        return f"[HTTP {status}] {url}\n\n{body}{suffix}"


class HttpPostTool(BaseTool):
    """Effectue une requête HTTP POST avec un corps JSON."""

    key = "http_post"
    name = "HTTP POST"
    description = (
        "Performs an HTTP POST request to the specified URL with a JSON body. "
        "Use this to submit data, call REST APIs, or trigger webhooks."
    )
    tool_type = ToolType.API
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to send the POST request to.",
            },
            "body": {
                "type": "object",
                "description": "The JSON body to send in the request.",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs.",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["url"],
    }

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def run(  # type: ignore[override]
        self,
        url: str = "",
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **_: Any,
    ) -> str:
        payload = json.dumps(body or {}).encode("utf-8")
        req_headers = {
            "Content-Type": "application/json",
            "User-Agent": "pyworkflow-ai-http/1.0",
        }
        req_headers.update(headers or {})
        req = urllib.request.Request(
            url, data=payload, headers=req_headers, method="POST"
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:  # noqa: S310
                raw = resp.read(_MAX_RESPONSE_BYTES)
                body_resp = raw.decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            return f"HTTP Error {exc.code}: {exc.reason} — URL: {url}"
        except urllib.error.URLError as exc:
            return f"URL Error: {exc.reason} — URL: {url}"
        except Exception as exc:
            logger.warning("HTTP POST failed for '%s': %s", url, exc)
            return f"Error: {exc}"
        suffix = (
            f"\n[Response truncated at {_MAX_RESPONSE_BYTES} bytes]"
            if len(raw) >= _MAX_RESPONSE_BYTES
            else ""
        )
        return f"[HTTP {status}] {url}\n\n{body_resp}{suffix}"
