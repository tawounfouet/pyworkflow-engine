"""
adapters/ai/tools — Tools concrets pour le function-calling LLM.

Tools disponibles :
  - CalculatorTool    : évaluation mathématique sécurisée
  - HttpGetTool       : requête HTTP GET
  - HttpPostTool      : requête HTTP POST
  - DuckDuckGoSearchTool : recherche web DuckDuckGo (sans clé API)
  - SerperSearchTool  : recherche web Google via Serper
  - ToolRegistry      : registre central des functions
  - ToolExecutor      : exécution de tool-calls + boucle tool-calling
"""

from __future__ import annotations

from pyworkflow_engine.adapters.ai.tools.calculator import CalculatorTool
from pyworkflow_engine.adapters.ai.tools.http_client import HttpGetTool, HttpPostTool
from pyworkflow_engine.adapters.ai.tools.registry import ToolRegistry
from pyworkflow_engine.adapters.ai.tools.executor import ToolExecutor
from pyworkflow_engine.adapters.ai.tools.web_search import (
    DuckDuckGoSearchTool,
    SerperSearchTool,
)

__all__ = [
    "CalculatorTool",
    "HttpGetTool",
    "HttpPostTool",
    "DuckDuckGoSearchTool",
    "SerperSearchTool",
    "ToolRegistry",
    "ToolExecutor",
]
