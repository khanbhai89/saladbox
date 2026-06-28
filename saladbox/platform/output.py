"""Standard output formatting and compression for local model optimization.

All tools should use ToolOutput to format results. This ensures:
- Consistent structure across tools
- Automatic truncation for local model context limits
- Compact mode that strips formatting overhead
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Default max characters for tool output (tuned for 8K context local models)
DEFAULT_MAX_CHARS = 2000
COMPACT_MAX_CHARS = 1200


@dataclass
class ToolOutput:
    """Standard structured output from any tool."""

    summary: str  # 1-2 sentence summary (always included)
    data: list[dict[str, Any]] = field(default_factory=list)  # structured items
    details: str = ""  # extended text (truncated first)
    error: str = ""  # error message if any
    action_hint: str = ""  # hint for next action the LLM can take
    source: str = ""  # tool name / data source

    def render(self, max_chars: int = DEFAULT_MAX_CHARS, compact: bool = False) -> str:
        """Render to string, fitting within max_chars."""
        if self.error:
            return f"Error: {self.error}"

        parts: list[str] = []

        # Summary always first
        parts.append(self.summary)

        # Structured data
        if self.data:
            for i, item in enumerate(self.data, 1):
                if compact:
                    line = f"{i}. " + " | ".join(
                        f"{v}" for k, v in item.items() if v
                    )
                else:
                    line = f"{i}. " + " | ".join(
                        f"**{k}:** {v}" for k, v in item.items() if v
                    )
                parts.append(line)

                # Check if we're approaching limit
                current_len = sum(len(p) for p in parts)
                if current_len > max_chars * 0.8 and i < len(self.data):
                    parts.append(f"... ({len(self.data) - i} more items)")
                    break

        # Details (added only if space remains)
        if self.details:
            current_len = sum(len(p) for p in parts)
            remaining = max_chars - current_len - 50
            if remaining > 100:
                detail_text = self.details[:remaining]
                if len(self.details) > remaining:
                    detail_text += "..."
                parts.append(detail_text)

        # Action hint
        if self.action_hint:
            parts.append(f"Next: {self.action_hint}")

        result = "\n".join(parts)
        return result[:max_chars]


def truncate_smart(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Truncate text at a sentence/paragraph boundary when possible."""
    if len(text) <= max_chars:
        return text

    # Try to cut at paragraph boundary
    cutoff = text[:max_chars]
    last_para = cutoff.rfind("\n\n")
    if last_para > max_chars * 0.5:
        return cutoff[:last_para] + "\n... (truncated)"

    # Try sentence boundary
    last_period = cutoff.rfind(". ")
    if last_period > max_chars * 0.5:
        return cutoff[: last_period + 1] + " ... (truncated)"

    return cutoff + "... (truncated)"


def compress_result(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Compress a tool result by removing redundant whitespace and truncating."""
    import re

    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)
    # Strip each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return truncate_smart(text, max_chars)
