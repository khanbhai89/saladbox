"""Background process management tool."""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass, field
from datetime import datetime

from saladbox.tools.base import BaseTool


@dataclass
class ManagedProcess:
    name: str
    command: str
    process: asyncio.subprocess.Process
    started_at: datetime = field(default_factory=datetime.now)
    output_lines: list[str] = field(default_factory=list)


class ProcessManagerTool(BaseTool):
    """Start, stop, and monitor background processes."""

    def __init__(self):
        self._processes: dict[str, ManagedProcess] = {}

    @property
    def name(self) -> str:
        return "process_manager"

    @property
    def description(self) -> str:
        return (
            "Manage background processes: start long-running commands, "
            "stop them, list active processes, and get their output."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "stop", "list", "output", "status"],
                    "description": "Process management action",
                },
                "name": {
                    "type": "string",
                    "description": "Unique name for the process",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to run (for 'start' action)",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of output lines to return (default: 20)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        name: str = "",
        command: str = "",
        lines: int | str = 20,
    ) -> str:
        # Normalize types (registry normalizes too; this handles direct calls)
        if isinstance(command, (list, tuple)):
            command = " ".join(str(c) for c in command)
        try:
            lines = int(lines) if lines is not None else 20
        except (TypeError, ValueError):
            lines = 20
        lines = max(1, min(lines, 1000))
        match action:
            case "start":
                return await self._start(name, command)
            case "stop":
                return await self._stop(name)
            case "list":
                return self._list()
            case "output":
                return self._output(name, lines)
            case "status":
                return self._status(name)
            case _:
                return f"Unknown action: {action}"

    async def _start(self, name: str, command: str) -> str:
        if not name or not command:
            return "name and command are required"
        if name in self._processes:
            mp = self._processes[name]
            if mp.process.returncode is None:
                return f"Process '{name}' is already running (PID {mp.process.pid})"

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        managed = ManagedProcess(name=name, command=command, process=proc)
        self._processes[name] = managed

        # Start background reader
        asyncio.create_task(self._read_output(managed))

        return f"Started '{name}' (PID {proc.pid}): {command}"

    async def _read_output(self, managed: ManagedProcess):
        """Read process output in the background."""
        try:
            async for line in managed.process.stdout:
                text = line.decode(errors="replace").rstrip()
                managed.output_lines.append(text)
                # Keep only the last 500 lines
                if len(managed.output_lines) > 500:
                    managed.output_lines = managed.output_lines[-500:]
        except Exception:
            pass

    async def _stop(self, name: str) -> str:
        if not name:
            return "name is required"
        if name not in self._processes:
            return f"No process named '{name}'"

        mp = self._processes[name]
        if mp.process.returncode is not None:
            return f"Process '{name}' already exited with code {mp.process.returncode}"

        mp.process.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(mp.process.wait(), timeout=5)
        except TimeoutError:
            mp.process.kill()
            await mp.process.wait()

        return f"Stopped '{name}' (exit code: {mp.process.returncode})"

    def _list(self) -> str:
        if not self._processes:
            return "No managed processes"
        lines = ["Managed processes:"]
        for name, mp in self._processes.items():
            status = "running" if mp.process.returncode is None else f"exited ({mp.process.returncode})"
            lines.append(
                f"  {name}: PID {mp.process.pid} | {status} | "
                f"started {mp.started_at.strftime('%H:%M:%S')} | {mp.command}"
            )
        return "\n".join(lines)

    def _output(self, name: str, lines: int) -> str:
        if not name:
            return "name is required"
        if name not in self._processes:
            return f"No process named '{name}'"

        mp = self._processes[name]
        recent = mp.output_lines[-lines:]
        if not recent:
            return f"No output from '{name}' yet"
        return f"Output from '{name}' (last {len(recent)} lines):\n" + "\n".join(recent)

    def _status(self, name: str) -> str:
        if not name:
            return "name is required"
        if name not in self._processes:
            return f"No process named '{name}'"

        mp = self._processes[name]
        running = mp.process.returncode is None
        return (
            f"Process: {name}\n"
            f"PID: {mp.process.pid}\n"
            f"Command: {mp.command}\n"
            f"Status: {'running' if running else f'exited ({mp.process.returncode})'}\n"
            f"Started: {mp.started_at.isoformat()}\n"
            f"Output lines: {len(mp.output_lines)}"
        )
