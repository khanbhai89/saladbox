# Saladbox Platform — Context File

> This directory provides shared utilities that **all tools and core modules** import. Each module is independent and self-contained. It acts as the standard library for the saladbox application.

---

## `__init__.py`  *(28 lines)*
**Purpose**: Convenience re-exports so consumers can write `from saladbox.platform import fetch_url, ToolOutput`.

**Exports**:
* **Output**: `ToolOutput`, `compress_result`, `truncate_smart`
* **Parsing**: `parse_natural_time`, `parse_natural_date`, `parse_duration_seconds`
* **HTTP**: `fetch_url`, `fetch_json`

---

## `output.py`  *(110 lines)*
**Purpose**: Standardized output formatting and compression for tool results. Ensures consistent structure and automatic truncation for local model context limits.

### Constants
| Name | Value | Description |
|------|-------|-------------|
| `DEFAULT_MAX_CHARS` | 2000 | Default maximum characters for tool output |
| `COMPACT_MAX_CHARS` | 1200 | Reduced limit for small context models (≤8K) |

### Class: `ToolOutput`
Fields: `summary: str`, `data: list[dict]`, `details: str`, `error: str`, `action_hint: str`, `source: str`.

| Method | What it does |
|--------|--------------|
| `render(max_chars=2000, compact=False) -> str` | Builds output string: summary → structured data items → details → action hint. Stops adding data items at 80% of max_chars and appends "... (N more items)". |

### Functions
| Function | What it does |
|----------|--------------|
| `truncate_smart(text, max_chars) -> str` | Cuts at paragraph boundary (if >50% of text remains), then sentence boundary, then hard cutoff. Appends "... (truncated)". |
| `compress_result(text, max_chars) -> str` | Collapses multiple blank lines, multiple spaces, strips each line, then calls `truncate_smart`. |

---

## `http.py`  *(182 lines)*
**Purpose**: Shared async HTTP client with browser-like headers, CAPTCHA detection, and bot-block awareness.

### Module State
* `_client: httpx.AsyncClient | None` — Singleton shared client (HTTP/2, follow redirects, 15s timeout).
* `_USER_AGENTS` — List of 5 modern Chrome user-agent strings for random rotation.
* `_BLOCKED_DOMAINS` — Set of 14 known bot-blocking domains (LinkedIn, Facebook, Twitter, etc.).
* `_BLOCK_PATTERNS` — List of 16 CAPTCHA/block detection strings.

### Functions
| Function | What it does |
|----------|--------------|
| `_get_browser_headers(url) -> dict` | Full set of headers mimicking Chrome 131: `User-Agent`, `Accept`, `Sec-Ch-Ua`, `Sec-Fetch-*`, `Referer`, etc. **Note**: Does NOT set `Accept-Encoding` because httpx handles decompression internally. |
| `_get_client() -> httpx.AsyncClient` | Returns the module-level client singleton. Creates it if `None` or closed. Limits: 10 max connections, 5 keepalive. |
| `is_blocked(html) -> bool` | Checks first 3000 chars of HTML for ≥2 CAPTCHA/block patterns. |
| `is_blocked_domain(url) -> bool` | Checks URL against known blocked domains. |
| `fetch_url(url, timeout?, headers?) -> (status, text)` | GET request with browser headers. Returns `(403, "blocked")` if CAPTCHA detected. Returns `(0, error_msg)` on failure. |
| `fetch_json(url, timeout?, headers?) -> (status, data)` | Same as `fetch_url` but sets `Accept: application/json` and parses response as JSON. |
| `cleanup()` | Closes the shared client. Called on app shutdown. |

---

## `parsing.py`  *(268 lines)*
**Purpose**: Natural language date/time parsing shared across tools (reminder, scheduler, datetime_tool).

### Duration Parsing
**`parse_duration_seconds(text) -> int | None`**

Parses strings like:
| Input | Output (seconds) |
|-------|-----------------|
| `"5 minutes"` | 300 |
| `"1h30m"` | 5400 |
| `"2 hours and 30 minutes"` | 9000 |
| `"90s"` | 90 |
| `"30"` (bare number) | 1800 (assumes minutes) |

### Time-of-Day Parsing
**`parse_time_of_day(text) -> datetime.time | None`**

Handles: `"3pm"`, `"15:30"`, `"9:00 AM"`, `"noon"`, `"midnight"`, `"morning"` (→9:00), `"afternoon"` (→14:00), `"evening"` (→18:00), `"night"` (→21:00).

**AM/PM ambiguity rule**: If no am/pm and hour < 8, assumes PM.

### Date Parsing
**`parse_natural_date(text, reference?) -> datetime | None`**

Handles:
* Relative: `"today"`, `"tomorrow"`, `"day after tomorrow"`, `"next week"`
* Day-of-week: `"friday"`, `"next tuesday"`
* ISO format: `"2025-03-15"`
* Month+day: `"december 25"`, `"jan 1"` (auto-increments year if date is past)

### Combined Date+Time Parsing
**`parse_natural_time(text, reference?) -> datetime | None`**

Handles all combinations:
* Relative: `"in 5 minutes"`, `"in 2 hours"`
* Absolute time: `"at 3pm"` (wraps to next day if past)
* Combined: `"tomorrow at 3pm"`, `"next friday at noon"`
* ISO datetime
* **Bare duration fallback**: `"5 minutes"` (without "in" prefix — LLMs often omit it)
