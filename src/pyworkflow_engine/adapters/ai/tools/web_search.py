"""
adapters/ai/tools/web_search — Tools de recherche web pour agents LLM.

DuckDuckGoSearchTool : sans clé API.
SerperSearchTool     : Google Search via Serper (SERPER_API_KEY requis).
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from pyworkflow_engine.models.ai.types import ToolType
from pyworkflow_engine.ports.ai.tool import BaseTool

logger = logging.getLogger(__name__)

_WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query."},
        "max_results": {
            "type": "integer",
            "description": "Max results to return.",
            "default": 5,
        },
    },
    "required": ["query"],
}


class DuckDuckGoSearchTool(BaseTool):
    """Recherche web via l'API DuckDuckGo Instant Answer (sans clé API)."""

    key = "web_search"
    name = "Web Search (DuckDuckGo)"
    description = (
        "Search the web using DuckDuckGo. Returns titles, snippets, and URLs. "
        "Use to find current information, facts, or documentation."
    )
    tool_type = ToolType.API
    parameters_schema = _WEB_SEARCH_SCHEMA

    def __init__(self, max_results: int = 5, timeout: int = 10) -> None:
        self.max_results = max_results
        self.timeout = timeout

    def run(self, query: str = "", max_results: int | None = None, **_: Any) -> str:  # type: ignore[override]
        n = max_results or self.max_results
        encoded = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "pyworkflow-ai/1.0"}
            )
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("DuckDuckGo search failed for '%s': %s", query, exc)
            return f"Error: web search failed — {exc}"

        results: list[str] = []
        if data.get("AbstractText"):
            results.append(
                f"Summary: {data['AbstractText']}\nSource: {data.get('AbstractURL', '')}"
            )
        for topic in data.get("RelatedTopics", []):
            if len(results) >= n:
                break
            if isinstance(topic, dict) and "Text" in topic:
                results.append(f"- {topic['Text']}\n  {topic.get('FirstURL', '')}")
            elif isinstance(topic, dict) and "Topics" in topic:
                for sub in topic.get("Topics", []):
                    if len(results) >= n:
                        break
                    if sub.get("Text"):
                        results.append(f"- {sub['Text']}\n  {sub.get('FirstURL', '')}")

        if not results:
            return f"No results found for: '{query}'"
        return f"Search results for '{query}':\n\n" + "\n".join(results[:n])


class SerperSearchTool(BaseTool):
    """Recherche web Google via Serper API (SERPER_API_KEY requis)."""

    key = "web_search_serper"
    name = "Web Search (Serper/Google)"
    description = (
        "Search the web using Google (via Serper API). Returns organic results "
        "with titles, snippets, and URLs."
    )
    tool_type = ToolType.API
    parameters_schema = _WEB_SEARCH_SCHEMA
    _SERPER_URL = "https://google.serper.dev/search"

    def __init__(
        self, api_key: str = "", max_results: int = 5, timeout: int = 10
    ) -> None:
        import os  # noqa: PLC0415

        self.api_key = api_key or os.environ.get("SERPER_API_KEY", "")
        self.max_results = max_results
        self.timeout = timeout

    def run(self, query: str = "", max_results: int | None = None, **_: Any) -> str:  # type: ignore[override]
        if not self.api_key:
            return "Error: Serper API key not configured. Set SERPER_API_KEY env var."
        n = max_results or self.max_results
        payload = json.dumps({"q": query, "num": n}).encode("utf-8")
        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}
        try:
            req = urllib.request.Request(
                self._SERPER_URL, data=payload, headers=headers
            )
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("Serper search failed for '%s': %s", query, exc)
            return f"Error: Serper search failed — {exc}"

        organic = data.get("organic", [])
        if not organic:
            return f"No results found for: '{query}'"
        lines = [f"Search results for '{query}':\n"]
        for i, item in enumerate(organic[:n], start=1):
            lines.append(
                f"{i}. {item.get('title', '')}\n   {item.get('snippet', '')}\n   {item.get('link', '')}"
            )
        return "\n".join(lines)
