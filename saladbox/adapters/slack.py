"""Slack adapter using slack_bolt with Socket Mode."""

from __future__ import annotations

import logging
import re

from saladbox.adapters.base import BaseAdapter
from saladbox.config import AppConfig
from saladbox.core.chat_store import ChatStore
from saladbox.core.engine import AgentEngine
from saladbox.core.types import ConversationContext

logger = logging.getLogger(__name__)


class SlackAdapter(BaseAdapter):
    """Slack bot using Socket Mode (no public URL needed)."""

    def __init__(self, engine: AgentEngine, config: AppConfig, chat_store: ChatStore | None = None):
        super().__init__(engine, config, chat_store=chat_store)
        self._app = None
        self._handler = None

    def _setup(self):
        """Lazy import and setup to avoid import errors when Slack is disabled."""
        bot_token = self._config.slack.bot_token
        app_token = self._config.slack.app_token

        if not bot_token or not bot_token.startswith("xoxb-"):
            raise ValueError(
                "Invalid Slack bot token. Expected format: xoxb-... "
                "Get yours at https://api.slack.com/apps"
            )
        if not app_token or not app_token.startswith("xapp-"):
            raise ValueError(
                "Invalid Slack app token. Expected format: xapp-... "
                "Enable Socket Mode in your Slack app settings."
            )

        from slack_bolt.async_app import AsyncApp
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

        self._app = AsyncApp(token=bot_token)
        self._handler = AsyncSocketModeHandler(self._app, app_token)
        self._register_handlers()

    def _register_handlers(self):
        @self._app.event("app_mention")
        async def on_mention(event, say):
            # Strip the bot mention from the text
            text = re.sub(r"<@[A-Z0-9]+>\s*", "", event.get("text", "")).strip()
            if not text:
                await say("How can I help you?")
                return

            context = ConversationContext(
                conversation_id=f"slack:{event['channel']}:{event['user']}",
                user_id=event["user"],
                channel_id=event["channel"],
                platform="slack",
            )

            try:
                response = await self.handle_message(text, context)
                # Slack has a 4000 char limit per message
                for i in range(0, len(response), 3900):
                    await say(response[i:i + 3900])
            except Exception as e:
                logger.exception("Error handling Slack mention")
                await say(f"Sorry, I encountered an error: {e}")

        @self._app.event("message")
        async def on_dm(event, say):
            # Only respond to DMs (no channel_type means it's not a DM)
            if event.get("channel_type") != "im":
                return
            # Ignore bot messages
            if event.get("bot_id"):
                return

            text = event.get("text", "").strip()
            if not text:
                return

            context = ConversationContext(
                conversation_id=f"slack:dm:{event['user']}",
                user_id=event["user"],
                channel_id=event.get("channel"),
                platform="slack",
            )

            try:
                response = await self.handle_message(text, context)
                for i in range(0, len(response), 3900):
                    await say(response[i:i + 3900])
            except Exception as e:
                logger.exception("Error handling Slack DM")
                await say(f"Sorry, I encountered an error: {e}")

    async def start(self) -> None:
        self._setup()
        logger.info("Starting Slack adapter (Socket Mode)")
        await self._handler.start_async()

    async def stop(self) -> None:
        if self._handler:
            await self._handler.close_async()
            logger.info("Slack adapter stopped")
