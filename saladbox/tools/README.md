# Saladbox Tools — Context File

> This directory contains all built-in tools the agent can invoke. Every tool extends `BaseTool` and is auto-registered by `__init__.py`.

---

## `__init__.py`  *(82 lines)*
**Purpose**: Auto-discovery and registration of all tools.

### `TOOL_MAP` (dict)
Maps config key → tool class for all 33 tools:

```
shell → ShellTool, python_exec → PythonExecTool, browser → BrowserTool,
filesystem → FileSystemTool, system_monitor → SystemMonitorTool,
scheduler → SchedulerTool, process_manager → ProcessManagerTool,
code_editor → CodeEditorTool, git → GitTool, reminder → ReminderTool,
web_search → WebSearchTool, calculator → CalculatorTool,
datetime_tool → DateTimeTool, clipboard → ClipboardTool, notes → NotesTool,
weather → WeatherTool, http_client → HttpClientTool, json_yaml → JsonYamlTool,
encoding → EncodingTool, text → TextTool, password → PasswordTool,
finance → FinanceTool, timer → TimerTool, qrcode → QRCodeTool,
translate → TranslateTool, color → ColorTool, unit_converter → UnitConverterTool,
url → URLTool, location → LocationTool, docker → DockerTool,
open_url → OpenURLTool, screen_capture → ScreenCaptureTool, image_gen → ImageGenTool
```

### `get_enabled_tools(config: dict[str, bool]) -> list[BaseTool]`
Iterates `TOOL_MAP`, instantiates tools where `config[name] == True`.

---

## `base.py`
**Purpose**: Abstract base class all tools extend.

### Class: `BaseTool`
| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Tool identifier used in schemas and registry |
| `description` | `str` | One-line description for LLM |
| `parameters` | `dict` | JSON Schema of accepted arguments |
| `category` | `ToolCategory` | Logical grouping (`system`, `files`, `code`, etc.) |

| Method | Description |
|--------|-------------|
| `to_schema(compact?, strict?) -> dict` | Returns OpenAI-compatible function schema. `strict` adds `additionalProperties: false`. `compact` truncates descriptions. |
| `execute(**kwargs) -> str` | Abstract async method. Returns string result. |

---

## System Tools

### `shell.py` — `ShellTool`
**Name**: `run_shell`  
**Actions**: Runs arbitrary shell commands via `asyncio.create_subprocess_shell`.  
**Args**: `command: str`, `working_dir: str = "."`, `timeout: int = 30` (clamped 1–600).  
**Output**: Combined stdout + stderr. Truncated at 8000 chars.  
**Safety**: Working dir validated to exist. Timeout kills subprocess.

### `python_exec.py` — `PythonExecTool`
**Name**: `run_python`  
**Actions**: Executes Python code in a subprocess (`python3 -c`).  
**Args**: `code: str`, `timeout: int = 15` (clamped 1–300).  
**Output**: stdout + stderr. Isolated from main process.

### `process_manager.py` — `ProcessManagerTool`
**Name**: `process_manager`  
**Actions**: `start` (background process), `stop`, `list`, `logs` (tail N lines).  
**Internal state**: Dict of managed `asyncio.subprocess.Process` objects.  
**Logs**: Per-process log buffers stored in circular deques.

### `scheduler.py` — `SchedulerTool`
**Name**: `scheduler`  
**Actions**: `schedule` (one-shot or cron), `list`, `cancel`.  
**Cron**: Uses `croniter` for cron expression evaluation.  
**Persistence**: In-memory only — scheduled jobs are lost on restart.

### `system_monitor.py` — `SystemMonitorTool`
**Name**: `system_monitor`  
**Actions**: `overview`, `cpu`, `memory`, `disk`, `network`, `processes`.  
**Dependency**: `psutil`.  
**Output**: Formatted text tables of system stats.

---

## File & Code Tools

### `filesystem.py` — `FileSystemTool`
**Name**: `filesystem`  
**Actions**: `read`, `write`, `append`, `list`, `search` (glob), `info` (stat), `mkdir`, `delete`, `copy`, `move`, `tree`.  
**Args**: `action`, `path`, `content`, `pattern`.  
**Safety**: Reads are capped at 50,000 chars. `tree` defaults depth 3.

### `code_editor.py` — `CodeEditorTool`
**Name**: `code_editor`  
**Actions**: `view` (with line numbers), `edit` (insert/replace/delete), `search` (grep), `scan` (project tree), `create`, `diff`, `run` (dev/build/test commands).  
**Args**: `action`, `path`, `start_line`, `end_line`, `edit_type`, `content`, `find`, `replace`, `pattern`, `file_glob`, `depth`, `command`, `run_type`, `scan_path`.  
**Smart editing**: `edit_type` values: `insert`, `replace`, `delete`, `find_replace`.  
**Project scanning**: `scan` action generates file tree with language detection from extensions.

### `git.py` — `GitTool`
**Name**: `git`  
**Actions**: `status`, `log`, `diff`, `add`, `commit`, `push`, `pull`, `branch`, `checkout`, `clone`, `create_pr`.  
**PR creation**: Uses `gh` CLI. Generates title and body.  
**Safety**: All commands executed via `asyncio.create_subprocess_exec` with 30s timeout.

---

## Web & Network Tools

### `web_search.py` — `WebSearchTool`
**Name**: `web_search`  
**Backends**: DuckDuckGo (`duckduckgo_search`), Google (`SerpAPI` if `SERPAPI_KEY` set), Bing (`BING_API_KEY`).  
**Actions**: `web` search, `news` search.  
**Output**: Title + URL + snippet for each result.

