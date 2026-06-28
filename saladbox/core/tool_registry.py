"""Tool registry: manages tool registration, schema generation, and execution.

Updated for modern LLM standards:
- Strict schema mode (additionalProperties: false) for OpenAI-compatible APIs
- Timing metrics on tool execution
- Better error messages for debugging
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from saladbox.core.types import ToolResult
from saladbox.tools.base import BaseTool

# MCP tools are dynamically discovered — we import the class for isinstance checks
try:
    from saladbox.core.mcp_client import MCPTool
except ImportError:
    MCPTool = None  # type: ignore

logger = logging.getLogger(__name__)


def _coerce_int(
    value: Any, default: int, min_val: int | None = None, max_val: int | None = None
) -> int:
    """Coerce value to int; clamp to [min_val, max_val] if given."""
    try:
        n = int(value) if value is not None else default
    except (TypeError, ValueError):
        n = default
    if min_val is not None and n < min_val:
        n = min_val
    if max_val is not None and n > max_val:
        n = max_val
    return n


def _command_to_str(command: Any) -> str:
    """Normalize command to a single string (LLM often sends list)."""
    if isinstance(command, (list, tuple)):
        return " ".join(str(c) for c in command)
    return str(command) if command is not None else ""


def _normalize_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Normalize and filter arguments so the LLM can send flexible input.

    Each tool receives only the kwargs it expects, with types coerced.
    """
    args = dict(arguments)

    if tool_name == "run_shell":
        args["command"] = _command_to_str(args.get("command"))
        args["working_dir"] = (args.get("working_dir") or ".").strip() or "."
        if args["working_dir"] != ".":
            expanded = os.path.expanduser(args["working_dir"])
            if not os.path.isdir(expanded):
                args["working_dir"] = "."
        args["timeout"] = _coerce_int(args.get("timeout"), 30, 1, 600)
        return {
            "command": args["command"],
            "timeout": args["timeout"],
            "working_dir": args["working_dir"],
        }

    if tool_name == "run_python":
        args["timeout"] = _coerce_int(args.get("timeout"), 15, 1, 300)
        return {"code": args.get("code", ""), "timeout": args["timeout"]}

    if tool_name == "browser":
        if (
            args.get("action") == "navigate"
            and not args.get("value")
            and args.get("url")
        ):
            args["value"] = args.get("url", "")
        if (
            args.get("action") == "fill_form"
            and not args.get("value")
            and args.get("form_data")
        ):
            import json as _json

            form_data = args.get("form_data")
            if isinstance(form_data, dict):
                args["value"] = _json.dumps(form_data)
            else:
                args["value"] = str(form_data)
        args["timeout"] = _coerce_int(args.get("timeout"), 30000, 5000, 120000)
        return {
            "action": args.get("action", ""),
            "selector": args.get("selector", ""),
            "value": args.get("value", ""),
            "timeout": args["timeout"],
        }

    if tool_name == "filesystem":
        if not args.get("path") and args.get("pattern"):
            args["path"] = args.get("pattern", "")
        return {
            "action": args.get("action", ""),
            "path": args.get("path", ""),
            "content": args.get("content", ""),
            "pattern": args.get("pattern", ""),
        }

    if tool_name == "system_monitor":
        args["top_n"] = _coerce_int(args.get("top_n"), 10, 1, 100)
        return {"action": args.get("action", ""), "top_n": args["top_n"]}

    if tool_name == "scheduler":
        args["seconds"] = _coerce_int(args.get("seconds"), 0, 0, 86400)
        return {
            "action": args.get("action", ""),
            "job_id": args.get("job_id", ""),
            "command": args.get("command", ""),
            "seconds": args["seconds"],
            "cron_expression": args.get("cron_expression", ""),
            "run_at": args.get("run_at", ""),
        }

    if tool_name == "process_manager":
        args["command"] = _command_to_str(args.get("command"))
        args["lines"] = _coerce_int(args.get("lines"), 20, 1, 1000)
        return {
            "action": args.get("action", ""),
            "name": args.get("name", ""),
            "command": args.get("command", ""),
            "lines": args["lines"],
        }

    if tool_name == "code_editor":
        args["start_line"] = _coerce_int(args.get("start_line"), 1, 1, 1_000_000)
        args["end_line"] = _coerce_int(args.get("end_line"), 0, 0, 1_000_000)
        args["depth"] = _coerce_int(args.get("depth"), 3, 1, 6)
        return {
            "action": args.get("action", ""),
            "path": args.get("path", ""),
            "scan_path": args.get("scan_path", ""),
            "start_line": args["start_line"],
            "end_line": args["end_line"],
            "edit_type": args.get("edit_type", ""),
            "content": args.get("content", ""),
            "find": args.get("find", ""),
            "replace": args.get("replace", ""),
            "pattern": args.get("pattern", ""),
            "file_glob": args.get("file_glob", ""),
            "depth": args["depth"],
            "command": args.get("command", ""),
            "run_type": args.get("run_type", "dev"),
        }

    if tool_name == "git":
        args["lines"] = _coerce_int(args.get("lines"), 10, 1, 100)
        return {
            "action": args.get("action", ""),
            "path": args.get("path", "."),
            "files": args.get("files", ""),
            "message": args.get("message", ""),
            "branch_name": args.get("branch_name", ""),
            "remote": args.get("remote", "origin"),
            "url": args.get("url", ""),
            "base_branch": args.get("base_branch", "main"),
            "body": args.get("body", ""),
            "lines": args["lines"],
        }

    if tool_name == "reminder":
        args["minutes"] = _coerce_int(args.get("minutes"), 5, 1, 1440)
        return {
            "action": args.get("action", ""),
            "reminder_id": args.get("reminder_id", ""),
            "message": args.get("message", ""),
            "remind_at": args.get("remind_at", ""),
            "repeat": args.get("repeat", ""),
            "category": args.get("category", ""),
            "priority": args.get("priority", "normal"),
            "minutes": args["minutes"],
        }

    if tool_name == "web_search":
        args["num_results"] = _coerce_int(args.get("num_results"), 5, 1, 10)
        return {
            "query": args.get("query", ""),
            "search_type": args.get("search_type", "web"),
            "num_results": args["num_results"],
        }

    if tool_name == "calculator":
        args["precision"] = _coerce_int(args.get("precision"), 6, 0, 15)
        return {
            "expression": args.get("expression", ""),
            "precision": args["precision"],
        }

    if tool_name == "datetime_tool":
        args["days"] = _coerce_int(args.get("days"), 0, -365, 365)
        args["hours"] = _coerce_int(args.get("hours"), 0, -24, 24)
        args["minutes"] = _coerce_int(args.get("minutes"), 0, -1440, 1440)
        return {
            "action": args.get("action", ""),
            "timezone": args.get("timezone"),
            "datetime_str": args.get("datetime_str"),
            "from_tz": args.get("from_tz"),
            "to_tz": args.get("to_tz"),
            "days": args["days"],
            "hours": args["hours"],
            "minutes": args["minutes"],
            "format_str": args.get("format_str"),
            "target_datetime": args.get("target_datetime"),
        }

    if tool_name == "clipboard":
        return {
            "action": args.get("action", ""),
            "text": args.get("text"),
        }

    if tool_name == "notes":
        args["limit"] = _coerce_int(args.get("limit"), 10, 1, 100)
        return {
            "action": args.get("action", ""),
            "title": args.get("title"),
            "content": args.get("content"),
            "tags": args.get("tags"),
            "query": args.get("query"),
            "limit": args["limit"],
        }

    if tool_name == "weather":
        return {
            "location": args.get("location", ""),
            "units": args.get("units", "metric"),
            "forecast": args.get("forecast", "current"),
            "format": args.get("format", "text"),
        }

    if tool_name == "http_client":
        args["timeout"] = _coerce_int(args.get("timeout"), 30, 1, 120)
        return {
            "method": args.get("method", "GET"),
            "url": args.get("url", ""),
            "headers": args.get("headers"),
            "body": args.get("body"),
            "params": args.get("params"),
            "timeout": args["timeout"],
        }

    if tool_name == "json_yaml":
        args["indent"] = _coerce_int(args.get("indent"), 2, 0, 8)
        return {
            "action": args.get("action", ""),
            "data": args.get("data", ""),
            "path": args.get("path"),
            "format": args.get("format", "json"),
            "indent": args["indent"],
        }

    if tool_name == "encoding":
        args["length"] = _coerce_int(args.get("length"), 16, 1, 128)
        return {
            "action": args.get("action", ""),
            "data": args.get("data"),
            "algorithm": args.get("algorithm", "sha256"),
            "length": args["length"],
        }

    if tool_name == "text":
        return {
            "action": args.get("action", ""),
            "text": args.get("text", ""),
            "pattern": args.get("pattern"),
            "replacement": args.get("replacement"),
            "delimiter": args.get("delimiter"),
        }

    if tool_name == "password":
        args["length"] = _coerce_int(args.get("length"), 16, 4, 128)
        args["word_count"] = _coerce_int(args.get("word_count"), 4, 3, 10)
        args["count"] = _coerce_int(args.get("count"), 1, 1, 10)
        return {
            "action": args.get("action", ""),
            "length": args["length"],
            "include_uppercase": args.get("include_uppercase", True),
            "include_lowercase": args.get("include_lowercase", True),
            "include_numbers": args.get("include_numbers", True),
            "include_symbols": args.get("include_symbols", True),
            "word_count": args["word_count"],
            "separator": args.get("separator", "-"),
            "count": args["count"],
        }

    if tool_name == "finance":
        return {
            "action": args.get("action", ""),
            "symbol": args.get("symbol"),
            "currency": args.get("currency", "usd"),
            "from_currency": args.get("from_currency"),
            "to_currency": args.get("to_currency"),
        }

    if tool_name == "timer":
        return {
            "action": args.get("action", ""),
            "name": args.get("name"),
            "duration": args.get("duration"),
            "message": args.get("message"),
        }

    if tool_name == "qrcode":
        args["size"] = _coerce_int(args.get("size"), 200, 100, 500)
        return {
            "action": args.get("action", ""),
            "data": args.get("data"),
            "ssid": args.get("ssid"),
            "password": args.get("password"),
            "security": args.get("security", "WPA"),
            "name": args.get("name"),
            "phone": args.get("phone"),
            "email": args.get("email"),
            "size": args["size"],
        }

    if tool_name == "translate":
        return {
            "action": args.get("action", ""),
            "text": args.get("text"),
            "source_lang": args.get("source_lang"),
            "target_lang": args.get("target_lang"),
        }

    if tool_name == "color":
        args["count"] = _coerce_int(args.get("count"), 5, 2, 12)
        return {
            "action": args.get("action", ""),
            "color": args.get("color"),
            "format": args.get("format", "all"),
            "count": args["count"],
        }

    if tool_name == "unit_converter":
        return {
            "action": args.get("action", ""),
            "category": args.get("category"),
            "value": args.get("value"),
            "from_unit": args.get("from_unit"),
            "to_unit": args.get("to_unit"),
        }

    if tool_name == "url":
        return {
            "action": args.get("action", ""),
            "url": args.get("url"),
            "scheme": args.get("scheme"),
            "host": args.get("host"),
            "port": args.get("port"),
            "path": args.get("path"),
            "query": args.get("query"),
            "fragment": args.get("fragment"),
            "base_url": args.get("base_url"),
            "relative_url": args.get("relative_url"),
        }

    if tool_name == "location":
        return {
            "action": args.get("action", ""),
            "address": args.get("address"),
            "lat": args.get("lat"),
            "lon": args.get("lon"),
            "query": args.get("query"),
            "dest_lat": args.get("dest_lat"),
            "dest_lon": args.get("dest_lon"),
            "provider": args.get("provider", "google"),
        }

    if tool_name == "docker":
        args["lines"] = _coerce_int(args.get("lines"), 50, 10, 500)
        return {
            "action": args.get("action", ""),
            "container": args.get("container"),
            "image": args.get("image"),
            "command": args.get("command"),
            "options": args.get("options"),
            "lines": args["lines"],
        }

    if tool_name == "open_url":
        return {
            "url": args.get("url", ""),
            "site": args.get("site", ""),
            "query": args.get("query", ""),
        }

    if tool_name == "screen_capture":
        return {
            "action": args.get("action", "capture"),
            "region": args.get("region", ""),
        }

    if tool_name == "image_gen":
        args["width"] = _coerce_int(args.get("width"), 1024, 256, 2048)
        args["height"] = _coerce_int(args.get("height"), 1024, 256, 2048)
        args["steps"] = _coerce_int(args.get("steps"), 2, 1, 50)
        seed = args.get("seed")
        if seed is not None:
            seed = _coerce_int(seed, None, 0, 2**32 - 1)
        return {
            "prompt": args.get("prompt", ""),
            "width": args["width"],
            "height": args["height"],
            "steps": args["steps"],
            "seed": seed,
            "backend": args.get("backend", "mflux"),
        }

    return args


