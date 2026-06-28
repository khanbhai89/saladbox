"""Clipboard operations tool."""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

from saladbox.tools.base import BaseTool


class ClipboardTool(BaseTool):
    """Read from and write to system clipboard."""

    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def description(self) -> str:
        return (
            "Read from or write to the system clipboard. Use this to copy text for the user "
            "or retrieve text the user has copied. Supports read, write, and clear operations."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "clear"],
                    "description": "Clipboard operation to perform",
                },
                "text": {
                    "type": "string",
                    "description": "Text to write to clipboard (required for 'write' action)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, text: Optional[str] = None) -> str:
        if action == "read":
            return await self._read()
        elif action == "write":
            if text is None:
                return "Error: 'text' parameter required for write action"
            return await self._write(text)
        elif action == "clear":
            return await self._clear()
        else:
            return f"Unknown action: {action}"

    async def _read(self) -> str:
        try:
            if sys.platform == "darwin":
                result = subprocess.run(
                    ["pbpaste"], capture_output=True, text=True, timeout=5
                )
            elif sys.platform == "win32":
                result = subprocess.run(
                    ["powershell", "-command", "Get-Clipboard"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            else:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

            if result.returncode != 0:
                return f"Error reading clipboard: {result.stderr}"

            content = result.stdout
            if not content.strip():
                return "Clipboard is empty"

            max_len = 2000
            if len(content) > max_len:
                return f"Clipboard content (truncated):\n{content[:max_len]}..."

            return f"Clipboard content:\n{content}"

        except FileNotFoundError:
            if sys.platform == "linux":
                return (
                    "Error: xclip not installed. Install with: sudo apt install xclip"
                )
            return "Error: Clipboard command not found"
        except subprocess.TimeoutExpired:
            return "Error: Clipboard operation timed out"
        except Exception as e:
            return f"Error reading clipboard: {str(e)}"

    async def _write(self, text: str) -> str:
        try:
            if sys.platform == "darwin":
                process = subprocess.Popen(
                    ["pbcopy"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                process.communicate(input=text.encode("utf-8"), timeout=5)
            elif sys.platform == "win32":
                escaped = text.replace("'", "''")
                subprocess.run(
                    ["powershell", "-command", f"Set-Clipboard -Value '{escaped}'"],
                    capture_output=True,
                    timeout=5,
                )
            else:
                process = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                process.communicate(input=text.encode("utf-8"), timeout=5)

            return f"Copied {len(text)} characters to clipboard"

        except FileNotFoundError:
            if sys.platform == "linux":
                return (
                    "Error: xclip not installed. Install with: sudo apt install xclip"
                )
            return "Error: Clipboard command not found"
        except subprocess.TimeoutExpired:
            return "Error: Clipboard operation timed out"
        except Exception as e:
            return f"Error writing to clipboard: {str(e)}"

    async def _clear(self) -> str:
        return await self._write("")
