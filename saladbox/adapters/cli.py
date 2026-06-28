"""CLI adapter for local testing and direct interaction."""

from __future__ import annotations

import asyncio
import logging
import re

from saladbox.adapters.base import BaseAdapter
from saladbox.core.types import ConversationContext

logger = logging.getLogger(__name__)


def strip_markdown(text: str) -> str:
    """Remove markdown formatting for clean terminal output."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"```(\w*)\n?", "", text)
    text = re.sub(r"```", "", text)
    text = re.sub(r"^[-•]\s+", "  • ", text, flags=re.MULTILINE)
    return text


def format_response(text: str) -> str:
    """Format response with proper indentation for CLI."""
    lines = text.strip().split("\n")
    formatted = []

    for line in lines:
        line = line.rstrip()
        if line:
            formatted.append(f"    {line}")
        else:
            formatted.append("")

    return "\n".join(formatted)


class CLIAdapter(BaseAdapter):
    """Interactive command-line interface for the bot."""

    async def start(self) -> None:
        """Run an interactive CLI loop."""
        context = ConversationContext(
            conversation_id="cli:local",
            user_id="local",
            platform="cli",
        )

        print("\n╔══════════════════════════════════════╗")
        print("║         saladbox CLI                 ║")
        print("║  Type 'quit' to exit                 ║")
        print("║  Type 'clear' to reset conversation  ║")
        print("╚══════════════════════════════════════╝\n")

        loop = asyncio.get_event_loop()

        while True:
            try:
                user_input = await loop.run_in_executor(None, lambda: input("you> "))
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            text = user_input.strip()
            if not text:
                continue
            if text.lower() in ("quit", "exit"):
                print("Goodbye!")
                break
            if text.lower() == "clear":
                self._engine._memory.clear(context.conversation_id)
                print("Conversation cleared.\n")
                continue

            try:
                response = await self.handle_message(text, context)
                clean_response = strip_markdown(response)
                print(f"\nbot>\n{format_response(clean_response)}\n")
            except Exception as e:
                logger.exception("Error processing message")
                print(f"\nError: {e}\n")

    async def stop(self) -> None:
        pass
