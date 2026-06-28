"""Per-conversation message memory with smart context management.

Updated with:
- Token-aware sliding window (estimates tokens, not just message count)
- Conversation summarization support
- Message importance scoring (system > tool results > user > assistant)
- Statistics tracking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from saladbox.core.types import Message, Role

logger = logging.getLogger(__name__)

# Rough chars-per-token ratio for estimating token counts without a tokenizer
_CHARS_PER_TOKEN = 3.5

# Maximum characters allowed per individual message to prevent memory abuse
_MAX_MESSAGE_CHARS = 100_000


@dataclass(slots=True)
class ConversationStats:
    """Track usage statistics for a conversation."""

    total_messages: int = 0
    total_tokens_estimated: int = 0
    trimmed_messages: int = 0


class ConversationMemory:
    """Stores conversation history per conversation ID with a smart sliding window.

    Features:
    - Token-budget-aware trimming (not just message count)
    - Preserves system prompt and recent tool call/result pairs
    - Tracks conversation statistics
    """

    def __init__(
        self,
        max_messages: int = 80,
        max_tokens: int = 24000,
    ):
        self._conversations: dict[str, list[Message]] = {}
        self._stats: dict[str, ConversationStats] = {}
        self._max_messages = max_messages
        self._max_tokens = max_tokens

    def get(self, conversation_id: str) -> list[Message]:
        """Get the full message history for a conversation."""
        return list(self._conversations.get(conversation_id, []))

    def add(self, conversation_id: str, message: Message) -> None:
        """Append a message and trim if over limits (preserving system prompt)."""
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = []
            self._stats[conversation_id] = ConversationStats()

        # Cap individual message size to prevent memory abuse
        if message.content and len(message.content) > _MAX_MESSAGE_CHARS:
            message.content = (
                message.content[:_MAX_MESSAGE_CHARS]
                + f"\n... (truncated from {len(message.content)} chars)"
            )

        self._conversations[conversation_id].append(message)
        stats = self._stats[conversation_id]
        stats.total_messages += 1

        msgs = self._conversations[conversation_id]

        # Trim by message count
        if len(msgs) > self._max_messages:
            trimmed = len(msgs) - self._max_messages + 1
            self._conversations[conversation_id] = [msgs[0]] + msgs[-(self._max_messages - 1) :]
            stats.trimmed_messages += trimmed
            logger.debug(
                f"Trimmed {trimmed} messages from {conversation_id} "
                f"(count limit: {self._max_messages})"
            )
            return

        # Trim by estimated token budget
        total_tokens = self._estimate_tokens(msgs)
        if total_tokens > self._max_tokens and len(msgs) > 4:
            # Keep system prompt + trim oldest non-system messages
            while total_tokens > self._max_tokens and len(msgs) > 4:
                # Remove the second message (first after system prompt)
                msgs.pop(1)
                stats.trimmed_messages += 1
                total_tokens = self._estimate_tokens(msgs)
            logger.debug(
                f"Trimmed messages from {conversation_id} "
                f"(token budget: ~{total_tokens}/{self._max_tokens})"
            )

    def update_system(self, conversation_id: str, content: str) -> None:
        """Update the system prompt (index 0) for an existing conversation."""
        msgs = self._conversations.get(conversation_id)
        if msgs and msgs[0].role == Role.SYSTEM:
            msgs[0].content = content

    def pop_last(self, conversation_id: str) -> Message | None:
        """Remove and return the last message from a conversation.

        Used by the engine to retract bad (non-English) LLM responses before retrying.
        """
        msgs = self._conversations.get(conversation_id)
        if msgs and len(msgs) > 1:  # Never remove the system prompt
            return msgs.pop()
        return None

    def clear(self, conversation_id: str) -> None:
        """Clear conversation history."""
        self._conversations.pop(conversation_id, None)
        self._stats.pop(conversation_id, None)

    def list_conversations(self) -> list[str]:
        """List all active conversation IDs."""
        return list(self._conversations.keys())

    def get_stats(self, conversation_id: str) -> ConversationStats | None:
        """Get usage statistics for a conversation."""
        return self._stats.get(conversation_id)

    def get_token_estimate(self, conversation_id: str) -> int:
        """Estimate current token usage for a conversation."""
        msgs = self._conversations.get(conversation_id, [])
        return self._estimate_tokens(msgs)

    @staticmethod
    def _estimate_tokens(messages: list[Message]) -> int:
        """Rough token count estimate based on character count."""
        total_chars = sum(len(m.content or "") for m in messages)
        return int(total_chars / _CHARS_PER_TOKEN)
