"""Natural language parsing utilities shared across tools.

Provides date/time parsing, duration parsing, and other NLP helpers
that multiple tools need (reminder, scheduler, datetime_tool, etc).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from datetime import time as dt_time


# Day-of-week names
_DOW = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# Relative day names
_RELATIVE_DAYS = {
    "today": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
    "next week": 7,
}

# Duration unit mapping
_DURATION_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1, "s": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60, "m": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600, "h": 3600,
    "day": 86400, "days": 86400, "d": 86400,
    "week": 604800, "weeks": 604800, "w": 604800,
}


def parse_duration_seconds(text: str) -> int | None:
    """Parse a duration string into total seconds.

    Examples: "5 minutes", "1h30m", "2 hours and 30 minutes", "90s"
    """
    text = text.strip().lower()

    # Pattern: "Xh Ym Zs" compact form
    compact = re.findall(r"(\d+)\s*(h|m|s|hr|min|sec)", text)
    if compact:
        total = 0
        for val, unit in compact:
            total += int(val) * _DURATION_UNITS.get(unit, 0)
        return total if total > 0 else None

    # Pattern: "X unit (and Y unit)"
    parts = re.findall(r"(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)", text)
    if parts:
        total = 0
        for val, unit in parts:
            total += int(val) * _DURATION_UNITS.get(unit, 0)
        return total if total > 0 else None

    # Single number assumed as minutes
    single = re.match(r"^(\d+)$", text)
    if single:
        return int(single.group(1)) * 60

    return None


def parse_time_of_day(text: str) -> dt_time | None:
    """Parse a time-of-day string.

    Examples: "3pm", "15:30", "9:00 AM", "noon", "midnight"
    """
    text = text.strip().lower()

    # Special names
    if text in ("noon", "midday", "12 noon"):
        return dt_time(12, 0)
    if text in ("midnight", "12 midnight"):
        return dt_time(0, 0)
    if text == "morning":
        return dt_time(9, 0)
    if text == "afternoon":
        return dt_time(14, 0)
    if text == "evening":
        return dt_time(18, 0)
    if text == "night":
        return dt_time(21, 0)

    is_pm = "pm" in text
    is_am = "am" in text
    cleaned = re.sub(r"\s*(am|pm|a\.m\.|p\.m\.)\s*", "", text).strip()

    # HH:MM or HH:MM:SS
    time_match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", cleaned)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        second = int(time_match.group(3) or 0)

        if is_pm and hour < 12:
            hour += 12
        elif is_am and hour == 12:
            hour = 0

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return dt_time(hour, minute, second)
        return None

    # Just a number: "3", "15"
    num_match = re.match(r"^(\d{1,2})$", cleaned)
    if num_match:
        hour = int(num_match.group(1))
        if is_pm and hour < 12:
            hour += 12
        elif is_am and hour == 12:
            hour = 0
        elif not is_am and not is_pm and hour < 8:
            # Assume PM for small numbers without am/pm
            hour += 12

        if 0 <= hour <= 23:
            return dt_time(hour, 0)

    return None


def parse_natural_date(text: str, reference: datetime | None = None) -> datetime | None:
    """Parse a natural language date expression.

    Examples: "tomorrow", "next friday", "december 25", "2025-03-15"
    Returns a datetime at midnight of that day.
    """
    now = reference or datetime.now()
    text = text.strip().lower()

    # Relative days
    for name, offset in _RELATIVE_DAYS.items():
        if text == name:
            target = now + timedelta(days=offset)
            return target.replace(hour=0, minute=0, second=0, microsecond=0)

    # "next <day_of_week>"
    next_match = re.match(r"next\s+(\w+)", text)
    if next_match:
        dow_name = next_match.group(1)
        if dow_name in _DOW:
            target_dow = _DOW[dow_name]
            days_ahead = (target_dow - now.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            target = now + timedelta(days=days_ahead)
            return target.replace(hour=0, minute=0, second=0, microsecond=0)

    # Day of week without "next"
    for name, dow in _DOW.items():
        if text == name:
            days_ahead = (dow - now.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            target = now + timedelta(days=days_ahead)
            return target.replace(hour=0, minute=0, second=0, microsecond=0)

    # ISO format
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    # "Month Day" or "Day Month"
    months = {
        "january": 1, "jan": 1, "february": 2, "feb": 2,
        "march": 3, "mar": 3, "april": 4, "apr": 4,
        "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
        "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10, "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }
    for month_name, month_num in months.items():
        match = re.match(rf"{month_name}\s+(\d{{1,2}})", text)
        if match:
            day = int(match.group(1))
            year = now.year
            target = datetime(year, month_num, day)
            if target < now:
                target = datetime(year + 1, month_num, day)
            return target

    return None


def parse_natural_time(text: str, reference: datetime | None = None) -> datetime | None:
    """Parse a natural language time expression into a datetime.

    Handles relative ("in 5 minutes"), absolute ("3pm"), and
    combined ("tomorrow at 3pm", "next friday at noon") expressions.
    """
    now = reference or datetime.now()
    text = text.strip().lower()

    # "in X minutes/hours/etc"
    in_match = re.match(r"in\s+(.+)", text)
    if in_match:
        seconds = parse_duration_seconds(in_match.group(1))
        if seconds is not None:
            return now + timedelta(seconds=seconds)

    # "at <time>"
    at_match = re.match(r"at\s+(.+)", text)
    if at_match:
        tod = parse_time_of_day(at_match.group(1))
        if tod:
            target = now.replace(hour=tod.hour, minute=tod.minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

    # "<date> at <time>"
    date_at_match = re.match(r"(.+?)\s+at\s+(.+)", text)
    if date_at_match:
        date_part = parse_natural_date(date_at_match.group(1), now)
        time_part = parse_time_of_day(date_at_match.group(2))
        if date_part and time_part:
            return date_part.replace(
                hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
            )
        elif date_part:
            return date_part
        elif time_part:
            target = now.replace(
                hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
            )
            if target <= now:
                target += timedelta(days=1)
            return target

    # Just a date
    date_only = parse_natural_date(text, now)
    if date_only:
        return date_only

    # Just a time
    tod = parse_time_of_day(text)
    if tod:
        target = now.replace(hour=tod.hour, minute=tod.minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    # ISO datetime
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    # Bare duration without "in" prefix: "5 minutes", "2 mins", "1h30m"
    # LLMs often omit the "in" prefix when passing remind_at values
    seconds = parse_duration_seconds(text)
    if seconds is not None:
        return now + timedelta(seconds=seconds)

    return None
