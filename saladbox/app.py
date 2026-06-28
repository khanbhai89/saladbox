"""Application orchestrator: wires all components and manages lifecycle.

Updated: parallel tool calls, reasoning model support, token-aware memory.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from saladbox.adapters.base import BaseAdapter
from saladbox.adapters.cli import CLIAdapter
from saladbox.config import AppConfig
from saladbox.core.chat_store import ChatStore
from saladbox.core.engine import AgentEngine
from saladbox.core.llm import create_llm_client
from saladbox.core.mcp_client import MCPManager, MCPServerConfig
from saladbox.core.memory import ConversationMemory
from saladbox.core.skills import SkillManager
from saladbox.core.tool_registry import ToolRegistry
from saladbox.tools import get_enabled_tools

logger = logging.getLogger(__name__)


class Application:
    """Main application that initializes and runs all components."""

    def __init__(
        self, config: AppConfig, http_mode: bool = False, http_port: int = 8765
    ):
        self.config = config
        self.http_mode = http_mode
        self.http_port = http_port
        self.llm = create_llm_client(config.ollama, config.openrouter, agent_config=config.agent)
        # Token-aware memory: budget based on context length and budget ratio
        max_tokens = int(
            config.ollama.context_length * config.agent.context_budget_ratio
        )
        self.memory = ConversationMemory(max_messages=80, max_tokens=max_tokens)
        self.tools = ToolRegistry()
        self.mcp_manager = MCPManager()
        self.skill_manager = SkillManager()
        self.chat_store = ChatStore()
        self.engine = AgentEngine(
            self.llm,
            self.memory,
            self.tools,
            config,
            skill_manager=self.skill_manager,
        )
        self.adapters: list[BaseAdapter] = []

    def setup(self):
        """Register native tools and create adapters based on config.

        In HTTP mode, also starts Telegram/Slack adapters if enabled,
        so the Electron app and messaging bots run simultaneously.
        """
        # Register native tools
        enabled_tools = get_enabled_tools(self.config.tools)
        self.tools.register_tools(enabled_tools)
        logger.info(
            f"Registered {len(enabled_tools)} native tools: {self.tools.tool_names}"
        )

        # Load skills
        if self.config.skills.enabled:
            skills_dir = self.config.skills.directory
            if not skills_dir:
                skills_dir = str(Path(__file__).parent.parent / "skills")
            count = self.skill_manager.load_skills(skills_dir)
            logger.info(f"Loaded {count} skills: {self.skill_manager.skill_names}")

        # HTTP adapter for Electron/desktop apps
        if self.http_mode:
            from saladbox.adapters.http import HTTPAdapter

            self.adapters.append(
                HTTPAdapter(
                    self.engine,
                    self.config,
                    port=self.http_port,
                    chat_store=self.chat_store,
                )
            )
            logger.info(f"HTTP adapter enabled on port {self.http_port}")

        # Messaging platform adapters (run alongside HTTP if enabled)
        if self.config.slack.enabled and self.config.slack.bot_token:
            from saladbox.adapters.slack import SlackAdapter

            self.adapters.append(
                SlackAdapter(self.engine, self.config, chat_store=self.chat_store)
            )
            logger.info("Slack adapter enabled")

        if self.config.telegram.enabled and self.config.telegram.token:
            from saladbox.adapters.telegram import TelegramAdapter

            self.adapters.append(
                TelegramAdapter(self.engine, self.config, chat_store=self.chat_store)
            )
            logger.info("Telegram adapter enabled")

        # Fall back to CLI only when no adapters are configured
        if not self.adapters:
            self.adapters.append(
                CLIAdapter(self.engine, self.config, chat_store=self.chat_store)
            )
            logger.info("No messaging platforms configured, using CLI mode")

        # Wire up reminder notifications to messaging adapters
        self._setup_reminder_notifications()

        # Configure image generation tool from config
        self._setup_image_gen()

    def _setup_reminder_notifications(self) -> None:
        """Wire reminder tool notifications to active messaging adapters."""
        from saladbox.tools.reminder import ReminderTool

        # Collect adapters that can send proactive notifications
        notification_adapters = []
        for adapter in self.adapters:
            if hasattr(adapter, "send_notification"):
                notification_adapters.append(adapter)

        if not notification_adapters:
            logger.info("No notification-capable adapters found for reminders")
            return

        adapter_names = [type(a).__name__ for a in notification_adapters]
        logger.info(f"Wiring reminder notifications to: {adapter_names}")

        async def _reminder_callback(message: str, metadata: dict) -> None:
            """Deliver reminder to all notification-capable adapters."""
            execute_prompt = metadata.get("execute_prompt")
            
            if execute_prompt:
                logger.info(f"Executing background task from reminder: {execute_prompt}")
                from saladbox.core.types import ConversationContext
                context = ConversationContext(
                    conversation_id="background:system",
                    user_id="system",
                    channel_id="background",
                    platform="system"
                )
                
                async def _run_agent():
                    try:
                        response = await self.engine.process(execute_prompt, context)
                        # Optionally notify with the final result
                        if response.strip():
                            for adapter in notification_adapters:
                                try:
                                    await adapter.send_notification(f"Task result: {response}")
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.error(f"Background task failed: {e}")
                
                asyncio.create_task(_run_agent())

            for adapter in notification_adapters:
                try:
                    await adapter.send_notification(message)
                except Exception as e:
                    logger.error(
                        f"Failed to send reminder via {type(adapter).__name__}: {e}"
                    )

        ReminderTool.set_notify_callback(_reminder_callback)

        # Start the checker loop immediately if there are existing reminders
        # (otherwise it only starts when execute() is first called)
        reminder_tool = self.tools.get("reminder")
        if reminder_tool and reminder_tool._reminders:
            logger.info(
                f"Starting reminder checker for {len(reminder_tool._reminders)} "
                f"existing reminder(s)"
            )
            reminder_tool._start_checker()

    def _setup_image_gen(self) -> None:
        """Apply image generation config to the ImageGenTool."""
        try:
            from saladbox.tools.image_gen import ImageGenTool

            ImageGenTool.configure(self.config.image_gen)
            logger.info(
                f"Image gen configured: backend={self.config.image_gen.backend}, "
                f"model={self.config.image_gen.model}, "
                f"quantize={self.config.image_gen.quantize}"
            )
        except Exception as e:
            logger.warning(f"Failed to configure image gen: {e}")

    async def _start_mcp_servers(self) -> None:
        """Start MCP servers and register their discovered tools."""
        if not self.config.mcp_servers:
            return

        # Convert config entries to MCPServerConfig objects
        mcp_configs = [
            MCPServerConfig(
                name=entry.name,
                command=entry.command,
                args=entry.args,
                env=entry.env,
                enabled=entry.enabled,
            )
            for entry in self.config.mcp_servers
        ]

        await self.mcp_manager.start_servers(mcp_configs)

        # Register discovered MCP tools into the main ToolRegistry
        mcp_tools = self.mcp_manager.tools
        if mcp_tools:
            self.tools.register_tools(mcp_tools)
            logger.info(
                f"Registered {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}"
            )

            # Refresh the system prompt for new conversations
            # (existing conversations keep their original tool list)
            logger.info(f"Total tools now available: {self.tools.tool_names}")

    async def run(self):
        """Start all adapters and wait for shutdown signal."""
        self.setup()

        # Start MCP servers (async — needs event loop)
        await self._start_mcp_servers()

        stop_event = asyncio.Event()

        def _signal_handler():
            logger.info("Shutdown signal received")
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                pass

        tasks = []
        for adapter in self.adapters:
            task = asyncio.create_task(adapter.start(), name=type(adapter).__name__)
            tasks.append(task)

        adapter_names = [type(a).__name__ for a in self.adapters]
        logger.info(f"Running adapters: {adapter_names}")

        wait_tasks = [asyncio.create_task(stop_event.wait())]

        if not self.http_mode:
            # In non-HTTP mode, also exit when a primary adapter finishes
            # (e.g. CLI adapter exits on user "exit" command)
            wait_tasks.extend(tasks)
        else:
            # In HTTP mode, adapter tasks run in the background.
            # Monitor them for crashes — if any adapter fails, signal shutdown.
            def _on_adapter_crash(t: asyncio.Task):
                if not t.cancelled() and t.exception():
                    logger.error(f"Adapter {t.get_name()} crashed: {t.exception()}")
                    stop_event.set()

            for task in tasks:
                task.add_done_callback(_on_adapter_crash)

        try:
            done, pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("Shutting down...")

            # Stop MCP servers
            try:
                await self.mcp_manager.stop_all()
            except Exception as e:
                logger.error(f"Error stopping MCP servers: {e}")

            for adapter in self.adapters:
                try:
                    await adapter.stop()
                except Exception as e:
                    logger.error(f"Error stopping adapter {type(adapter).__name__}: {e}")

            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            # Close chat store — always, even on crash
            if self.chat_store:
                try:
                    self.chat_store.close()
                except Exception as e:
                    logger.error(f"Error closing chat store: {e}")

            logger.info("Shutdown complete")
