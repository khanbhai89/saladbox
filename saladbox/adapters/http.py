"""HTTP adapter with WebSocket support for Electron/desktop apps."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from aiohttp import web

from saladbox.adapters.base import BaseAdapter
from saladbox.core.types import ConversationContext
from saladbox.core.whisper_service import WhisperService

if TYPE_CHECKING:
    from saladbox.config import AppConfig
    from saladbox.core.chat_store import ChatStore
    from saladbox.core.engine import AgentEngine

# Screenshot directory (must match screen_capture tool and engine)
_SCREENSHOT_DIR = os.path.join(tempfile.gettempdir(), "saladbox_screenshots")
# Generated image directory (must match image_gen tool and engine)
_GENERATED_IMAGE_DIR = os.path.join(tempfile.gettempdir(), "saladbox_generated_images")

logger = logging.getLogger(__name__)


class HTTPAdapter(BaseAdapter):
    """HTTP server with WebSocket support for desktop apps."""

    def __init__(
        self,
        engine: AgentEngine,
        config: AppConfig,
        host: str = "127.0.0.1",
        port: int = 8765,
        chat_store: ChatStore | None = None,
    ):
        super().__init__(engine, config, chat_store=chat_store)
        self.host = host
        self.port = port
        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None
        self.websocket_clients: list[web.WebSocketResponse] = []
        self._notification_queue: list[dict] = []
        self._whisper: WhisperService | None = None
        if config.whisper.enabled:
            self._whisper = WhisperService(config.whisper)

    _MAX_NOTIFICATION_QUEUE = 500

    async def send_notification(self, message: str) -> None:
        """Queue a notification for the Electron app to poll."""
        import time as _time

        notification = {
            "message": message,
            "timestamp": _time.time(),
        }
        self._notification_queue.append(notification)
        # Cap the queue to prevent unbounded memory growth
        if len(self._notification_queue) > self._MAX_NOTIFICATION_QUEUE:
            self._notification_queue = self._notification_queue[-self._MAX_NOTIFICATION_QUEUE:]
        logger.info(f"[HTTP] Notification queued: {message}")

        # Also push via WebSocket if any clients connected
        payload = {"type": "notification", "message": message}
        for ws in list(self.websocket_clients):
            try:
                if not ws.closed:
                    await ws.send_json(payload)
            except Exception:
                pass

    async def handle_chat(self, request: web.Request) -> web.Response:
        """Handle POST /chat requests."""
        try:
            data = await request.json()
            message = data.get("message", "")
            images = data.get("images", [])
            conversation_id = data.get("conversation_id", "default")
            user_id = data.get("user_id", "electron-user")
            stream = data.get("stream", False)

            if not message and not images:
                return web.json_response(
                    {"error": "message or images is required"}, status=400
                )

            if ":" in conversation_id:
                parts = conversation_id.split(":", 1)
                platform = parts[0]
                full_conv_id = conversation_id
            else:
                platform = "http"
                full_conv_id = f"http:{conversation_id}"

            context = ConversationContext(
                conversation_id=full_conv_id,
                user_id=user_id,
                channel_id=conversation_id,
                platform=platform,
            )

            if stream:
                response = web.StreamResponse()
                response.headers["Content-Type"] = "text/event-stream"
                await response.prepare(request)

                chunks = []

                async def on_chunk(chunk: str):
                    chunks.append(chunk)
                    await response.write(
                        f"data: {json.dumps({'chunk': chunk})}\n\n".encode()
                    )

                result = await self.handle_message(message, context, on_chunk=on_chunk)
                await response.write(
                    f"data: {json.dumps({'done': True, 'message': result})}\n\n".encode()
                )
                await response.write_eof()
                return response
            else:
                response = await self.handle_message(message, context, images=images)
                return web.json_response(
                    {"message": response, "conversation_id": conversation_id}
                )

        except Exception as e:
            logger.exception("Error handling chat request")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections for real-time chat."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.websocket_clients.append(ws)

        conversation_id = "default"
        user_id = "ws-user"

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)

                        if data.get("type") == "init":
                            conversation_id = data.get(
                                "conversation_id", conversation_id
                            )
                            user_id = data.get("user_id", user_id)
                            await ws.send_json(
                                {"type": "ready", "conversation_id": conversation_id}
                            )
                            continue

                        if data.get("type") == "chat":
                            message = data.get("message", "")
                            if not message:
                                continue

                            if ":" in conversation_id:
                                parts = conversation_id.split(":", 1)
                                platform = parts[0]
                                full_conv_id = conversation_id
                            else:
                                platform = "websocket"
                                full_conv_id = f"ws:{conversation_id}"

                            context = ConversationContext(
                                conversation_id=full_conv_id,
                                user_id=user_id,
                                channel_id=conversation_id,
                                platform=platform,
                            )

                            images = data.get("images", [])

                            chunks = []

                            async def on_chunk(chunk: str):
                                chunks.append(chunk)
                                await ws.send_json({"type": "chunk", "chunk": chunk})

                            response = await self.handle_message(
                                message, context, images=images, on_chunk=on_chunk
                            )
                            await ws.send_json({"type": "done", "message": response})

                        if data.get("type") == "clear":
                            self._engine._memory.clear(f"ws:{conversation_id}")
                            await ws.send_json({"type": "cleared"})

                    except json.JSONDecodeError:
                        await ws.send_json({"type": "error", "error": "Invalid JSON"})
                    except Exception as e:
                        logger.exception("WebSocket error")
                        await ws.send_json({"type": "error", "error": str(e)})

        finally:
            try:
                self.websocket_clients.remove(ws)
            except ValueError:
                pass  # already removed (e.g. during shutdown)

        return ws

    async def handle_models(self, request: web.Request) -> web.Response:
        """Return available model configurations."""
        return web.json_response(
            {
                "ollama": {
                    "enabled": not self._config.openrouter.enabled,
                    "default_model": self._config.ollama.default_model,
                    "code_model": self._config.ollama.code_model,
                    "fast_model": self._config.ollama.fast_model,
                },
                "openrouter": {
                    "enabled": self._config.openrouter.enabled,
                    "default_model": self._config.openrouter.default_model,
                    "code_model": self._config.openrouter.code_model,
                    "fast_model": self._config.openrouter.fast_model,
                },
            }
        )

    async def handle_tools(self, request: web.Request) -> web.Response:
        """Return list of available tools."""
        tools = []
        for name, enabled in self._config.tools.items():
            tools.append({"name": name, "enabled": enabled})
        return web.json_response({"tools": tools})

    async def handle_config(self, request: web.Request) -> web.Response:
        """Return current configuration (non-sensitive)."""
        return web.json_response(
            {
                "log_level": self._config.log_level,
                "max_tool_iterations": self._config.max_tool_iterations,
                "telegram_enabled": self._config.telegram.enabled,
                "slack_enabled": self._config.slack.enabled,
            }
        )

    async def handle_set_model(self, request: web.Request) -> web.Response:
        """Update model configuration."""
        try:
            data = await request.json()
            provider = data.get("provider", "ollama")
            model_type = data.get("type", "default")
            model_name = data.get("model", "")

            if not model_name:
                return web.json_response({"error": "model is required"}, status=400)

            config = self._config.openrouter if provider == "openrouter" else self._config.ollama

            if model_type == "default":
                config.default_model = model_name
            elif model_type == "code":
                config.code_model = model_name
            elif model_type == "fast":
                config.fast_model = model_name
            else:
                return web.json_response({"error": "Invalid model type"}, status=400)

            logger.info(f"Updated {provider} {model_type}_model to {model_name}")
            return web.json_response({"success": True, "model": model_name})

        except Exception as e:
            logger.exception("Error setting model")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        from saladbox import __version__
        return web.json_response({"status": "ok", "version": __version__})

    async def handle_mcp_servers(self, request: web.Request) -> web.Response:
        """Return list of configured MCP servers."""
        servers = []
        for server in self._config.mcp_servers:
            servers.append(
                {
                    "name": server.name,
                    "command": server.command,
                    "args": server.args,
                    "env": {
                        k: "***" if "token" in k.lower() or "key" in k.lower() else v
                        for k, v in server.env.items()
                    },
                    "enabled": server.enabled,
                }
            )
        return web.json_response({"servers": servers})

    async def handle_mcp_add(self, request: web.Request) -> web.Response:
        """Add or update an MCP server configuration."""
        try:
            data = await request.json()
            name = data.get("name", "").strip()
            command = data.get("command", "").strip()
            args = data.get("args", [])
            env = data.get("env", {})
            enabled = data.get("enabled", True)

            if not name:
                return web.json_response({"error": "name is required"}, status=400)
            if not command:
                return web.json_response({"error": "command is required"}, status=400)

            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config.yaml"

            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}

            if "mcp_servers" not in config_data:
                config_data["mcp_servers"] = {}

            config_data["mcp_servers"][name] = {
                "command": command,
                "args": args,
                "env": env,
                "enabled": enabled,
            }

            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            return web.json_response(
                {
                    "success": True,
                    "name": name,
                    "message": "MCP server added. Restart Saladbox to apply changes.",
                }
            )

        except Exception as e:
            logger.exception("Error adding MCP server")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_mcp_remove(self, request: web.Request) -> web.Response:
        """Remove an MCP server configuration."""
        try:
            data = await request.json()
            name = data.get("name", "").strip()

            if not name:
                return web.json_response({"error": "name is required"}, status=400)

            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config.yaml"

            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}

            if "mcp_servers" in config_data and name in config_data["mcp_servers"]:
                del config_data["mcp_servers"][name]

                with open(config_path, "w") as f:
                    yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

                return web.json_response(
                    {
                        "success": True,
                        "message": "MCP server removed. Restart Saladbox to apply changes.",
                    }
                )

            return web.json_response(
                {"error": f"MCP server '{name}' not found"}, status=404
            )

        except Exception as e:
            logger.exception("Error removing MCP server")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_mcp_toggle(self, request: web.Request) -> web.Response:
        """Toggle an MCP server enabled status."""
        try:
            data = await request.json()
            name = data.get("name", "").strip()
            enabled = data.get("enabled", True)

            if not name:
                return web.json_response({"error": "name is required"}, status=400)

            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config.yaml"

            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}

            if (
                "mcp_servers" not in config_data
                or name not in config_data["mcp_servers"]
            ):
                return web.json_response(
                    {"error": f"MCP server '{name}' not found"}, status=404
                )

            config_data["mcp_servers"][name]["enabled"] = enabled

            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            return web.json_response(
                {
                    "success": True,
                    "message": "MCP server updated. Restart Saladbox to apply changes.",
                }
            )

        except Exception as e:
            logger.exception("Error toggling MCP server")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_setup_status(self, request: web.Request) -> web.Response:
        """Check if initial setup is needed."""
        project_root = Path(__file__).parent.parent.parent
        env_path = project_root / ".env"
        config_path = project_root / "config.yaml"

        needs_setup = False
        has_config = config_path.exists()
        has_env = env_path.exists()

        if has_env:
            env_content = env_path.read_text()
            has_api_key = any(
                key in env_content
                for key in [
                    "OPENROUTER_API_KEY",
                    "TELEGRAM_BOT_TOKEN",
                    "SLACK_BOT_TOKEN",
                ]
            )
            if not has_api_key:
                needs_setup = True
        else:
            needs_setup = True

        return web.json_response(
            {
                "needs_setup": needs_setup,
                "has_config": has_config,
                "has_env": has_env,
            }
        )

    async def handle_setup_run(self, request: web.Request) -> web.Response:
        """Run setup with provided configuration."""
        try:
            data = await request.json()

            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config.yaml"
            env_path = project_root / ".env"

            env_vars = {}
            config_updates = {}

            provider = data.get("provider", "ollama")

            if provider == "ollama":
                config_updates["openrouter"] = {"enabled": False}
                config_updates["ollama"] = {
                    "default_model": data.get("default_model", "llama3"),
                    "code_model": data.get(
                        "code_model", data.get("default_model", "llama3")
                    ),
                    "fast_model": data.get(
                        "fast_model", data.get("default_model", "llama3")
                    ),
                }
            elif provider == "openrouter":
                config_updates["openrouter"] = {"enabled": True}
                if data.get("openrouter_api_key"):
                    env_vars["OPENROUTER_API_KEY"] = data["openrouter_api_key"]
                config_updates["openrouter"].update(
                    {
                        "default_model": data.get(
                            "default_model", "anthropic/claude-3.5-sonnet"
                        ),
                        "code_model": data.get(
                            "code_model", "anthropic/claude-3.5-sonnet"
                        ),
                        "fast_model": data.get("fast_model", "openai/gpt-4o-mini"),
                    }
                )

            if data.get("telegram_enabled"):
                config_updates["telegram"] = {"enabled": True}
                if data.get("telegram_token"):
                    env_vars["TELEGRAM_BOT_TOKEN"] = data["telegram_token"]

            if data.get("slack_enabled"):
                config_updates["slack"] = {"enabled": True}
                if data.get("slack_bot_token"):
                    env_vars["SLACK_BOT_TOKEN"] = data["slack_bot_token"]
                if data.get("slack_app_token"):
                    env_vars["SLACK_APP_TOKEN"] = data["slack_app_token"]

            if data.get("tools"):
                config_updates["tools"] = data["tools"]

            if data.get("mcp_servers"):
                config_updates["mcp_servers"] = data["mcp_servers"]

            if env_vars:
                env_content = "# Saladbox environment configuration\n\n"
                if "OPENROUTER_API_KEY" in env_vars:
                    env_content += f"# OpenRouter API\nOPENROUTER_API_KEY={env_vars['OPENROUTER_API_KEY']}\n\n"
                if "TELEGRAM_BOT_TOKEN" in env_vars:
                    env_content += f"# Telegram Bot\nTELEGRAM_BOT_TOKEN={env_vars['TELEGRAM_BOT_TOKEN']}\n\n"
                if "SLACK_BOT_TOKEN" in env_vars:
                    env_content += (
                        f"# Slack Bot\nSLACK_BOT_TOKEN={env_vars['SLACK_BOT_TOKEN']}\n"
                    )
                    if "SLACK_APP_TOKEN" in env_vars:
                        env_content += (
                            f"SLACK_APP_TOKEN={env_vars['SLACK_APP_TOKEN']}\n"
                        )
                    env_content += "\n"

                with open(env_path, "w") as f:
                    f.write(env_content.strip() + "\n")

            if config_path.exists():
                with open(config_path) as f:
                    config_data = yaml.safe_load(f) or {}
            else:
                config_data = {}

            for key, value in config_updates.items():
                if (
                    isinstance(value, dict)
                    and key in config_data
                    and isinstance(config_data[key], dict)
                ):
                    config_data[key].update(value)
                else:
                    config_data[key] = value

            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            return web.json_response(
                {
                    "success": True,
                    "message": "Setup complete. Restart Saladbox to apply all changes.",
                    "restart_required": True,
                }
            )

        except Exception as e:
            logger.exception("Error running setup")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_notifications_poll(self, request: web.Request) -> web.Response:
        """Return and clear any pending notifications (polled by Electron)."""
        notifications = list(self._notification_queue)
        self._notification_queue.clear()
        return web.json_response({"notifications": notifications})

    # ── Speech-to-Text (Whisper) ─────────────────────────────────

    async def handle_transcribe(self, request: web.Request) -> web.Response:
        """Handle POST /api/transcribe — speech-to-text via faster-whisper."""
        if not self._whisper:
            return web.json_response(
                {"error": "Speech-to-text is not enabled. Set whisper.enabled=true in config.yaml"},
                status=503,
            )

        try:
            data = await request.json()
            audio_base64 = data.get("audio", "")

            if not audio_base64:
                return web.json_response(
                    {"error": "audio (base64) is required"}, status=400
                )

            # Run transcription in a thread pool to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(
                None, self._whisper.transcribe_base64_webm, audio_base64
            )

            return web.json_response({"text": text})

        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            logger.exception("Error in transcription")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_whisper_config(self, request: web.Request) -> web.Response:
        """Return whisper configuration."""
        cfg = self._config.whisper
        return web.json_response({
            "enabled": cfg.enabled,
            "model_size": cfg.model_size,
            "device": cfg.device,
            "compute_type": cfg.compute_type,
            "language": cfg.language,
        })

    # ── Image Gen & HuggingFace API endpoints ──────────────────────

    async def handle_image_gen_config(self, request: web.Request) -> web.Response:
        """Return image generation configuration."""
        cfg = self._config.image_gen
        return web.json_response(
            {
                "enabled": cfg.enabled,
                "backend": cfg.backend,
                "model": cfg.model,
                "quantize": cfg.quantize,
                "default_width": cfg.default_width,
                "default_height": cfg.default_height,
                "default_steps": cfg.default_steps,
                "drawthings_url": cfg.drawthings_url,
            }
        )

    async def handle_image_gen_update(self, request: web.Request) -> web.Response:
        """Update image generation configuration."""
        try:
            data = await request.json()
            cfg = self._config.image_gen

            # Update in-memory config
            if "backend" in data:
                cfg.backend = data["backend"]
            if "model" in data:
                cfg.model = data["model"]
            if "quantize" in data:
                cfg.quantize = int(data["quantize"])
            if "default_width" in data:
                cfg.default_width = int(data["default_width"])
            if "default_height" in data:
                cfg.default_height = int(data["default_height"])
            if "default_steps" in data:
                cfg.default_steps = int(data["default_steps"])
            if "drawthings_url" in data:
                cfg.drawthings_url = data["drawthings_url"]
            if "enabled" in data:
                cfg.enabled = bool(data["enabled"])

            # Persist to config.yaml
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    config_data = yaml.safe_load(f) or {}
            else:
                config_data = {}

            config_data["image_gen"] = {
                "enabled": cfg.enabled,
                "backend": cfg.backend,
                "model": cfg.model,
                "quantize": cfg.quantize,
                "default_width": cfg.default_width,
                "default_height": cfg.default_height,
                "default_steps": cfg.default_steps,
                "drawthings_url": cfg.drawthings_url,
            }

            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Image gen config updated: backend={cfg.backend}, model={cfg.model}")
            return web.json_response({"success": True})

        except Exception as e:
            logger.exception("Error updating image gen config")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_hf_token_save(self, request: web.Request) -> web.Response:
        """Save HuggingFace token to .env file."""
        try:
            data = await request.json()
            token = data.get("token", "").strip()

            if not token:
                return web.json_response({"error": "Token is required"}, status=400)

            project_root = Path(__file__).parent.parent.parent
            env_path = project_root / ".env"

            # Read existing .env
            existing = {}
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        existing[k.strip()] = v.strip()

            existing["HF_TOKEN"] = token

            # Rebuild .env preserving all keys
            env_content = "# Saladbox environment configuration\n\n"
            for k, v in existing.items():
                if k == "OPENROUTER_API_KEY":
                    env_content += f"# OpenRouter API\n{k}={v}\n\n"
                elif k == "TELEGRAM_BOT_TOKEN":
                    env_content += f"# Telegram Bot\n{k}={v}\n\n"
                elif k == "SLACK_BOT_TOKEN":
                    env_content += f"# Slack Bot\n{k}={v}\n\n"
                elif k == "SLACK_APP_TOKEN":
                    env_content += f"{k}={v}\n\n"
                elif k == "HF_TOKEN":
                    env_content += f"# HuggingFace\n{k}={v}\n\n"
                else:
                    env_content += f"{k}={v}\n"

            env_path.write_text(env_content.strip() + "\n")

            # Update in-memory config
            self._config.huggingface.token = token
            os.environ["HF_TOKEN"] = token

            # Also login to huggingface_hub if available
            try:
                from huggingface_hub import login
                login(token=token, add_to_git_credential=False)
                logger.info("HuggingFace login successful")
            except ImportError:
                logger.info("huggingface_hub not installed, skipping login")
            except Exception as e:
                logger.warning(f"HuggingFace login failed: {e}")

            return web.json_response({"success": True})

        except Exception as e:
            logger.exception("Error saving HF token")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_hf_status(self, request: web.Request) -> web.Response:
        """Check HuggingFace and image gen backend status."""
        status = {
            "hf_configured": bool(self._config.huggingface.token),
            "mflux_available": False,
            "drawthings_available": False,
        }

        # Check mflux
        try:
            import importlib
            importlib.import_module("mflux")
            status["mflux_available"] = True
        except ImportError:
            pass

        # Check Draw Things
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session, session.get(
                f"{self._config.image_gen.drawthings_url}/sdapi/v1/sd-models",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                status["drawthings_available"] = resp.status == 200
        except Exception:
            pass

        return web.json_response(status)

    # ── Dashboard API endpoints ──────────────────────────────────

    async def handle_dashboard_stats(self, request: web.Request) -> web.Response:
        """Return dashboard statistics."""
        if not self._chat_store:
            return web.json_response({"error": "Chat store not available"}, status=503)
        try:
            stats = self._chat_store.get_stats()
            return web.json_response(stats)
        except Exception as e:
            logger.exception("Error fetching dashboard stats")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_dashboard_conversations(
        self, request: web.Request
    ) -> web.Response:
        """Return list of conversations, optionally filtered by platform."""
        if not self._chat_store:
            return web.json_response({"error": "Chat store not available"}, status=503)
        try:
            platform = request.query.get("platform")
            limit = int(request.query.get("limit", "50"))
            offset = int(request.query.get("offset", "0"))
            conversations = self._chat_store.get_conversations(
                platform=platform, limit=limit, offset=offset
            )
            return web.json_response({"conversations": conversations})
        except Exception as e:
            logger.exception("Error fetching conversations")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_dashboard_messages(self, request: web.Request) -> web.Response:
        """Return messages for a specific conversation."""
        if not self._chat_store:
            return web.json_response({"error": "Chat store not available"}, status=503)
        try:
            conversation_id = request.match_info["conversation_id"]
            limit = int(request.query.get("limit", "200"))
            offset = int(request.query.get("offset", "0"))
            messages = self._chat_store.get_messages(
                conversation_id=conversation_id, limit=limit, offset=offset
            )
            return web.json_response({"messages": messages})
        except Exception as e:
            logger.exception("Error fetching messages")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_dashboard_search(self, request: web.Request) -> web.Response:
        """Search messages across all conversations."""
        if not self._chat_store:
            return web.json_response({"error": "Chat store not available"}, status=503)
        try:
            query = request.query.get("q", "")
            platform = request.query.get("platform")
            limit = int(request.query.get("limit", "50"))
            if not query:
                return web.json_response({"error": "q parameter required"}, status=400)
            results = self._chat_store.search_messages(
                query=query, platform=platform, limit=limit
            )
            return web.json_response({"results": results})
        except Exception as e:
            logger.exception("Error searching messages")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_conversation_delete(self, request: web.Request) -> web.Response:
        """Delete a conversation."""
        if not self._chat_store:
            return web.json_response({"error": "Chat store not available"}, status=503)
        try:
            data = await request.json()
            conversation_id = data.get("conversation_id", "")
            if not conversation_id:
                return web.json_response(
                    {"error": "conversation_id required"}, status=400
                )

            self._chat_store.delete_conversation(conversation_id)
            return web.json_response({"success": True})
        except Exception as e:
            logger.exception("Error deleting conversation")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_screenshot(self, request: web.Request) -> web.Response:
        """Serve a screenshot image from the screenshots directory."""
        filename = request.match_info.get("filename", "")

        # Security: only allow simple filenames (no path traversal)
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            return web.Response(text="Not found", status=404)

        filepath = os.path.join(_SCREENSHOT_DIR, filename)
        if not os.path.isfile(filepath):
            return web.Response(text="Screenshot not found", status=404)

        content_type = mimetypes.guess_type(filepath)[0] or "image/png"
        return web.FileResponse(filepath, headers={"Content-Type": content_type})

    async def handle_generated_image(self, request: web.Request) -> web.Response:
        """Serve a generated image from the generated images directory."""
        filename = request.match_info.get("filename", "")

        # Security: only allow simple filenames (no path traversal)
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            return web.Response(text="Not found", status=404)

        filepath = os.path.join(_GENERATED_IMAGE_DIR, filename)
        if not os.path.isfile(filepath):
            return web.Response(text="Generated image not found", status=404)

        content_type = mimetypes.guess_type(filepath)[0] or "image/png"
        return web.FileResponse(filepath, headers={"Content-Type": content_type})

    async def handle_dashboard_page(self, request: web.Request) -> web.Response:
        """Serve the dashboard HTML page."""
        dashboard_path = (
            Path(__file__).parent.parent.parent / "electron" / "dashboard.html"
        )
        if dashboard_path.exists():
            return web.FileResponse(dashboard_path)
        return web.Response(text="Dashboard not found", status=404)

    async def handle_dashboard_css(self, request: web.Request) -> web.Response:
        """Serve dashboard CSS."""
        css_path = Path(__file__).parent.parent.parent / "electron" / "dashboard.css"
        if css_path.exists():
            return web.FileResponse(css_path, headers={"Content-Type": "text/css"})
        return web.Response(text="Not found", status=404)

    async def handle_dashboard_js(self, request: web.Request) -> web.Response:
        """Serve dashboard JavaScript."""
        js_path = Path(__file__).parent.parent.parent / "electron" / "dashboard.js"
        if js_path.exists():
            return web.FileResponse(
                js_path, headers={"Content-Type": "application/javascript"}
            )
        return web.Response(text="Not found", status=404)

    async def start(self) -> None:
        """Start the HTTP server."""
        self.app = web.Application()
        self.app.router.add_post("/chat", self.handle_chat)
        self.app.router.add_get("/ws", self.handle_websocket)
        self.app.router.add_get("/models", self.handle_models)
        self.app.router.add_post("/models/set", self.handle_set_model)
        self.app.router.add_get("/tools", self.handle_tools)
        self.app.router.add_get("/config", self.handle_config)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/mcp/servers", self.handle_mcp_servers)
        self.app.router.add_post("/mcp/add", self.handle_mcp_add)
        self.app.router.add_post("/mcp/remove", self.handle_mcp_remove)
        self.app.router.add_post("/mcp/toggle", self.handle_mcp_toggle)
        self.app.router.add_get("/setup/status", self.handle_setup_status)
        self.app.router.add_post("/setup/run", self.handle_setup_run)
        self.app.router.add_get("/notifications/poll", self.handle_notifications_poll)
        self.app.router.add_post("/api/transcribe", self.handle_transcribe)
        self.app.router.add_get("/api/whisper/config", self.handle_whisper_config)
        self.app.router.add_get("/image-gen/config", self.handle_image_gen_config)
        self.app.router.add_post("/image-gen/update", self.handle_image_gen_update)
        self.app.router.add_post("/hf/token", self.handle_hf_token_save)
        self.app.router.add_get("/hf/status", self.handle_hf_status)

        # Screenshot serving (for screen_capture tool → frontend display)
        self.app.router.add_get(
            "/screenshots/{filename}", self.handle_screenshot
        )
        # Generated image serving (for image_gen tool → frontend display)
        self.app.router.add_get(
            "/generated/{filename}", self.handle_generated_image
        )

        # Dashboard routes
        self.app.router.add_get("/dashboard", self.handle_dashboard_page)
        self.app.router.add_get("/dashboard.css", self.handle_dashboard_css)
        self.app.router.add_get("/dashboard.js", self.handle_dashboard_js)
        self.app.router.add_get("/api/dashboard/stats", self.handle_dashboard_stats)
        self.app.router.add_get(
            "/api/dashboard/conversations", self.handle_dashboard_conversations
        )
        self.app.router.add_get(
            "/api/dashboard/conversations/{conversation_id}",
            self.handle_dashboard_messages,
        )
        self.app.router.add_get("/api/dashboard/search", self.handle_dashboard_search)
        self.app.router.add_post(
            "/api/conversation/delete", self.handle_conversation_delete
        )

        # CORS headers and Auth token validation for production
        async def auth_and_cors_middleware(app, handler):
            async def middleware_handler(request):
                import os
                # 1. Enforce Token Auth if SALADBOX_API_TOKEN is set
                api_token = os.environ.get("SALADBOX_API_TOKEN")
                if api_token and request.path != "/health" and request.method != "OPTIONS":
                    auth_header = request.headers.get("Authorization", "")
                    query_token = request.query.get("token", "")
                    expected_bearer = f"Bearer {api_token}"
                    if auth_header != expected_bearer and query_token != api_token:
                        return web.json_response({"error": "Unauthorized"}, status=401)

                # 2. CORS Handling
                if request.method == "OPTIONS":
                    response = web.Response()
                else:
                    response = await handler(request)

                origin = request.headers.get("Origin", "")
                is_allowed = False
                if not origin or origin.startswith("file://"):
                    is_allowed = True
                else:
                    from urllib.parse import urlparse
                    try:
                        parsed = urlparse(origin)
                        hostname = parsed.hostname
                        if hostname in ("localhost", "127.0.0.1"):
                            is_allowed = True
                    except Exception:
                        pass

                if is_allowed:
                    response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
                    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

                return response

            return middleware_handler

        self.app.middlewares.append(auth_and_cors_middleware)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

        logger.info(f"HTTP adapter started at http://{self.host}:{self.port}")
        print(f"\n  saladbox HTTP API running at http://{self.host}:{self.port}")
        print(f"  WebSocket: ws://{self.host}:{self.port}/ws")
        print(
            "  Endpoints: POST /chat, GET /ws, GET /models, GET /tools, GET /config\n"
        )

    async def stop(self) -> None:
        """Stop the HTTP server and close all WebSocket connections."""
        # Close all active WebSocket connections
        for ws in list(self.websocket_clients):
            try:
                if not ws.closed:
                    await ws.close()
            except Exception:
                pass
        self.websocket_clients.clear()

        if self.runner:
            await self.runner.cleanup()
            logger.info("HTTP adapter stopped")
