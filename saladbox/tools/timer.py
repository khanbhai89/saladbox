"""Timer and stopwatch tool."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict

from saladbox.tools.base import BaseTool


class TimerTool(BaseTool):
    """Timer, stopwatch, and countdown functionality."""

    def __init__(self):
        self._timers: Dict[str, Dict] = {}
        self._stopwatches: Dict[str, float] = {}

    @property
    def name(self) -> str:
        return "timer"

    @property
    def description(self) -> str:
        return (
            "Manage timers, stopwatches, and countdowns. Start timers that alert after "
            "a duration, track elapsed time with stopwatches, and check status of active timers."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "start",
                        "stop",
                        "status",
                        "list",
                        "stopwatch_start",
                        "stopwatch_stop",
                        "stopwatch_lap",
                    ],
                    "description": "Timer operation to perform",
                },
                "name": {
                    "type": "string",
                    "description": "Timer or stopwatch name (default: 'default')",
                },
                "duration": {
                    "type": "string",
                    "description": "Duration for timer (e.g., '5m', '1h 30m', '90s')",
                },
                "message": {
                    "type": "string",
                    "description": "Message to display when timer completes",
                },
            },
            "required": ["action"],
        }

    def _parse_duration(self, duration_str: str) -> int:
        duration_str = duration_str.lower().strip()
        total_seconds = 0

        patterns = [
            (r"(\d+)\s*h(?:our)?s?", 3600),
            (r"(\d+)\s*m(?:in(?:ute)?)?s?", 60),
            (r"(\d+)\s*s(?:ec(?:ond)?)?s?", 1),
        ]

        for pattern, multiplier in patterns:
            match = re.search(pattern, duration_str)
            if match:
                total_seconds += int(match.group(1)) * multiplier

        return total_seconds if total_seconds > 0 else 0

    def _format_duration(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes, secs = divmod(seconds, 60)
            return f"{minutes}m {secs}s"
        else:
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            return f"{hours}h {minutes}m {secs}s"

    async def execute(
        self,
        action: str,
        name: Optional[str] = None,
        duration: Optional[str] = None,
        message: Optional[str] = None,
    ) -> str:
        import re

        timer_name = name or "default"

        if action == "start":
            if not duration:
                return "Error: 'duration' required to start timer"
            return await self._start_timer(timer_name, duration, message)

        elif action == "stop":
            return self._stop_timer(timer_name)

        elif action == "status":
            return self._timer_status(timer_name)

        elif action == "list":
            return self._list_timers()

        elif action == "stopwatch_start":
            return self._start_stopwatch(timer_name)

        elif action == "stopwatch_stop":
            return self._stop_stopwatch(timer_name)

        elif action == "stopwatch_lap":
            return self._lap_stopwatch(timer_name)

        else:
            return f"Unknown action: {action}"

    async def _start_timer(
        self, name: str, duration: str, message: Optional[str]
    ) -> str:
        seconds = self._parse_duration(duration)
        if seconds <= 0:
            return f"Error: Invalid duration '{duration}'. Use format like '5m', '1h 30m', '90s'"

        if name in self._timers:
            return f"Timer '{name}' already exists. Stop it first."

        end_time = datetime.now() + timedelta(seconds=seconds)

        self._timers[name] = {
            "end_time": end_time,
            "duration": seconds,
            "message": message or f"Timer '{name}' completed!",
            "started_at": datetime.now(),
        }

        return f"Timer '{name}' started for {self._format_duration(seconds)}. Will complete at {end_time.strftime('%H:%M:%S')}"

    def _stop_timer(self, name: str) -> str:
        if name not in self._timers:
            return f"Timer '{name}' not found"

        timer = self._timers.pop(name)
        elapsed = (datetime.now() - timer["started_at"]).total_seconds()
        remaining = timer["duration"] - elapsed

        return f"Timer '{name}' stopped. {self._format_duration(int(max(0, remaining)))} remaining"

    def _timer_status(self, name: str) -> str:
        if name not in self._timers:
            return f"Timer '{name}' not found"

        timer = self._timers[name]
        remaining = (timer["end_time"] - datetime.now()).total_seconds()

        if remaining <= 0:
            self._timers.pop(name)
            return f"Timer '{name}' has completed! {timer['message']}"

        return f"Timer '{name}': {self._format_duration(int(remaining))} remaining"

    def _list_timers(self) -> str:
        if not self._timers:
            return "No active timers"

        result = [f"**Active Timers ({len(self._timers)}):**\n"]

        for name, timer in sorted(self._timers.items()):
            remaining = (timer["end_time"] - datetime.now()).total_seconds()
            if remaining <= 0:
                status = "COMPLETED"
            else:
                status = self._format_duration(int(remaining))
            result.append(f"- {name}: {status}")

        return "\n".join(result)

    def _start_stopwatch(self, name: str) -> str:
        if name in self._stopwatches:
            return f"Stopwatch '{name}' is already running"

        self._stopwatches[name] = time.time()
        return f"Stopwatch '{name}' started at {datetime.now().strftime('%H:%M:%S')}"

    def _stop_stopwatch(self, name: str) -> str:
        if name not in self._stopwatches:
            return f"Stopwatch '{name}' not found"

        elapsed = time.time() - self._stopwatches.pop(name)
        return f"Stopwatch '{name}' stopped. Elapsed: {self._format_duration(int(elapsed))}"

    def _lap_stopwatch(self, name: str) -> str:
        if name not in self._stopwatches:
            return f"Stopwatch '{name}' not found"

        elapsed = time.time() - self._stopwatches[name]
        return f"Stopwatch '{name}' lap: {self._format_duration(int(elapsed))}"
