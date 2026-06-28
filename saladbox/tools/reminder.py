"""Reminder tool with smart scheduling, recurring support, and Electron notifications.

Optimized for local models:
- Uses platform NLP for natural language time parsing
- Compact output format
- Supports recurring reminders (daily, weekly, custom interval)
- Categories and priorities for organization
- Notification dispatch via callback (works with Electron, CLI, Slack, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from saladbox.platform.output import ToolOutput
from saladbox.platform.parsing import parse_duration_seconds, parse_natural_time
from saladbox.tools.base import BaseTool

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class ReminderTool(BaseTool):
    """Manage reminders with natural language scheduling and recurring support."""

    max_output_chars = 1200

    # Notification callback: set by the app to push to Electron/CLI/Slack
    _notify_callback: Callable[[str, dict], Awaitable[None]] | None = None

    def __init__(self):
        self._reminders: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._storage_path = Path.home() / ".saladbox" / "reminders.json"
        self._load_reminders()
        self._checker_task: asyncio.Task | None = None

    @classmethod
    def set_notify_callback(cls, callback: Callable[[str, dict], Awaitable[None]]):
        """Set a callback for delivering notifications.

        callback(message: str, metadata: dict) -> None
        metadata includes: reminder_id, category, priority, recurring
        """
        cls._notify_callback = callback

    def _load_reminders(self):
        try:
            if self._storage_path.exists():
                data = json.loads(self._storage_path.read_text())
                now = datetime.now()
                self._reminders = {}
                for k, v in data.items():
                    remind_at = datetime.fromisoformat(v["remind_at"])
                    # Keep future reminders and recurring ones
                    if remind_at > now or v.get("recurring"):
                        self._reminders[k] = v
        except Exception as e:
            logger.warning(f"Failed to load reminders: {e}")
            self._reminders = {}

    def _save_reminders(self):
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(json.dumps(self._reminders, indent=2))
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}")

    def _start_checker(self):
        if self._checker_task is None or self._checker_task.done():
            self._checker_task = asyncio.create_task(self._check_loop())

    async def _check_loop(self):
        """Background loop that fires reminders when due."""
        while True:
            try:
                now = datetime.now()
                fired = []

                async with self._lock:
                    for rid, reminder in list(self._reminders.items()):
                        remind_at = datetime.fromisoformat(reminder["remind_at"])
                        if remind_at <= now:
                            fired.append((rid, dict(reminder)))

                # Fire outside the lock (callbacks may take time)
                for rid, reminder_snapshot in fired:
                    await self._fire_reminder(rid, reminder_snapshot)

                # Update state under lock
                if fired:
                    async with self._lock:
                        for rid, _ in fired:
                            reminder = self._reminders.get(rid)
                            if not reminder:
                                continue

                            if reminder.get("recurring"):
                                interval = reminder.get("interval_seconds", 86400)
                                new_time = datetime.fromisoformat(
                                    reminder["remind_at"]
                                ) + timedelta(seconds=interval)
                                while new_time <= now:
                                    new_time += timedelta(seconds=interval)
                                reminder["remind_at"] = new_time.isoformat()
                                reminder["fire_count"] = reminder.get("fire_count", 0) + 1
                            else:
                                del self._reminders[rid]

                        self._save_reminders()

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[REMINDER] Check loop error: {e}")

            await asyncio.sleep(10)

    async def _fire_reminder(self, rid: str, reminder: dict):
        """Deliver a reminder notification."""
        message = reminder["message"]
        category = reminder.get("category", "")
        priority = reminder.get("priority", "normal")

        prefix = ""
        if priority == "high":
            prefix = "[URGENT] "
        elif category:
            prefix = f"[{category.upper()}] "

        full_message = f"{prefix}REMINDER: {message}"

        logger.info(f"[REMINDER] Firing reminder {rid}: {full_message}")

        # Use callback if available (Electron, Slack, etc.)
        if ReminderTool._notify_callback:
            try:
                await ReminderTool._notify_callback(
                    full_message,
                    {
                        "reminder_id": rid,
                        "category": category,
                        "priority": priority,
                        "recurring": bool(reminder.get("recurring")),
                        "execute_prompt": reminder.get("execute_prompt", ""),
                    },
                )
                logger.info("[REMINDER] Callback invoked successfully")
            except Exception as e:
                logger.error(f"Notification callback failed: {e}")
        else:
            logger.warning("[REMINDER] No callback set - notification will be missed!")
            # Fallback to console
            print(f"\n🔔 {full_message}\n")

        logger.info(f"Fired reminder: {rid} - {message}")

    @property
    def name(self) -> str:
        return "reminder"

    @property
    def description(self) -> str:
        return (
            "Schedule reminders with natural language times. "
            "Actions: add, list, remove, snooze, edit. "
            "Supports recurring (daily/weekly/custom), categories, and priorities. "
            "Time examples: 'in 5 minutes', 'tomorrow at 9am', '3pm', 'next friday at noon'. "
            "Recurring: set repeat='daily', 'weekly', or 'every 2 hours'. "
            "Reminders persist across sessions."
        )

    @property
    def compact_description(self) -> str:
        return (
            "Set reminders. Actions: add/list/remove/snooze/edit. "
            "Times: 'in 5 min', 'tomorrow 9am', '3pm'. "
            "Supports recurring (daily/weekly) and categories."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove", "snooze", "edit"],
                    "description": "Reminder action",
                },
                "reminder_id": {
                    "type": "string",
                    "description": "Reminder ID (auto-generated if not provided)",
                },
                "message": {
                    "type": "string",
                    "description": "Reminder message text",
                },
                "remind_at": {
                    "type": "string",
                    "description": "When to remind: natural language ('in 5 min', 'tomorrow at 9am', '3pm') or ISO datetime",
                },
                "execute_prompt": {
                    "type": "string",
                    "description": "Optional command/prompt to execute automatically when the reminder fires (e.g. 'open youtube.com/catvideo')",
                },
                "repeat": {
                    "type": "string",
                    "description": "Recurrence: 'daily', 'weekly', 'hourly', or 'every X minutes/hours/days'",
                },
                "category": {
                    "type": "string",
                    "description": "Category: work, personal, health, finance, shopping, etc.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high"],
                    "description": "Priority level (default: normal)",
                },
                "minutes": {
                    "type": "integer",
                    "description": "Minutes to snooze (for snooze action, default: 5)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        reminder_id: str = "",
        message: str = "",
        remind_at: str = "",
        repeat: str = "",
        category: str = "",
        priority: str = "normal",
        minutes: int = 5,
        execute_prompt: str = "",
    ) -> str:
        self._start_checker()

        match action:
            case "add":
                return self._add(
                    reminder_id, message, remind_at, repeat, category, priority, execute_prompt
                )
            case "list":
                return self._list(category)
            case "remove":
                return self._remove(reminder_id)
            case "snooze":
                return self._snooze(reminder_id, minutes)
            case "edit":
                return self._edit(reminder_id, message, remind_at, category, priority)
            case _:
                return f"Unknown action: {action}"

    def _add(
        self,
        reminder_id: str,
        message: str,
        remind_at: str,
        repeat: str,
        category: str,
        priority: str,
        execute_prompt: str = "",
    ) -> str:
        if not message:
            return "Error: message is required"
        if not remind_at:
            return (
                "Error: remind_at is required (e.g. 'in 5 minutes', 'tomorrow at 9am')"
            )

        # Parse time using platform NLP
        remind_time = parse_natural_time(remind_at)
        if remind_time is None:
            return (
                f"Error: Could not parse time '{remind_at}'. "
                "Try: 'in 5 minutes', 'tomorrow at 9am', '3pm', 'next friday at noon'"
            )

        if not reminder_id:
            reminder_id = f"r_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        reminder_data: dict[str, Any] = {
            "message": message,
            "remind_at": remind_time.isoformat(),
            "created_at": datetime.now().isoformat(),
            "category": category,
            "priority": priority,
            "execute_prompt": execute_prompt,
        }

        # Handle recurring
        if repeat:
            interval = self._parse_repeat(repeat)
            if interval:
                reminder_data["recurring"] = True
                reminder_data["interval_seconds"] = interval
                reminder_data["repeat_label"] = repeat
                reminder_data["fire_count"] = 0

        self._reminders[reminder_id] = reminder_data
        self._save_reminders()

        # Build a human-friendly time description
        time_str = remind_time.strftime("%Y-%m-%d %H:%M")

        output = ToolOutput(
            summary=f'Reminder set: "{message}" at {time_str}',
            source="reminder",
        )

        info = {"message": message, "time": time_str}
        if category:
            info["category"] = category
        if priority != "normal":
            info["priority"] = priority
        if repeat:
            info["repeats"] = repeat
        output.data.append(info)

        return self.format_output(output.render())

    def _parse_repeat(self, repeat: str) -> int | None:
        """Parse a repeat/recurrence string into seconds."""
        repeat = repeat.strip().lower()

        presets = {
            "hourly": 3600,
            "daily": 86400,
            "weekly": 604800,
            "every hour": 3600,
            "every day": 86400,
            "every week": 604800,
        }

        if repeat in presets:
            return presets[repeat]

        # "every X minutes/hours/days"
        if repeat.startswith("every "):
            return parse_duration_seconds(repeat[6:])

        return parse_duration_seconds(repeat)

    def _list(self, category: str = "") -> str:
        if not self._reminders:
            return "No reminders scheduled. Use action='add' to create one."

        output = ToolOutput(
            summary=f"{len(self._reminders)} reminder(s) scheduled",
            source="reminder",
        )

        sorted_reminders = sorted(
            self._reminders.items(),
            key=lambda x: x[1]["remind_at"],
        )

        for rid, r in sorted_reminders:
            if category and r.get("category", "") != category.lower():
                continue

            remind_at = datetime.fromisoformat(r["remind_at"])
            now = datetime.now()
            delta = remind_at - now

            # Friendly time-until
            if delta.total_seconds() < 60:
                time_str = "< 1 min"
            elif delta.total_seconds() < 3600:
                time_str = f"in {int(delta.total_seconds() / 60)} min"
            elif delta.total_seconds() < 86400:
                hours = int(delta.total_seconds() / 3600)
                time_str = f"in {hours}h"
            else:
                days = int(delta.total_seconds() / 86400)
                time_str = f"in {days}d"

            item: dict[str, Any] = {
                "id": rid,
                "message": r["message"][:60],
                "when": f"{remind_at.strftime('%m/%d %H:%M')} ({time_str})",
            }
            if r.get("recurring"):
                item["repeats"] = r.get("repeat_label", "yes")
            if r.get("category"):
                item["cat"] = r["category"]
            if r.get("priority", "normal") != "normal":
                item["priority"] = r["priority"]

            output.data.append(item)

        return self.format_output(output.render())

    def _remove(self, reminder_id: str) -> str:
        if not reminder_id:
            return "Error: reminder_id is required"

        # Support partial match
        match = None
        for rid in self._reminders:
            if rid == reminder_id or rid.endswith(reminder_id):
                match = rid
                break

        if match:
            msg = self._reminders[match]["message"]
            del self._reminders[match]
            self._save_reminders()
            return f"Removed reminder '{match}': {msg}"
        return f"Reminder not found: {reminder_id}"

    def _snooze(self, reminder_id: str, minutes: int) -> str:
        if not reminder_id:
            return "Error: reminder_id is required"

        minutes = max(1, min(minutes, 1440))

        match = None
        for rid in self._reminders:
            if rid == reminder_id or rid.endswith(reminder_id):
                match = rid
                break

        if not match:
            return f"Reminder not found: {reminder_id}"

        new_time = datetime.now() + timedelta(minutes=minutes)
        self._reminders[match]["remind_at"] = new_time.isoformat()
        self._save_reminders()

        return (
            f"Snoozed '{match}' for {minutes} min (now: {new_time.strftime('%H:%M')})"
        )

    def _edit(
        self,
        reminder_id: str,
        message: str = "",
        remind_at: str = "",
        category: str = "",
        priority: str = "",
    ) -> str:
        if not reminder_id:
            return "Error: reminder_id is required"

        match = None
        for rid in self._reminders:
            if rid == reminder_id or rid.endswith(reminder_id):
                match = rid
                break

        if not match:
            return f"Reminder not found: {reminder_id}"

        r = self._reminders[match]
        changes = []

        if message:
            r["message"] = message
            changes.append("message")
        if remind_at:
            new_time = parse_natural_time(remind_at)
            if new_time:
                r["remind_at"] = new_time.isoformat()
                changes.append(f"time -> {new_time.strftime('%H:%M')}")
            else:
                return f"Could not parse time: {remind_at}"
        if category:
            r["category"] = category
            changes.append(f"category -> {category}")
        if priority:
            r["priority"] = priority
            changes.append(f"priority -> {priority}")

        self._save_reminders()
        return f"Updated '{match}': {', '.join(changes)}"
