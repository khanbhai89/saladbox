"""Base class for all saladbox tools.

Updated for modern LLM tool-calling standards:
- Strict JSON Schema with additionalProperties: false
- Tool categories for better organization
- Confirmation flags for dangerous operations
- Structured metadata for the engine
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from saladbox.core.types import ToolCategory
from saladbox.platform.output import DEFAULT_MAX_CHARS, compress_result


class BaseTool(ABC):
    """Abstract base class that every tool must implement.

    Platform standards:
    - max_output_chars: max characters returned to the LLM (auto-truncated)
    - compact_description: shorter description for local models with small context
    - category: logical grouping for filtering and display
    - requires_confirmation: if True, engine should confirm before executing
    """

    # Override in subclass to limit output size
    max_output_chars: int = DEFAULT_MAX_CHARS

    # Tool metadata — override in subclasses
    category: ToolCategory = ToolCategory.UTILITY
    requires_confirmation: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name used in tool-calling."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for the LLM."""
        ...

    @property
    def compact_description(self) -> str:
        """Shorter description for local models. Override in subclass."""
        return self.description

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema describing the tool's parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool and return a string result."""
        ...

    def to_schema(self, compact: bool = False, strict: bool = False) -> dict:
        """Generate a tool schema compatible with Ollama and OpenAI.

        Args:
            compact: Use shorter descriptions for small-context models.
            strict: If True, add 'additionalProperties: false' and mark all
                    params as required (for OpenAI strict mode / structured outputs).
        """
        desc = self.compact_description if compact else self.description
        params = self.parameters.copy()

        if strict:
            params["additionalProperties"] = False
            # In strict mode, all properties should be listed as required
            if "properties" in params and "required" not in params:
                params["required"] = list(params["properties"].keys())

        schema: dict = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": desc,
                "parameters": params,
            },
        }

        if strict:
            schema["function"]["strict"] = True

        return schema

    def format_output(self, result: str) -> str:
        """Apply platform output standards (compression, truncation)."""
        if len(result) > self.max_output_chars:
            return compress_result(result, self.max_output_chars)
        return result
