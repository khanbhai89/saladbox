"""Platform standards: shared utilities for all saladbox tools.

These modules provide common functionality that tools can import
without coupling to each other. Each module is independent.
"""

from saladbox.platform.http import fetch_json, fetch_url
from saladbox.platform.output import ToolOutput, compress_result, truncate_smart
from saladbox.platform.parsing import (
    parse_duration_seconds,
    parse_natural_date,
    parse_natural_time,
)

__all__ = [
    # Output formatting
    "ToolOutput",
    "compress_result",
    "fetch_json",
    # HTTP utilities
    "fetch_url",
    "parse_duration_seconds",
    "parse_natural_date",
    # Natural language parsing
    "parse_natural_time",
    "truncate_smart",
]
