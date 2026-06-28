"""Date and time operations tool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from saladbox.tools.base import BaseTool

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


class DateTimeTool(BaseTool):
    """Date, time, and timezone operations."""

    COMMON_TIMEZONES = {
        "utc": "UTC",
        "gmt": "GMT",
        "est": "US/Eastern",
        "pst": "US/Pacific",
        "cst": "US/Central",
        "mst": "US/Mountain",
        "ist": "Asia/Kolkata",
        "jst": "Asia/Tokyo",
        "cet": "Europe/Paris",
        "bst": "Europe/London",
        "aedt": "Australia/Sydney",
        "uae": "Asia/Dubai",
        "china": "Asia/Shanghai",
        "singapore": "Asia/Singapore",
    }

    @property
    def name(self) -> str:
        return "datetime_tool"

    @property
    def description(self) -> str:
        return (
            "Get current date/time, convert between timezones, calculate date differences, "
            "and format dates. Useful for scheduling, timezone conversion, and date arithmetic."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "now",
                        "convert",
                        "add",
                        "subtract",
                        "diff",
                        "format",
                        "parse",
                    ],
                    "description": "The datetime operation to perform",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone name (e.g., 'US/Pacific', 'Europe/London', 'UTC')",
                },
                "datetime_str": {
                    "type": "string",
                    "description": "Datetime string for conversion or parsing",
                },
                "from_tz": {
                    "type": "string",
                    "description": "Source timezone for conversion",
                },
                "to_tz": {
                    "type": "string",
                    "description": "Target timezone for conversion",
                },
                "days": {
                    "type": "integer",
                    "description": "Days to add or subtract",
                },
                "hours": {
                    "type": "integer",
                    "description": "Hours to add or subtract",
                },
                "minutes": {
                    "type": "integer",
                    "description": "Minutes to add or subtract",
                },
                "format_str": {
                    "type": "string",
                    "description": "Format string (e.g., '%Y-%m-%d %H:%M:%S')",
                },
                "target_datetime": {
                    "type": "string",
                    "description": "Second datetime for difference calculation",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        timezone: str | None = None,
        datetime_str: str | None = None,
        from_tz: str | None = None,
        to_tz: str | None = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        format_str: str | None = None,
        target_datetime: str | None = None,
    ) -> str:
        try:
            if action == "now":
                return self._get_now(timezone)
            elif action == "convert":
                return self._convert(datetime_str, from_tz, to_tz)
            elif action == "add":
                return self._add(datetime_str, timezone, days, hours, minutes)
            elif action == "subtract":
                return self._subtract(datetime_str, timezone, days, hours, minutes)
            elif action == "diff":
                return self._diff(datetime_str, target_datetime)
            elif action == "format":
                return self._format(datetime_str, timezone, format_str)
            elif action == "parse":
                return self._parse(datetime_str)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"Error: {e!s}"

    def _get_now(self, tz_name: str | None) -> str:
        if tz_name:
            tz_name = self.COMMON_TIMEZONES.get(tz_name.lower(), tz_name)
            try:
                tz = ZoneInfo(tz_name)
                now = datetime.now(tz)
                return (
                    f"Current time in {tz_name}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
            except Exception:
                return f"Error: Unknown timezone '{tz_name}'"

        utc_now = datetime.now(UTC)
        local_now = datetime.now()
        return (
            f"UTC: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Local: {local_now.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def _convert(
        self, dt_str: str | None, from_tz: str | None, to_tz: str | None
    ) -> str:
        if not dt_str or not to_tz:
            return "Error: datetime_str and to_tz are required for conversion"

        to_tz = self.COMMON_TIMEZONES.get(to_tz.lower(), to_tz)

        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

        if from_tz:
            from_tz = self.COMMON_TIMEZONES.get(from_tz.lower(), from_tz)
            dt = dt.replace(tzinfo=ZoneInfo(from_tz))
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        target_tz = ZoneInfo(to_tz)
        converted = dt.astimezone(target_tz)

        return f"{dt_str} -> {converted.strftime('%Y-%m-%d %H:%M:%S %Z')}"

    def _add(
        self,
        dt_str: str | None,
        tz: str | None,
        days: int,
        hours: int,
        minutes: int,
    ) -> str:
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.now()
            if tz:
                tz = self.COMMON_TIMEZONES.get(tz.lower(), tz)
                dt = datetime.now(ZoneInfo(tz))

        delta = timedelta(days=days, hours=hours, minutes=minutes)
        result = dt + delta

        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} + {days}d {hours}h {minutes}m = {result.strftime('%Y-%m-%d %H:%M:%S')}"

    def _subtract(
        self,
        dt_str: str | None,
        tz: str | None,
        days: int,
        hours: int,
        minutes: int,
    ) -> str:
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.now()

        delta = timedelta(days=days, hours=hours, minutes=minutes)
        result = dt - delta

        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} - {days}d {hours}h {minutes}m = {result.strftime('%Y-%m-%d %H:%M:%S')}"

    def _diff(self, dt1_str: str | None, dt2_str: str | None) -> str:
        if not dt1_str or not dt2_str:
            return "Error: Two datetimes required for difference calculation"

        try:
            dt1 = datetime.fromisoformat(dt1_str.replace("Z", "+00:00"))
            dt2 = datetime.fromisoformat(dt2_str.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt1 = datetime.strptime(dt1_str, "%Y-%m-%d %H:%M:%S")
                dt2 = datetime.strptime(dt2_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return "Error: Invalid datetime format"

        diff = dt2 - dt1 if dt2 > dt1 else dt1 - dt2

        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        return f"Difference: {days} days, {hours} hours, {minutes} minutes, {seconds} seconds"

    def _format(
        self, dt_str: str | None, tz: str | None, fmt: str | None
    ) -> str:
        if not dt_str:
            return "Error: datetime_str required for formatting"

        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

        if tz and dt.tzinfo:
            tz = self.COMMON_TIMEZONES.get(tz.lower(), tz)
            dt = dt.astimezone(ZoneInfo(tz))

        fmt = fmt or "%Y-%m-%d %H:%M:%S"
        return f"Formatted: {dt.strftime(fmt)}"

    def _parse(self, dt_str: str | None) -> str:
        if not dt_str:
            return "Error: datetime_str required for parsing"

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%d-%m-%Y",
            "%B %d, %Y",
            "%b %d, %Y",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(dt_str, fmt)
                iso = dt.isoformat()
                return f"Parsed: {iso}\nYear: {dt.year}, Month: {dt.month}, Day: {dt.day}\nHour: {dt.hour}, Minute: {dt.minute}, Second: {dt.second}"
            except ValueError:
                continue

        return f"Error: Could not parse '{dt_str}'. Try format like '2024-01-15 14:30:00' or '2024-01-15'"
