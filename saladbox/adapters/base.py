"""Base adapter interface for messaging platforms."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from saladbox.config import AppConfig
from saladbox.core.chat_store import ChatStore
from saladbox.core.engine import AgentEngine
from saladbox.core.types import ConversationContext

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """All messaging adapters implement this interface."""

    def __init__(
        self,
        engine: AgentEngine,
        config: AppConfig,
        chat_store: ChatStore | None = None,
    ):
        self._engine = engine
        self._config = config
        self._chat_store = chat_store

    @abstractmethod
    async def start(self) -> None:
        """Start listening for messages."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown."""
        ...

    async def handle_message(
        self,
        text: str,
        context: ConversationContext,
        images: list[str] | None = None,
        **kwargs,
    ) -> str:
        """Forward a message to the engine, persist to chat store, and return the response."""
        # Persist user message
        if self._chat_store:
            try:
                self._chat_store.save_message(
                    conversation_id=context.conversation_id,
                    role="user",
                    content=text,
                    platform=context.platform,
                    user_id=context.user_id,
                    channel_id=context.channel_id,
                )
            except Exception as e:
                logger.error(f"Failed to persist user message: {e}")

        response = await self._engine.process(text, context, images=images, **kwargs)

        # Persist assistant response
        if self._chat_store:
            try:
                self._chat_store.save_message(
                    conversation_id=context.conversation_id,
                    role="assistant",
                    content=response,
                    platform=context.platform,
                    user_id=context.user_id,
                    channel_id=context.channel_id,
                )
            except Exception as e:
                logger.error(f"Failed to persist assistant message: {e}")

        return response
