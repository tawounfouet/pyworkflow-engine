"""
adapters/ai/tools/calculator — Tool de calcul mathématique sécurisé.
"""

from __future__ import annotations

import math
import re
from typing import Any

from pyworkflow_engine.models.ai.types import ToolType
from pyworkflow_engine.ports.ai.tool import BaseTool

_SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "pow": math.pow,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "pi": math.pi,
    "e": math.e,
    "inf": math.inf,
}
_ALLOWED_PATTERN = re.compile(r"^[0-9\s\+\-\*\/\%\(\)\.\,\_a-zA-Z\*\*]+$")


class CalculatorTool(BaseTool):
    """Évalue des expressions mathématiques dans un sandbox sécurisé."""

    key = "calculator"
    name = "Calculator"
    description = (
        "Evaluates a mathematical expression and returns the numeric result. "
        "Supports: +, -, *, /, **, % and functions: sqrt, pow, log, log2, log10, "
        "exp, floor, ceil, sin, cos, tan, abs, round, min, max. Constants: pi, e."
    )
    tool_type = ToolType.FUNCTION
    parameters_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The mathematical expression to evaluate. E.g. '2**10', 'sqrt(144)'",
            },
        },
        "required": ["expression"],
    }

    def run(self, expression: str = "", **_: Any) -> str:  # type: ignore[override]
        expression = expression.strip()
        if not expression:
            return "Error: empty expression."
        if not _ALLOWED_PATTERN.match(expression):
            return f"Error: expression contains forbidden characters: '{expression}'"
        try:
            result = eval(
                expression, {"__builtins__": {}}, _SAFE_FUNCTIONS
            )  # noqa: S307
            if isinstance(result, float) and result.is_integer():
                return str(int(result))
            return str(result)
        except ZeroDivisionError:
            return "Error: division by zero."
        except Exception as exc:
            return f"Error evaluating expression '{expression}': {exc}"
