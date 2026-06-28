"""Telegram adapter using python-telegram-bot with image/vision support."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from saladbox.adapters.base import BaseAdapter
from saladbox.config import AppConfig
from saladbox.core.chat_store import ChatStore
from saladbox.core.engine import AgentEngine
from saladbox.core.types import ConversationContext

logger = logging.getLogger(__name__)

# Directory for saving Telegram images for vision processing
_TELEGRAM_IMAGE_DIR = os.path.join(tempfile.gettempdir(), "saladbox_telegram_images")


class TelegramAdapter(BaseAdapter):
    """Telegram bot with image support and non-blocking start for asyncio coexistence."""

    def __init__(
        self,
        engine: AgentEngine,
        config: AppConfig,
        chat_store: ChatStore | None = None,
    ):
        super().__init__(engine, config, chat_store=chat_store)
        self._application = None
        self._running = asyncio.Event()
        self._active_chat_ids: set[int] = set()  # Track chats that have messaged us

    def _setup(self):
        """Lazy import and setup to avoid import errors when Telegram is disabled."""
        from telegram import Update
        from telegram.ext import (
            ApplicationBuilder,
            CommandHandler,
            ContextTypes,
            MessageHandler,
            filters,
        )

        self._application = (
            ApplicationBuilder().token(self._config.telegram.token).build()
        )

        # ── Command handlers ─────────────────────────────────────

        async def on_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                "🥗 *saladbox* is ready\\! Send me a message or image\\.\n\n"
                "*Commands:*\n"
                "/start \\- Show this message\n"
                "/clear \\- Reset conversation\n"
                "/model `<name>` \\- Switch Ollama model\n"
                "/screenshot \\- Take a screenshot of the host machine\n\n"
                "💡 *Tip:* Send a photo with a caption to ask questions about it\\!",
                parse_mode="MarkdownV2",
            )

        async def on_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            conv_id = f"telegram:{update.effective_chat.id}"
            self._engine._memory.clear(conv_id)
            await update.message.reply_text("Conversation cleared.")

        async def on_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            active_llm = self._engine._llm
            from saladbox.core.llm import OpenRouterClient
            provider = "OpenRouter" if isinstance(active_llm, OpenRouterClient) else "Ollama"

            if ctx.args:
                model_name = ctx.args[0]
                if hasattr(active_llm, "_config"):
                    active_llm._config.default_model = model_name
                if provider == "OpenRouter":
                    self._config.openrouter.default_model = model_name
                else:
                    self._config.ollama.default_model = model_name
                await update.message.reply_text(f"Switched {provider} default model to: {model_name}")
            else:
                current = getattr(active_llm._config, "default_model", "unknown") if hasattr(active_llm, "_config") else "unknown"
                await update.message.reply_text(
                    f"Current {provider} default model: {current}\n"
                    f"Usage: /model <name> (e.g., /model llama3)"
                )

        async def on_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            """Handle /screenshot command — take a screenshot on the host."""
            user = update.effective_user
            chat_id = update.effective_chat.id

            allowed = self._config.telegram.allowed_user_ids
            if allowed and user.id not in allowed:
                await update.message.reply_text("Unauthorized.")
                return

            context = ConversationContext(
                conversation_id=f"telegram:{chat_id}",
                user_id=str(user.id),
                channel_id=str(chat_id),
                platform="telegram",
            )

            await update.effective_chat.send_action("typing")

            try:
                response = await self.handle_message(
                    "Take a screenshot and describe what's on the screen.", context
                )
                await self._send_long_message(update, response)
            except Exception as e:
                logger.exception("Error handling /screenshot command")
                await update.message.reply_text(f"Error: {e}")

        # ── Message handlers ─────────────────────────────────────

        async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            """Handle text-only messages."""
            user = update.effective_user
            chat_id = update.effective_chat.id
            self._active_chat_ids.add(chat_id)

            allowed = self._config.telegram.allowed_user_ids
            if allowed and user.id not in allowed:
                await update.message.reply_text("Unauthorized.")
                return

            text = update.message.text
            if not text:
                return

            context = ConversationContext(
                conversation_id=f"telegram:{chat_id}",
                user_id=str(user.id),
                channel_id=str(chat_id),
                platform="telegram",
            )

            await update.effective_chat.send_action("typing")

            try:
                response = await self.handle_message(text, context)
                await self._send_long_message(update, response)
            except Exception as e:
                logger.exception("Error handling Telegram message")
                await update.message.reply_text(f"Sorry, an error occurred: {e}")

        async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            """Handle photo messages — download image, pass to vision model."""
            user = update.effective_user
            chat_id = update.effective_chat.id
            self._active_chat_ids.add(chat_id)

            allowed = self._config.telegram.allowed_user_ids
            if allowed and user.id not in allowed:
                await update.message.reply_text("Unauthorized.")
                return

            # Use caption as text, or default prompt
            text = update.message.caption or "Describe what you see in this image."

            await update.effective_chat.send_action("typing")

            try:
                # Download the highest resolution photo
                image_path = await self._download_photo(update.message.photo)
                if not image_path:
                    await update.message.reply_text(
                        "Sorry, I couldn't download the image."
                    )
                    return

                context = ConversationContext(
                    conversation_id=f"telegram:{chat_id}",
                    user_id=str(user.id),
                    channel_id=str(chat_id),
                    platform="telegram",
                )

                # Pass the image path to the engine for vision processing
                response = await self.handle_message(
                    text, context, images=[image_path]
                )
                await self._send_long_message(update, response)

            except Exception as e:
                logger.exception("Error handling Telegram photo")
                await update.message.reply_text(f"Sorry, an error occurred: {e}")

        async def on_document_image(
            update: Update, ctx: ContextTypes.DEFAULT_TYPE
        ):
            """Handle images sent as documents (uncompressed)."""
            user = update.effective_user
            chat_id = update.effective_chat.id

            allowed = self._config.telegram.allowed_user_ids
            if allowed and user.id not in allowed:
                await update.message.reply_text("Unauthorized.")
                return

            text = update.message.caption or "Describe what you see in this image."

            await update.effective_chat.send_action("typing")

            try:
                doc = update.message.document
                file = await doc.get_file()

                os.makedirs(_TELEGRAM_IMAGE_DIR, exist_ok=True)
                ext = os.path.splitext(doc.file_name or "image.png")[1] or ".png"
                image_path = os.path.join(
                    _TELEGRAM_IMAGE_DIR, f"telegram_doc_{doc.file_unique_id}{ext}"
                )
                await file.download_to_drive(image_path)
                logger.info(
                    f"[TELEGRAM] Downloaded document image: {image_path} "
                    f"({os.path.getsize(image_path):,} bytes)"
                )

                context = ConversationContext(
                    conversation_id=f"telegram:{chat_id}",
                    user_id=str(user.id),
                    channel_id=str(chat_id),
                    platform="telegram",
                )

                response = await self.handle_message(
                    text, context, images=[image_path]
                )
                await self._send_long_message(update, response)

            except Exception as e:
                logger.exception("Error handling Telegram document image")
                await update.message.reply_text(f"Sorry, an error occurred: {e}")

        # ── Register handlers ────────────────────────────────────

        self._application.add_handler(CommandHandler("start", on_start))
        self._application.add_handler(CommandHandler("clear", on_clear))
        self._application.add_handler(CommandHandler("model", on_model))
        self._application.add_handler(CommandHandler("screenshot", on_screenshot))

        # Photo handler (compressed images)
        self._application.add_handler(
            MessageHandler(filters.PHOTO, on_photo)
        )

        # Document images (uncompressed — sent as file)
        self._application.add_handler(
            MessageHandler(
                filters.Document.IMAGE & ~filters.COMMAND, on_document_image
            )
        )

        # Text handler (must be after photo/document handlers)
        self._application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
        )

    async def _download_photo(self, photo_sizes: list) -> str | None:
        """Download the highest-res photo from Telegram and save to disk.

        Returns the local file path, or None on failure.
        """
        if not photo_sizes:
            return None

        try:
            os.makedirs(_TELEGRAM_IMAGE_DIR, exist_ok=True)

            # Telegram sends multiple sizes; last one is highest resolution
            best_photo = photo_sizes[-1]
            file = await best_photo.get_file()

            image_path = os.path.join(
                _TELEGRAM_IMAGE_DIR,
                f"telegram_{best_photo.file_unique_id}.jpg",
            )
            await file.download_to_drive(image_path)

            file_size = os.path.getsize(image_path)
            logger.info(
                f"[TELEGRAM] Downloaded photo: {image_path} ({file_size:,} bytes)"
            )
            return image_path

        except Exception as e:
            logger.exception(f"[TELEGRAM] Failed to download photo: {e}")
            return None

    async def _send_long_message(self, update, text: str) -> None:
        """Send a response, splitting into chunks if needed.

        Strips markdown image tags (![...](url)) since Telegram can't render them,
        and sends the screenshot as a photo if available.
        """
        import re

        # Extract image URLs from markdown images (screenshots + generated)
        image_urls = re.findall(
            r"!\[.*?\]\((http://127\.0\.0\.1:\d+/(?:screenshots|generated)/[^)]+)\)",
            text,
        )

        # Remove markdown image syntax for Telegram
        clean_text = re.sub(r"!\[.*?\]\([^)]+\)\s*", "", text).strip()

        if not clean_text and image_urls:
            clean_text = "Here's the result."

        # Send images as photos if we have local files
        for url in image_urls:
            # Extract filename and determine directory from URL
            parts = url.rsplit("/", 2)  # [..., "screenshots"|"generated", filename]
            if len(parts) >= 2:
                filename = parts[-1]
                url_type = parts[-2]
                if url_type == "screenshots":
                    local_path = os.path.join(tempfile.gettempdir(), "saladbox_screenshots", filename)
                elif url_type == "generated":
                    local_path = os.path.join(tempfile.gettempdir(), "saladbox_generated_images", filename)
                else:
                    continue

                if os.path.isfile(local_path):
                    try:
                        with open(local_path, "rb") as photo_file:
                            await update.message.reply_photo(
                                photo=photo_file,
                                caption=(
                                    clean_text[:1024]
                                    if len(clean_text) <= 1024
                                    else None
                                ),
                            )
                        # If the full text was used as caption, we're done
                        if len(clean_text) <= 1024:
                            return
                    except Exception as e:
                        logger.warning(
                            f"[TELEGRAM] Failed to send photo: {e}"
                        )

        # Telegram has a 4096 char limit per message
        for i in range(0, len(clean_text), 4000):
            chunk = clean_text[i : i + 4000]
            await update.message.reply_text(chunk)

    async def send_notification(self, message: str) -> None:
        """Send a proactive notification to all active Telegram chats.

        Used by the reminder system to deliver due reminders.
        """
        if not self._application or not self._active_chat_ids:
            logger.warning(
                "[TELEGRAM] Cannot send notification: "
                f"app={'yes' if self._application else 'no'}, "
                f"chats={len(self._active_chat_ids)}"
            )
            return

        for chat_id in list(self._active_chat_ids):
            try:
                await self._application.bot.send_message(
                    chat_id=chat_id,
                    text=f"\U0001f514 {message}",
                )
                logger.info(f"[TELEGRAM] Sent notification to chat {chat_id}")
            except Exception as e:
                logger.error(
                    f"[TELEGRAM] Failed to send notification to {chat_id}: {e}"
                )

    async def start(self) -> None:
        """Start polling for Telegram messages."""
        self._setup()
        logger.info("Starting Telegram adapter")
        self._running = asyncio.Event()

        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling()
        logger.info("Telegram adapter started — polling for messages")

        # Keep running until stopped
        await self._running.wait()

    async def stop(self) -> None:
        """Stop the Telegram bot gracefully."""
        self._running.set()  # Signal start() to exit
        if self._application:
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()
            logger.info("Telegram adapter stopped")

        # Clean up temp images
        self._cleanup_images()

    def _cleanup_images(self) -> None:
        """Remove temporary Telegram images."""
        try:
            if os.path.isdir(_TELEGRAM_IMAGE_DIR):
                for f in os.listdir(_TELEGRAM_IMAGE_DIR):
                    fpath = os.path.join(_TELEGRAM_IMAGE_DIR, f)
                    if os.path.isfile(fpath):
                        os.remove(fpath)
        except OSError:
            pass
