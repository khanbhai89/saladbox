"""Calculator tool for mathematical expressions."""

from __future__ import annotations

import math
import re

from saladbox.tools.base import BaseTool


class CalculatorTool(BaseTool):
    """Evaluate mathematical expressions safely."""

    ALLOWED_NAMES = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
    ALLOWED_NAMES.update(
        {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
        }
    )

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return (
            "Evaluate mathematical expressions. Supports basic operations (+, -, *, /, **), "
            "and functions like sin, cos, tan, sqrt, log, exp, abs, round, floor, ceil, etc. "
            "Also supports constants like pi and e."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2**10 + sqrt(16)')",
                },
                "precision": {
                    "type": "integer",
                    "description": "Number of decimal places for the result (default: 6)",
                },
            },
            "required": ["expression"],
        }

    async def execute(self, expression: str, precision: int = 6) -> str:
        expr = expression.strip()

        if not expr:
            return "Error: Empty expression"

        if not self._is_safe(expr):
            return "Error: Expression contains disallowed characters or functions"

        try:
            code = compile(expr, "<string>", "eval")
            for name in code.co_names:
                if name not in self.ALLOWED_NAMES:
                    return f"Error: Function or variable '{name}' is not allowed"

            result = eval(code, {"__builtins__": {}}, self.ALLOWED_NAMES)

            if isinstance(result, float):
                result = int(result) if result == int(result) else round(result, precision)

            return f"{expression} = {result}"

        except ZeroDivisionError:
            return "Error: Division by zero"
        except ValueError as e:
            return f"Error: {e!s}"
        except SyntaxError:
            return "Error: Invalid mathematical expression"
        except Exception as e:
            return f"Error evaluating expression: {e!s}"

    def _is_safe(self, expr: str) -> bool:
        safe_pattern = r"^[\d\s\+\-\*\/\%\(\)\.\,\w]+$"
        if not re.match(safe_pattern, expr):
            return False

        dangerous = [
            "import",
            "exec",
            "eval",
            "open",
            "file",
            "__",
            "getattr",
            "setattr",
        ]
        return all(word not in expr.lower() for word in dangerous)