### `browser.py` — `BrowserTool`
**Name**: `browser`  
**Actions**: `navigate`, `click`, `fill_form`, `screenshot`, `get_text`, `get_links`, `execute_js`, `scroll`.  
**Dependency**: `playwright` (auto-installed headless Chromium).  
**Args**: `action`, `selector`, `value`, `timeout: int = 30000`.

### `http_client.py` — `HttpClientTool`
**Name**: `http_client`  
**Methods**: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`.  
**Args**: `method`, `url`, `headers: dict`, `body`, `params: dict`, `timeout: int = 30`.  
**Uses**: `saladbox.platform.http.fetch_url` / `fetch_json` shared client.

### `open_url.py` — `OpenURLTool`
**Name**: `open_url`  
**Actions**: Opens URL in default browser or a specific site search.  
**Args**: `url`, `site` (e.g., "youtube", "github"), `query`.  
**Mechanism**: `webbrowser.open()`.

---

## Utility Tools

### `calculator.py` — `CalculatorTool`
**Name**: `calculator`  
**Args**: `expression: str`, `precision: int = 6`.  
**Safety**: Uses `ast.literal_eval` + safe math functions. No `eval()`.

### `datetime_tool.py` — `DateTimeTool`
**Name**: `datetime_tool`  
**Actions**: `now`, `convert` (timezone), `add` (offset), `diff`, `format`, `parse`, `countdown`.  
**Uses**: `saladbox.platform.parsing` for natural language date/time parsing.

### `clipboard.py` — `ClipboardTool`
**Name**: `clipboard`  
**Actions**: `copy`, `paste`.  
**Mechanism**: macOS `pbcopy`/`pbpaste`, Linux `xclip`, Windows `pyperclip`.

### `notes.py` — `NotesTool`
**Name**: `notes`  
**Actions**: `create`, `list`, `search`, `delete`.  
**Storage**: SQLite database in `data/notes.db`.

### `reminder.py` — `ReminderTool`
**Name**: `reminder`  
**Actions**: `set`, `list`, `cancel`, `snooze`.  
**Persistence**: SQLite database. Uses `saladbox.platform.parsing.parse_natural_time()` for "remind me at 3pm" style input.

### `timer.py` — `TimerTool`
**Name**: `timer`  
**Actions**: `start`, `stop`, `list`, `lap`.  
**Storage**: In-memory dict of named timers.

### `weather.py` — `WeatherTool`
**Name**: `weather`  
**Args**: `location`, `units` (metric/imperial), `forecast` (current/3day/5day), `format` (text/json).  
**API**: `wttr.in` free weather service.

### `finance.py` — `FinanceTool`
**Name**: `finance`  
**Actions**: `price` (stock), `crypto`, `convert` (currency exchange).  
**APIs**: CoinGecko (crypto), Alpha Vantage / Yahoo Finance (stocks).

### `password.py` — `PasswordTool`
**Name**: `password`  
**Actions**: `generate`, `passphrase`, `strength` (check), `batch`.  
**Args**: `length`, `include_uppercase`, `include_lowercase`, `include_numbers`, `include_symbols`, `word_count`, `count`.

### `qrcode_tool.py` — `QRCodeTool`
**Name**: `qrcode`  
**Actions**: `generate` (text/URL), `wifi`, `vcard`.  
**Output**: Saves PNG to temp directory, returns base64-encoded image.

### `translate.py` — `TranslateTool`
**Name**: `translate`  
**Actions**: `translate`, `detect` (language).  
**API**: Google Translate (free `googletrans` library).

### `color.py` — `ColorTool`
**Name**: `color`  
**Actions**: `info` (convert between hex/rgb/hsl), `palette` (generate N harmonious colors), `contrast` (accessibility check).

### `unit_converter.py` — `UnitConverterTool`
**Name**: `unit_converter`  
**Categories**: `length`, `weight`, `temperature`, `volume`, `area`, `speed`, `data`, `time`.

### `url.py` — `URLTool`
**Name**: `url`  
**Actions**: `parse`, `build`, `encode`, `decode`, `join` (base + relative).

### `location.py` — `LocationTool`
**Name**: `location`  
**Actions**: `geocode` (address→lat/lon), `reverse` (lat/lon→address), `search` (places), `distance`.

### `docker.py` — `DockerTool`
**Name**: `docker`  
**Actions**: `ps` (list containers), `images`, `run`, `stop`, `logs`, `exec`, `build`.

### `json_yaml.py` — `JsonYamlTool`
**Name**: `json_yaml`  
**Actions**: `parse`, `format`, `convert` (JSON↔YAML), `query` (JMESPath-like paths).

### `encoding.py` — `EncodingTool`
**Name**: `encoding`  
**Actions**: `base64_encode`, `base64_decode`, `url_encode`, `url_decode`, `hash` (md5/sha256/sha512), `uuid`.

### `text.py` — `TextTool`
**Name**: `text`  
**Actions**: `count` (words/chars/lines), `replace`, `split`, `join`, `case` (upper/lower/title), `regex`.

---

## Media Tools

### `screen_capture.py` — `ScreenCaptureTool`
**Name**: `screen_capture`  
**Actions**: `capture` (full screen or region).  
**Mechanism**: macOS `screencapture`, Linux `gnome-screenshot` / `scrot`.  
**Output**: Saves PNG, returns path. The engine then switches to vision model to analyze it.

### `image_gen.py` — `ImageGenTool`
**Name**: `image_gen`  
**Backends**: `mflux` (Apple MLX Flux), `drawthings` (Draw Things HTTP API).  
**Args**: `prompt`, `width: int = 1024`, `height: int = 1024`, `steps: int = 2`, `seed`, `backend`.  
**Output**: Saves PNG to `~/saladbox_generated/`, returns file path.
