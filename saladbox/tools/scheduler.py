"""Task scheduling tool using APScheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from saladbox.tools.base import BaseTool

logger = logging.getLogger(__name__)


class SchedulerTool(BaseTool):
    """Schedule and manage recurring or one-time tasks."""

    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None
        self._task_outputs: dict[str, list[str]] = {}

    def _ensure_scheduler(self):
        """Lazily start the scheduler when first needed (requires event loop)."""
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()
            self._scheduler.start()

    @property
    def name(self) -> str:
        return "scheduler"

    @property
    def description(self) -> str:
        return (
            "Schedule tasks to run at specific times or intervals. "
            "Actions: add_interval, add_cron, add_once, remove, list. "
            "Scheduled tasks execute shell commands."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add_interval", "add_cron", "add_once", "remove", "list", "get_output"],
                    "description": "Scheduler action to perform",
                },
                "job_id": {
                    "type": "string",
                    "description": "Unique identifier for the job",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to execute when the job fires",
                },
                "seconds": {
                    "type": "integer",
                    "description": "Interval in seconds (for add_interval)",
                },
                "cron_expression": {
                    "type": "string",
                    "description": "Cron expression like '*/5 * * * *' (for add_cron: min hour day month dow)",
                },
                "run_at": {
                    "type": "string",
                    "description": "ISO datetime string for one-time execution (for add_once)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        job_id: str = "",
        command: str = "",
        seconds: int = 0,
        cron_expression: str = "",
        run_at: str = "",
    ) -> str:
        self._ensure_scheduler()
        match action:
            case "add_interval":
                return self._add_interval(job_id, command, seconds)
            case "add_cron":
                return self._add_cron(job_id, command, cron_expression)
            case "add_once":
                return self._add_once(job_id, command, run_at)
            case "remove":
                return self._remove(job_id)
            case "list":
                return self._list()
            case "get_output":
                return self._get_output(job_id)
            case _:
                return f"Unknown action: {action}"

    def _job_callback(self, job_id: str, command: str):
        """Synchronous callback that creates an async task for shell execution."""
        asyncio.create_task(self._run_command(job_id, command))

    async def _run_command(self, job_id: str, command: str):
        """Execute the scheduled shell command."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode(errors="replace") if stdout else ""
            if job_id not in self._task_outputs:
                self._task_outputs[job_id] = []
            self._task_outputs[job_id].append(
                f"[{datetime.now().isoformat()}] Exit: {proc.returncode}\n{output}"
            )
            # Keep only last 10 outputs
            self._task_outputs[job_id] = self._task_outputs[job_id][-10:]
        except Exception as e:
            logger.error(f"Scheduled job {job_id} failed: {e}")

    def _add_interval(self, job_id: str, command: str, seconds: int) -> str:
        if not job_id or not command or seconds <= 0:
            return "job_id, command, and positive seconds are required"
        self._scheduler.add_job(
            self._job_callback,
            trigger=IntervalTrigger(seconds=seconds),
            id=job_id,
            args=[job_id, command],
            replace_existing=True,
        )
        return f"Scheduled '{job_id}': runs '{command}' every {seconds}s"

    def _add_cron(self, job_id: str, command: str, cron_expression: str) -> str:
        if not job_id or not command or not cron_expression:
            return "job_id, command, and cron_expression are required"
        parts = cron_expression.split()
        if len(parts) != 5:
            return "Cron expression must have 5 fields: minute hour day month day_of_week"
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
        self._scheduler.add_job(
            self._job_callback,
            trigger=trigger,
            id=job_id,
            args=[job_id, command],
            replace_existing=True,
        )
        return f"Scheduled '{job_id}': runs '{command}' on cron '{cron_expression}'"

    def _add_once(self, job_id: str, command: str, run_at: str) -> str:
        if not job_id or not command or not run_at:
            return "job_id, command, and run_at are required"
        try:
            dt = datetime.fromisoformat(run_at)
        except ValueError:
            return f"Invalid datetime format: {run_at}. Use ISO format."
        self._scheduler.add_job(
            self._job_callback,
            trigger=DateTrigger(run_date=dt),
            id=job_id,
            args=[job_id, command],
            replace_existing=True,
        )
        return f"Scheduled '{job_id}': runs '{command}' once at {run_at}"

    def _remove(self, job_id: str) -> str:
        if not job_id:
            return "job_id is required"
        try:
            self._scheduler.remove_job(job_id)
            return f"Removed job: {job_id}"
        except Exception:
            return f"Job not found: {job_id}"

    def _list(self) -> str:
        jobs = self._scheduler.get_jobs()
        if not jobs:
            return "No scheduled jobs"
        lines = ["Scheduled jobs:"]
        for job in jobs:
            next_run = job.next_run_time
            lines.append(f"  {job.id}: next run at {next_run}")
        return "\n".join(lines)

    def _get_output(self, job_id: str) -> str:
        outputs = self._task_outputs.get(job_id, [])
        if not outputs:
            return f"No output recorded for job: {job_id}"
        return f"Output for {job_id} (last {len(outputs)} runs):\n" + "\n---\n".join(outputs)