class ToolRegistry:
    """Central registry for all available tools.

    Features:
    - Strict schema mode for OpenAI-compatible structured outputs
    - Execution timing metrics
    - MCP tool detection
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_schemas(
        self, compact: bool = False, strict: bool = False
    ) -> list[dict]:
        """Return tool schemas for all registered tools.

        Args:
            compact: Use shorter descriptions (for local models).
            strict: Add additionalProperties: false (for OpenAI strict mode).
        """
        return [
            tool.to_schema(compact=compact, strict=strict)
            for tool in self._tools.values()
        ]

    def is_mcp_tool(self, name: str) -> bool:
        """Check if a tool is an MCP tool (discovered from external server)."""
        tool = self._tools.get(name)
        if tool is None or MCPTool is None:
            return False
        return isinstance(tool, MCPTool)

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with the given arguments.

        Returns ToolResult with timing information.
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                tool_call_id="",
                name=name,
                content=f"Unknown tool: '{name}'. Available tools: {', '.join(self.tool_names[:10])}",
                is_error=True,
            )

        start_time = time.monotonic()
        try:
            # MCP tools: pass arguments through directly
            if MCPTool is not None and isinstance(tool, MCPTool):
                result = await tool.execute(**arguments)
            else:
                normalized = _normalize_arguments(name, arguments)
                result = await tool.execute(**normalized)

            elapsed_ms = (time.monotonic() - start_time) * 1000
            return ToolResult(
                tool_call_id="",
                name=name,
                content=str(result),
                duration_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.exception(f"Tool '{name}' failed after {elapsed_ms:.0f}ms")
            return ToolResult(
                tool_call_id="",
                name=name,
                content=f"Error executing {name}: {type(e).__name__}: {e}",
                is_error=True,
                duration_ms=elapsed_ms,
            )

    def register_tools(self, tools: list[BaseTool]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)
