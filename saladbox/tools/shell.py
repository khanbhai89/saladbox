"""Shell command execution tool."""

from __future__ import annotations

import asyncio
import os
from typing import Union

from saladbox.tools.base import BaseTool


class ShellTool(BaseTool):
    """Execute shell commands with timeout support."""

    @property
    def name(self) -> str:
        return "run_shell"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command and return its output. "
            "Use for system tasks, git, package management, running scripts, etc."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the command (default: current dir)",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: Union[str, list[str]],
        timeout: int = 30,
        working_dir: str = ".",
    ) -> str:
        # LLM sometimes sends command as a list/array (e.g. ["ls", "-l"]); subprocess needs a string
        if isinstance(command, (list, tuple)):
            command = " ".join(str(c) for c in command)
        elif not isinstance(command, str):
            command = str(command)

        # Resolve working_dir; avoid FileNotFoundError when the model assumes a path that doesn't exist (e.g. /home/saladbox)
        working_dir = (working_dir or ".").strip() or "."
        if working_dir != ".":
            working_dir = os.path.expanduser(working_dir)
            if not os.path.isdir(working_dir):
                return (
                    f"Error: Working directory '{working_dir}' does not exist. "
                    "Use '.' for the current directory or a path that exists on this machine."
                )

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"Command timed out after {timeout}s"

        output = stdout.decode(errors="replace") if stdout else ""
        errors = stderr.decode(errors="replace") if stderr else ""

        # Truncate long output
        max_len = 4000
        if len(output) > max_len:
            output = output[:max_len] + "\n... (truncated)"
        if len(errors) > max_len:
            errors = errors[:max_len] + "\n... (truncated)"

        parts = [f"Exit code: {proc.returncode}"]
        if output.strip():
            parts.append(f"Stdout:\n{output}")
        if errors.strip():
            parts.append(f"Stderr:\n{errors}")

        return "\n".join(parts)
