"""MCP (Model Context Protocol) client: connects to MCP servers over stdio.

Discovers tools from external MCP servers and wraps them as BaseTool instances
so they integrate seamlessly with the existing ToolRegistry and agent engine.

Protocol: JSON-RPC 2.0 over stdin/stdout (newline-delimited).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from saladbox.tools.base import BaseTool

logger = logging.getLogger(__name__)

# MCP protocol version
PROTOCOL_VERSION = "2024-11-05"


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    command: str  # e.g. "npx", "uvx", "node", "python3"
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _make_request(method: str, params: dict | None = None, req_id: int | None = None) -> dict:
    """Build a JSON-RPC 2.0 request."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if req_id is not None:
        msg["id"] = req_id
    return msg


def _make_notification(method: str, params: dict | None = None) -> dict:
    """Build a JSON-RPC 2.0 notification (no id → no response expected)."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


# ---------------------------------------------------------------------------
# MCPTool: wraps a single MCP-discovered tool as a BaseTool
# ---------------------------------------------------------------------------

class MCPTool(BaseTool):
    """Wraps an MCP server tool so it looks like a native saladbox tool."""

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_parameters: dict,
        server: MCPServerConnection,
        server_prefix: str = "",
    ):
        self._name = f"{server_prefix}{tool_name}" if server_prefix else tool_name
        self._raw_name = tool_name  # original name for MCP call
        self._description = tool_description
        self._parameters = tool_parameters
        self._server = server

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, **kwargs) -> str:
        """Forward the call to the MCP server via tools/call."""
        return await self._server.call_tool(self._raw_name, kwargs)


# ---------------------------------------------------------------------------
# MCPServerConnection: manages a single MCP server subprocess
# ---------------------------------------------------------------------------

class MCPServerConnection:
    """Manages the lifecycle of a single MCP server subprocess."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._tools: list[dict] = []  # raw MCP tool definitions
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    # ---- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        """Start the MCP server subprocess and complete the handshake."""
        # Merge env
        env = {**os.environ}
        for key, val in self.config.env.items():
            # Support ${VAR} references to existing env vars
            if val.startswith("${") and val.endswith("}"):
                env_key = val[2:-1]
                env[key] = os.environ.get(env_key, "")
            else:
                env[key] = val

        cmd = [self.config.command] + self.config.args
        logger.info(f"[MCP:{self.config.name}] Starting: {' '.join(cmd)}")

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            logger.error(
                f"[MCP:{self.config.name}] Command not found: {self.config.command}. "
                f"Make sure it is installed."
            )
            return
        except Exception as e:
            logger.error(f"[MCP:{self.config.name}] Failed to start: {e}")
            return

        # Start reading stdout in background
        self._reader_task = asyncio.create_task(self._read_loop())

        # Initialize handshake
        try:
            await self._initialize()
            self._ready = True
            logger.info(f"[MCP:{self.config.name}] Connected and ready")
        except Exception as e:
            logger.error(f"[MCP:{self.config.name}] Handshake failed: {e}")
            await self.stop()

    async def stop(self) -> None:
        """Shut down the MCP server."""
        self._ready = False
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
            self._process = None

        # Cancel pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        logger.info(f"[MCP:{self.config.name}] Stopped")

    # ---- I/O --------------------------------------------------------------

    async def _send(self, message: dict) -> None:
        """Send a JSON-RPC message to the server's stdin."""
        if not self._process or not self._process.stdin:
            raise RuntimeError(f"MCP server {self.config.name} is not running")

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Continuously read JSON-RPC messages from the server's stdout."""
        if not self._process or not self._process.stdout:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break  # EOF - server exited

                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.debug(f"[MCP:{self.config.name}] Non-JSON: {line_str[:200]}")
                    continue

                # Handle response (has "id")
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(
                                RuntimeError(
                                    f"MCP error: {msg['error'].get('message', msg['error'])}"
                                )
                            )
                        else:
                            fut.set_result(msg.get("result"))

                # Handle notifications (no "id")
                elif "method" in msg and "id" not in msg:
                    logger.debug(
                        f"[MCP:{self.config.name}] Notification: {msg['method']}"
                    )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[MCP:{self.config.name}] Reader error: {e}")

        # Server exited or reader failed — mark not ready and fail pending requests
        self._ready = False
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(
                    RuntimeError(f"MCP server {self.config.name} disconnected")
                )
        self._pending.clear()
        logger.warning(f"[MCP:{self.config.name}] Reader loop exited, server marked not ready")

    async def _request(self, method: str, params: dict | None = None, timeout: float = 30) -> Any:
        """Send a request and wait for its response."""
        req_id = self._next_id()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut

        msg = _make_request(method, params, req_id)
        await self._send(msg)

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError(
                f"[MCP:{self.config.name}] Timeout waiting for {method}"
            )

    async def _notify(self, method: str, params: dict | None = None) -> None:
        """Send a notification (no response expected)."""
        msg = _make_notification(method, params)
        await self._send(msg)

    # ---- MCP protocol methods --------------------------------------------

    async def _initialize(self) -> dict:
        """Perform the MCP initialize handshake."""
        result = await self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "roots": {"listChanged": True},
            },
            "clientInfo": {
                "name": "saladbox",
                "version": "0.3.0",
            },
        })

        # Send initialized notification
        await self._notify("notifications/initialized")
        return result

    async def list_tools(self) -> list[dict]:
        """Discover tools from the MCP server."""
        result = await self._request("tools/list", {})
        self._tools = result.get("tools", []) if result else []
        logger.info(
            f"[MCP:{self.config.name}] Discovered {len(self._tools)} tools: "
            f"{[t['name'] for t in self._tools]}"
        )
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool on the MCP server and return the result as text."""
        if not self._ready:
            return f"MCP server '{self.config.name}' is not connected."
        try:
            result = await self._request("tools/call", {
                "name": tool_name,
                "arguments": arguments,
            }, timeout=120)
        except Exception as e:
            return f"MCP tool error: {e}"

        if not result:
            return "No result from MCP server."

        # MCP returns content as a list of content blocks
        content_list = result.get("content", [])
        if not content_list:
            return json.dumps(result) if isinstance(result, dict) else str(result)

        parts = []
        for block in content_list:
            if isinstance(block, dict):
                block_type = block.get("type", "text")
                if block_type == "text":
                    parts.append(block.get("text", ""))
                elif block_type == "image":
                    parts.append(f"[Image: {block.get('mimeType', 'image')}]")
                elif block_type == "resource":
                    res = block.get("resource", {})
                    parts.append(res.get("text", str(res)))
                else:
                    parts.append(str(block))
            else:
                parts.append(str(block))

        is_error = result.get("isError", False)
        text = "\n".join(parts)
        if is_error:
            text = f"[MCP Error] {text}"
        return text

    def get_tool_definitions(self) -> list[dict]:
        """Return cached tool definitions."""
        return self._tools


# ---------------------------------------------------------------------------
# MCPManager: manages all MCP server connections
# ---------------------------------------------------------------------------

class MCPManager:
    """Manages multiple MCP server connections and their tools."""

    def __init__(self):
        self._servers: dict[str, MCPServerConnection] = {}
        self._tools: list[MCPTool] = []

    @property
    def tools(self) -> list[MCPTool]:
        return self._tools

    async def start_servers(self, configs: list[MCPServerConfig]) -> None:
        """Start all configured MCP servers and discover their tools."""
        if not configs:
            return

        # Start servers concurrently
        tasks = []
        for cfg in configs:
            if not cfg.enabled:
                logger.info(f"[MCP] Skipping disabled server: {cfg.name}")
                continue
            conn = MCPServerConnection(cfg)
            self._servers[cfg.name] = conn
            tasks.append(self._start_and_discover(conn))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(
            f"[MCP] Total MCP tools discovered: {len(self._tools)} "
            f"from {len([s for s in self._servers.values() if s.is_ready])} servers"
        )

    async def _start_and_discover(self, conn: MCPServerConnection) -> None:
        """Start a server, discover its tools, create MCPTool wrappers."""
        try:
            await conn.start()
            if not conn.is_ready:
                return

            raw_tools = await conn.list_tools()

            # Collect existing native tool names to detect conflicts
            existing_names = {t.name for t in self._tools}

            for tool_def in raw_tools:
                name = tool_def.get("name", "")
                desc = tool_def.get("description", f"MCP tool from {conn.config.name}")
                schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})

                # Use server prefix if name conflicts
                prefix = f"{conn.config.name}_" if name in existing_names else ""

                mcp_tool = MCPTool(
                    tool_name=name,
                    tool_description=f"[{conn.config.name}] {desc}",
                    tool_parameters=schema,
                    server=conn,
                    server_prefix=prefix,
                )
                self._tools.append(mcp_tool)

        except Exception as e:
            logger.error(f"[MCP:{conn.config.name}] Start/discover failed: {e}")

    async def stop_all(self) -> None:
        """Shut down all MCP servers."""
        tasks = [conn.stop() for conn in self._servers.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._servers.clear()
        self._tools.clear()
        logger.info("[MCP] All servers stopped")

    def get_server(self, name: str) -> MCPServerConnection | None:
        """Get a specific server connection by name."""
        return self._servers.get(name)

    @property
    def server_names(self) -> list[str]:
        return [
            name for name, conn in self._servers.items()
            if conn.is_ready
        ]
