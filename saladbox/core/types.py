"""Shared data types for the saladbox system.

Uses modern Python 3.12+ typing features: StrEnum, slots, type aliases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    """Message role in a conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class TaskType(StrEnum):
    """Model tier classification for routing to the right model."""

    FAST = "fast"
    DEFAULT = "default"
    CODE = "code"
    VISION = "vision"
    REASONING = "reasoning"


class ToolCategory(StrEnum):
    """Logical grouping for tools."""

    SYSTEM = "system"
    FILES = "files"
    CODE = "code"
    WEB = "web"
    MEDIA = "media"
    UTILITY = "utility"
    DATA = "data"


@dataclass(slots=True)
class ToolCall:
    """A tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    """Result from executing a tool."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False
    duration_ms: float = 0.0


@dataclass(slots=True)
class TokenUsage:
    """Token usage tracking for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class Message:
    """A single message in a conversation."""

    role: Role
    content: str
    images: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage | None = None


@dataclass(slots=True)
class ConversationContext:
    """Context for a conversation across platforms."""

    conversation_id: str  # e.g. "slack:C12345:U67890" or "telegram:12345"
    user_id: str
    channel_id: str | None = None
    platform: str = "cli"  # "slack", "telegram", "cli", "http"


# Type aliases for common patterns
ToolSchemaList = list[dict[str, Any]]
MessageList = list[Message]
